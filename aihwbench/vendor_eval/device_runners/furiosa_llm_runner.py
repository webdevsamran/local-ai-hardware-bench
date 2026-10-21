#!/usr/bin/env python3
"""Self-contained on-device benchmark runner for FuriosaAI ``furiosa-llm`` (RNGD).

This file is intentionally standalone (stdlib + ``furiosa_llm`` only) so it can be
copied to a vendor-provided evaluation machine without installing ``aihwbench``.
It emits one vendor-evaluation JSON document per model which the host-side
``aihwbench vendor-review`` tooling turns into review packages.

Methodology (aligned with vendor pre-publication review feedback):

* Prefix caching is **off** (``PrefixCacheConfig(enabled=False)`` passed through
  ``SchedulerConfig`` -- passing ``enable_prefix_caching=False`` directly to
  ``LLM()`` is silently swallowed by ``**kwargs`` in furiosa-llm 2026.4).
* Overlap scheduling is **on** for generative models
  (``SchedulingLoop.OVERLAP`` == ``--enable-overlap-scheduling``). It is not
  compatible with pooling models, which therefore run with the eager loop.
* Every prompt is a fresh, distinct random token sequence, so no KV/prefix reuse
  is possible between runs, streams, or batch items.
* Every table row records input/output length, number of runs, warm-up runs and
  the flags in effect. Accelerator power is sampled via ``furiosa-smi`` during
  every measured run; efficiency = output tok/s / total accelerator power (W),
  with no idle subtraction.
* Nothing is estimated: anything that could not be measured is ``null``.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as _dt
import hashlib
import json
import math
import os
import platform
import random
import statistics
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any

RUNNER_VERSION = "1.0.0"

DEFAULT_GRID = [
    (128, 128),
    (128, 1024),
    (1024, 128),
    (1024, 1024),
    (2048, 1024),
    (4096, 1024),
    (8192, 1024),
    (16384, 1024),
    (31744, 1024),
]
DEFAULT_CONCURRENCY = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512]
DEFAULT_POOL_SEQ = [256, 512, 1024, 2048]
DEFAULT_POOL_BATCH = [1, 8, 32, 64, 128]
DEFAULT_IMAGE_RES = [224, 448, 672, 1024]
DEFAULT_IMAGE_CONC = [1, 2, 4, 8]


# --------------------------------------------------------------------------- #
# Statistics helpers
# --------------------------------------------------------------------------- #
def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * q
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return float(s[int(k)])
    return float(s[f] * (c - k) + s[c] * (k - f))


def _mean(values: list[float]) -> float | None:
    return float(statistics.fmean(values)) if values else None


def _std(values: list[float]) -> float | None:
    return float(statistics.stdev(values)) if len(values) >= 2 else None


def _r(v: float | None, nd: int = 2) -> float | None:
    return None if v is None else round(float(v), nd)


# --------------------------------------------------------------------------- #
# furiosa-smi telemetry (no fallbacks: failed samples are dropped, never faked)
# --------------------------------------------------------------------------- #
def _num(val: Any) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val)
    for tok in ("°C", "MHz", "W"):
        s = s.replace(tok, "")
    try:
        return float(s.strip().split()[0])
    except (ValueError, IndexError):
        return None


def smi_snapshot(device: str) -> dict[str, Any] | None:
    try:
        info = json.loads(
            subprocess.check_output(
                ["furiosa-smi", "info", "--format", "json"], text=True, timeout=5,
                stderr=subprocess.DEVNULL,
            )
        )
        status = json.loads(
            subprocess.check_output(
                ["furiosa-smi", "status", "--format", "json"], text=True, timeout=5,
                stderr=subprocess.DEVNULL,
            )
        )
    except Exception:  # noqa: BLE001
        return None
    idev = next((d for d in info if d.get("dev_name") == device), info[0] if info else {})
    sdev = next((d for d in status if d.get("device") == device), status[0] if status else {})
    pes = [float(p.get("pe_utilization", 0.0)) for p in sdev.get("pe_utilizations", [])]
    mem = sdev.get("memory", {}) or {}
    return {
        "ts": time.time(),
        "power_w": _num(idev.get("power")),
        "temp_c": _num(idev.get("temperature")),
        "hbm_used_mb": (float(mem["used_size"]) / 2**20) if "used_size" in mem else None,
        "hbm_total_mb": (float(mem["total_size"]) / 2**20) if "total_size" in mem else None,
        "pe_count": len(pes) or None,
        "pe_util_mean_pct": (sum(pes) / len(pes)) if pes else None,
        "_info": idev,
    }


class Sampler:
    """Background ``furiosa-smi`` sampler (~0.25 s period)."""

    def __init__(self, device: str, interval: float = 0.25):
        self.device = device
        self.interval = interval
        self.samples: list[dict[str, Any]] = []
        self._stop = threading.Event()
        self._t: threading.Thread | None = None

    def __enter__(self) -> "Sampler":
        self.samples = []
        self._stop.clear()
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()
        return self

    def _loop(self) -> None:
        while not self._stop.is_set():
            s = smi_snapshot(self.device)
            if s:
                s.pop("_info", None)
                self.samples.append(s)
            self._stop.wait(self.interval)

    def __exit__(self, *exc: Any) -> None:
        self._stop.set()
        if self._t:
            self._t.join(timeout=10)

    def summary(self) -> dict[str, Any]:
        p = [s["power_w"] for s in self.samples if s.get("power_w") is not None]
        t = [s["temp_c"] for s in self.samples if s.get("temp_c") is not None]
        h = [s["hbm_used_mb"] for s in self.samples if s.get("hbm_used_mb") is not None]
        u = [s["pe_util_mean_pct"] for s in self.samples if s.get("pe_util_mean_pct") is not None]
        return {
            "power_samples": len(p),
            "avg_power_w": _r(_mean(p)),
            "peak_power_w": _r(max(p)) if p else None,
            "peak_temp_c": _r(max(t)) if t else None,
            "peak_hbm_used_mb": _r(max(h), 1) if h else None,
            "avg_pe_util_pct": _r(_mean(u)),
        }


def idle_baseline(device: str, seconds: float = 5.0) -> dict[str, Any]:
    with Sampler(device, 0.5) as s:
        time.sleep(seconds)
    out = s.summary()
    return {"idle_power_w": out["avg_power_w"], "idle_temp_c": out["peak_temp_c"],
            "samples": out["power_samples"]}


# --------------------------------------------------------------------------- #
# Prompt construction: distinct random token sequences (no prefix reuse)
# --------------------------------------------------------------------------- #
class TokenSource:
    def __init__(self, seed: int, lo: int = 1000, hi: int = 30000):
        self.rng = random.Random(seed)
        self.lo, self.hi = lo, hi

    def seq(self, n: int) -> list[int]:
        return [self.rng.randrange(self.lo, self.hi) for _ in range(n)]


# --------------------------------------------------------------------------- #
# Engine construction
# --------------------------------------------------------------------------- #
def build_llm(model_id: str, *, overlap: bool, npu_queue_limit: int | None,
              extra: dict[str, Any] | None = None):
    from furiosa_llm import LLM
    from furiosa_llm.metadata.config_types import (
        PrefixCacheConfig,
        SchedulerConfig,
        SchedulingLoop,
    )

    sc_kwargs: dict[str, Any] = {
        "scheduling_loop_type": SchedulingLoop.OVERLAP if overlap else SchedulingLoop.EAGER,
        "prefix_cache_config": PrefixCacheConfig(enabled=False),
    }
    if npu_queue_limit is not None:
        sc_kwargs["npu_queue_limit"] = npu_queue_limit
    sc = SchedulerConfig(**sc_kwargs)
    t0 = time.perf_counter()
    llm = LLM(model_id, scheduler_config=sc, **(extra or {}))
    load_ms = (time.perf_counter() - t0) * 1000.0
    flags = {
        "enable_overlap_scheduling": bool(overlap),
        "enable_prefix_caching": False,
        "npu_queue_limit": sc.npu_queue_limit,
        "batch_scheduling_budget_ms": sc.batch_scheduling_budget_ms,
        "experimental_enable_npu_sampling": bool(sc.enable_npu_sampling),
        "scheduler_config_repr": repr(sc),
    }
    return llm, load_ms, flags


# --------------------------------------------------------------------------- #
# Generative measurements
# --------------------------------------------------------------------------- #
async def _one_request(engine, prompt: dict[str, Any], osl: int, req_id: str,
                       timeout: float) -> dict[str, Any]:
    from furiosa_llm import SamplingParams

    sp = SamplingParams(max_tokens=osl, min_tokens=osl, ignore_eos=True, temperature=0.0)
    t0 = time.perf_counter()
    t_first = None
    t_prev = None
    n = 0
    itls: list[float] = []
    prompt_len = None

    async def _consume() -> None:
        nonlocal t_first, t_prev, n, prompt_len
        async for out in engine.generate(prompt, sp, request_id=req_id):
            now = time.perf_counter()
            if prompt_len is None and getattr(out, "prompt_token_ids", None) is not None:
                prompt_len = len(out.prompt_token_ids)
            cur = len(out.outputs[0].token_ids)
            if cur > n:
                if t_first is None:
                    t_first = now
                elif t_prev is not None:
                    step = (now - t_prev) * 1000.0 / (cur - n)
                    itls.extend([step] * (cur - n))
                t_prev = now
                n = cur

    await asyncio.wait_for(_consume(), timeout=timeout)
    t1 = time.perf_counter()
    ttft = ((t_first or t1) - t0) * 1000.0
    dec_s = t1 - (t_first or t0)
    tpot = (dec_s * 1000.0 / (n - 1)) if n > 1 else None
    return {
        "ttft_ms": ttft,
        "e2e_ms": (t1 - t0) * 1000.0,
        "output_tokens": n,
        "prompt_tokens": prompt_len,
        "tpot_ms": tpot,
        "decode_tps": ((n - 1) / dec_s) if n > 1 and dec_s > 0 else None,
        "itls_ms": itls,
        "t_start": t0,
        "t_end": t1,
    }


async def single_stream_shape(engine, toks: TokenSource, isl: int, osl: int, runs: int,
                              warmup: int, device: str, timeout: float) -> dict[str, Any]:
    for w in range(warmup):
        await _one_request(engine, {"prompt_token_ids": toks.seq(isl)}, osl,
                           f"ss-w-{isl}-{osl}-{w}-{time.time_ns()}", timeout)
    recs = []
    with Sampler(device) as s:
        for i in range(runs):
            recs.append(await _one_request(engine, {"prompt_token_ids": toks.seq(isl)}, osl,
                                           f"ss-{isl}-{osl}-{i}-{time.time_ns()}", timeout))
    tel = s.summary()
    ttft = [r["ttft_ms"] for r in recs]
    tpot = [r["tpot_ms"] for r in recs if r["tpot_ms"] is not None]
    dtps = [r["decode_tps"] for r in recs if r["decode_tps"] is not None]
    e2e = [r["e2e_ms"] for r in recs]
    itls = [x for r in recs for x in r["itls_ms"]]
    dmean = _mean(dtps)
    return {
        "input_tokens": isl,
        "output_tokens": osl,
        "concurrency": 1,
        "runs": runs,
        "warmup_runs": warmup,
        "ttft_mean_ms": _r(_mean(ttft)),
        "ttft_p50_ms": _r(_pct(ttft, 0.5)),
        "ttft_min_ms": _r(min(ttft)),
        "ttft_max_ms": _r(max(ttft)),
        "ttft_stddev_ms": _r(_std(ttft), 3),
        "tpot_mean_ms": _r(_mean(tpot), 3),
        "tpot_p50_ms": _r(_pct(tpot, 0.5), 3),
        "itl_samples": len(itls),
        "itl_p50_ms": _r(_pct(itls, 0.5), 3),
        "itl_p90_ms": _r(_pct(itls, 0.9), 3),
        "itl_p99_ms": _r(_pct(itls, 0.99), 3),
        "itl_max_ms": _r(max(itls), 3) if itls else None,
        "prefill_tps_mean": _r(_mean([isl * 1000.0 / t for t in ttft if t > 0]), 1),
        "decode_tps_mean": _r(dmean),
        "decode_tps_min": _r(min(dtps)) if dtps else None,
        "decode_tps_max": _r(max(dtps)) if dtps else None,
        "decode_tps_stddev": _r(_std(dtps), 3),
        "e2e_mean_ms": _r(_mean(e2e)),
        "e2e_p50_ms": _r(_pct(e2e, 0.5)),
        "e2e_min_ms": _r(min(e2e)),
        "e2e_max_ms": _r(max(e2e)),
        "e2e_stddev_ms": _r(_std(e2e), 3),
        **tel,
        "efficiency_tok_s_per_w": _r(dmean / tel["avg_power_w"], 3)
        if dmean and tel.get("avg_power_w") else None,
        "per_run": [
            {k: _r(v, 3) if isinstance(v, float) else v for k, v in r.items()
             if k not in ("itls_ms", "t_start", "t_end")}
            for r in recs
        ],
    }


async def concurrency_point(engine, toks: TokenSource, c: int, isl: int, osl: int,
                            runs: int, device: str, timeout: float, slo: float,
                            prompt_factory=None, label: str = "text") -> dict[str, Any]:
    per_run = []
    all_reqs: list[dict[str, Any]] = []
    with Sampler(device) as s:
        for i in range(runs):
            prompts = [
                prompt_factory(k) if prompt_factory else {"prompt_token_ids": toks.seq(isl)}
                for k in range(c)
            ]
            w0 = time.perf_counter()
            reqs = await asyncio.gather(*[
                _one_request(engine, prompts[k], osl, f"c{c}-r{i}-{k}-{time.time_ns()}", timeout)
                for k in range(c)
            ])
            wall = time.perf_counter() - w0
            out_toks = sum(r["output_tokens"] for r in reqs)
            per_run.append({
                "run": i + 1,
                "wall_s": _r(wall, 3),
                "output_tokens": out_toks,
                "aggregate_output_tps": _r(out_toks / wall),
                "aggregate_total_tps": _r((out_toks + sum((r["prompt_tokens"] or isl) for r in reqs)) / wall),
            })
            all_reqs.extend(reqs)
    tel = s.summary()
    ttft = [r["ttft_ms"] for r in all_reqs]
    tpot = [r["tpot_ms"] for r in all_reqs if r["tpot_ms"] is not None]
    user_tps = [r["decode_tps"] for r in all_reqs if r["decode_tps"] is not None]
    agg = _mean([p["aggregate_output_tps"] for p in per_run])
    ptoks = [r["prompt_tokens"] for r in all_reqs if r["prompt_tokens"] is not None]
    mean_user = _mean(user_tps)
    return {
        "concurrency": c,
        "input_tokens": isl,
        "prompt_tokens_observed_mean": _r(_mean(ptoks), 1) if ptoks else None,
        "output_tokens": osl,
        "modality": label,
        "runs": runs,
        "aggregate_output_tps": _r(agg),
        "aggregate_output_tps_min": _r(min(p["aggregate_output_tps"] for p in per_run)),
        "aggregate_output_tps_max": _r(max(p["aggregate_output_tps"] for p in per_run)),
        "ttft_mean_ms": _r(_mean(ttft)),
        "ttft_p50_ms": _r(_pct(ttft, 0.5)),
        "ttft_p90_ms": _r(_pct(ttft, 0.9)),
        "ttft_p99_ms": _r(_pct(ttft, 0.99)),
        "tpot_mean_ms": _r(_mean(tpot), 3),
        "tpot_p50_ms": _r(_pct(tpot, 0.5), 3),
        "tpot_p90_ms": _r(_pct(tpot, 0.9), 3),
        "per_user_decode_tps_mean": _r(mean_user),
        "per_user_decode_tps_p10": _r(_pct(user_tps, 0.1)),
        "slo_tok_s_per_user": slo,
        "meets_slo": bool(mean_user is not None and mean_user >= slo),
        **tel,
        "efficiency_tok_s_per_w": _r(agg / tel["avg_power_w"], 3)
        if agg and tel.get("avg_power_w") else None,
        "per_run": per_run,
    }


def capacity_at_slo(sweep: list[dict[str, Any]], slo: float) -> dict[str, Any]:
    ok = [p for p in sweep if p.get("meets_slo") and not p.get("error")]
    valid = [p for p in sweep if p.get("aggregate_output_tps") and not p.get("error")]
    best = max(ok, key=lambda p: p["concurrency"]) if ok else None
    peak = max(valid, key=lambda p: p["aggregate_output_tps"]) if valid else None
    return {
        "slo_tok_s_per_user": slo,
        "max_concurrency_meeting_slo": best["concurrency"] if best else None,
        "aggregate_output_tps_at_slo": best["aggregate_output_tps"] if best else None,
        "power_w_at_slo": best.get("avg_power_w") if best else None,
        "peak_aggregate_output_tps": peak["aggregate_output_tps"] if peak else None,
        "peak_concurrency": peak["concurrency"] if peak else None,
        "peak_power_w": peak.get("avg_power_w") if peak else None,
        "peak_efficiency_tok_s_per_w": peak.get("efficiency_tok_s_per_w") if peak else None,
        "concurrency_evaluated": [p["concurrency"] for p in sweep],
    }


def _vlm_prompt(img_px: int, text: str = "Describe this image in detail."):
    from PIL import Image

    rng = random.Random(img_px * 7919 + time.time_ns() % 100000)
    img = Image.new("RGB", (img_px, img_px),
                    color=(rng.randrange(256), rng.randrange(256), rng.randrange(256)))
    return {
        "prompt": "<|im_start|>user\n<|vision_start|><|image_pad|><|vision_end|>"
                  f"{text}<|im_end|>\n<|im_start|>assistant\n",
        "multi_modal_data": {"image": img},
    }


async def run_generative(args, result: dict[str, Any]) -> None:
    from furiosa_llm import AsyncLLMEngine

    llm, load_ms, flags = build_llm(args.model, overlap=not args.no_overlap,
                                    npu_queue_limit=args.npu_queue_limit)
    result["runtime"]["flags"] = flags
    result["load_time_ms"] = _r(load_ms)
    engine = AsyncLLMEngine.from_llm(llm)
    max_len = None
    for attr in ("max_model_len", "max_seq_len"):
        max_len = max_len or getattr(llm, attr, None)
    result["model"]["max_model_len_reported"] = max_len
    toks = TokenSource(args.seed)
    slo = args.slo

    grid = [tuple(map(int, s.split("/"))) for s in args.grid.split(",")] if args.grid else DEFAULT_GRID
    matrix = []
    for isl, osl in grid:
        if max_len and isl + osl > max_len:
            matrix.append({"input_tokens": isl, "output_tokens": osl,
                           "error": f"exceeds max_model_len={max_len}"})
            continue
        print(f"[grid] {isl}/{osl}", flush=True)
        try:
            row = await single_stream_shape(engine, toks, isl, osl, args.runs, args.warmup,
                                            args.device, args.timeout)
            print(f"  ttft={row['ttft_mean_ms']} ms tpot={row['tpot_mean_ms']} ms "
                  f"decode={row['decode_tps_mean']} tok/s pwr={row['avg_power_w']} W", flush=True)
        except Exception as e:  # noqa: BLE001
            row = {"input_tokens": isl, "output_tokens": osl, "error": repr(e)[:300]}
            print(f"  ERROR {e!r}", flush=True)
        matrix.append(row)
        _checkpoint(args, result)
    result["single_stream_isl_osl_matrix"] = matrix

    conc = [int(x) for x in args.concurrency.split(",")] if args.concurrency else DEFAULT_CONCURRENCY
    sweep = []
    # warm the batch path once
    try:
        await concurrency_point(engine, toks, 8, args.conc_isl, 64, 1, args.device, args.timeout, slo)
    except Exception:  # noqa: BLE001
        pass
    for c in conc:
        print(f"[conc] C={c} {args.conc_isl}/{args.conc_osl}", flush=True)
        try:
            pt = await concurrency_point(engine, toks, c, args.conc_isl, args.conc_osl,
                                         args.conc_runs, args.device, args.timeout * 4, slo)
            print(f"  agg={pt['aggregate_output_tps']} tok/s user={pt['per_user_decode_tps_mean']} "
                  f"ttft={pt['ttft_mean_ms']} tpot={pt['tpot_mean_ms']} pwr={pt['avg_power_w']} W",
                  flush=True)
        except Exception as e:  # noqa: BLE001
            pt = {"concurrency": c, "input_tokens": args.conc_isl, "output_tokens": args.conc_osl,
                  "error": repr(e)[:300]}
            print(f"  ERROR {e!r}", flush=True)
        sweep.append(pt)
        result["concurrency_scaling_sweep"] = sweep
        _checkpoint(args, result)
        if pt.get("error"):
            break
    result["capacity"] = capacity_at_slo(sweep, slo)

    if args.task == "vlm":
        vis = []
        for px in DEFAULT_IMAGE_RES:
            for c in DEFAULT_IMAGE_CONC:
                print(f"[image] {px}x{px} C={c}", flush=True)
                try:
                    pt = await concurrency_point(
                        engine, toks, c, 0, args.image_osl, args.runs if c == 1 else args.conc_runs,
                        args.device, args.timeout, slo,
                        prompt_factory=lambda k, px=px: _vlm_prompt(px), label="image")
                    pt["resolution"] = f"{px}x{px}"
                    print(f"  prompt_tokens={pt['prompt_tokens_observed_mean']} ttft={pt['ttft_mean_ms']} "
                          f"user={pt['per_user_decode_tps_mean']} agg={pt['aggregate_output_tps']}",
                          flush=True)
                except Exception as e:  # noqa: BLE001
                    pt = {"resolution": f"{px}x{px}", "concurrency": c, "modality": "image",
                          "output_tokens": args.image_osl, "error": repr(e)[:300]}
                    print(f"  ERROR {e!r}", flush=True)
                vis.append(pt)
                result["vision_resolution_sweep"] = vis
                _checkpoint(args, result)
                if pt.get("error"):
                    break
    try:
        engine.shutdown() if hasattr(engine, "shutdown") else None
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------- #
# Pooling (embedding / reranker) measurements
# --------------------------------------------------------------------------- #
def run_pooling(args, result: dict[str, Any]) -> None:
    llm, load_ms, flags = build_llm(args.model, overlap=False, npu_queue_limit=args.npu_queue_limit)
    flags["note"] = "overlap scheduling is not supported for pooling models; eager loop used"
    result["runtime"]["flags"] = flags
    result["load_time_ms"] = _r(load_ms)
    toks = TokenSource(args.seed)
    seqs = [int(x) for x in args.pool_seq.split(",")] if args.pool_seq else DEFAULT_POOL_SEQ
    batches = [int(x) for x in args.pool_batch.split(",")] if args.pool_batch else DEFAULT_POOL_BATCH
    is_score = args.task == "score"
    q_len = 32

    def _call(seq_len: int, bs: int) -> None:
        if is_score:
            q = {"prompt_token_ids": toks.seq(q_len)}
            docs = [{"prompt_token_ids": toks.seq(seq_len - q_len)} for _ in range(bs)]
            llm.score(q, docs)
        else:
            llm.embed([{"prompt_token_ids": toks.seq(seq_len)} for _ in range(bs)])

    try:
        _call(seqs[0], 1)
        _call(seqs[0], 1)
    except Exception as e:  # noqa: BLE001
        result["errors"].append(f"warmup failed: {e!r}"[:300])

    rows = []
    for seq_len in seqs:
        for bs in batches:
            print(f"[pool] seq={seq_len} batch={bs}", flush=True)
            lat = []
            try:
                _call(seq_len, bs)  # per-shape warm-up
                with Sampler(args.device) as s:
                    for _ in range(args.pool_runs):
                        t0 = time.perf_counter()
                        _call(seq_len, bs)
                        lat.append((time.perf_counter() - t0) * 1000.0)
                tel = s.summary()
                m = _mean(lat)
                row = {
                    "seq_len": seq_len,
                    "input_tokens_per_item": seq_len,
                    "query_tokens": q_len if is_score else None,
                    "batch_size": bs,
                    "runs": args.pool_runs,
                    "warmup_runs": 1,
                    "latency_mean_ms": _r(m),
                    "latency_p50_ms": _r(_pct(lat, 0.5)),
                    "latency_min_ms": _r(min(lat)),
                    "latency_max_ms": _r(max(lat)),
                    "latency_stddev_ms": _r(_std(lat), 3),
                    "single_request_latency_ms": _r(m) if bs == 1 else None,
                    "requests_per_second": _r(bs * 1000.0 / m),
                    "tokens_per_second": _r(bs * seq_len * 1000.0 / m, 1),
                    **tel,
                }
                row["efficiency_tok_s_per_w"] = (
                    _r(row["tokens_per_second"] / tel["avg_power_w"], 2) if tel.get("avg_power_w") else None
                )
                print(f"  lat={row['latency_mean_ms']} ms tok/s={row['tokens_per_second']} "
                      f"pwr={row['avg_power_w']} W", flush=True)
            except Exception as e:  # noqa: BLE001
                row = {"seq_len": seq_len, "batch_size": bs, "error": repr(e)[:300]}
                print(f"  ERROR {e!r}", flush=True)
            rows.append(row)
            result["pooling_batch_sweep"] = rows
            _checkpoint(args, result)
            if row.get("error"):
                break


# --------------------------------------------------------------------------- #
# Result document
# --------------------------------------------------------------------------- #
def _model_meta(model_id: str) -> dict[str, Any]:
    hf_home = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    snaps = sorted((hf_home / "hub" / ("models--" + model_id.replace("/", "--")) / "snapshots").glob("*"))
    meta: dict[str, Any] = {"id": model_id, "name": model_id.split("/")[-1]}
    if not snaps:
        return meta
    snap = snaps[-1]
    meta["revision"] = snap.name
    cfg = snap / "config.json"
    if cfg.exists():
        try:
            c = json.loads(cfg.read_text(encoding="utf-8"))
            meta["architecture"] = (c.get("architectures") or [None])[0]
            meta["family"] = c.get("model_type")
            meta["torch_dtype"] = c.get("torch_dtype") or (c.get("text_config") or {}).get("torch_dtype")
            q = c.get("quantization_config") or {}
            meta["quantization"] = q.get("quant_method") or q.get("format") or meta.get("torch_dtype")
            meta["max_position_embeddings"] = c.get("max_position_embeddings") or (
                c.get("text_config") or {}).get("max_position_embeddings")
        except (OSError, ValueError):
            pass
    fxbs = sorted(snap.glob("*.fxb"))
    if fxbs:
        f = fxbs[0]
        h = hashlib.sha256()
        try:
            with f.resolve().open("rb") as fh:
                for chunk in iter(lambda: fh.read(16 * 2**20), b""):
                    h.update(chunk)
            meta["checksum"] = "sha256:" + h.hexdigest()
        except OSError:
            meta["checksum"] = None
        meta["artifact_file"] = f.name
        meta["format"] = "fxb"
    return meta


def _system_info(device: str) -> dict[str, Any]:
    cpu = None
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    ram_gb = None
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                ram_gb = round(int(line.split()[1]) / 2**20, 1)
    except OSError:
        pass
    snap = smi_snapshot(device) or {}
    info = snap.get("_info", {})
    return {
        "os": platform.system(),
        "os_version": platform.release(),
        "cpu": cpu,
        "cpu_cores_logical": os.cpu_count(),
        "ram_gb": ram_gb,
        "device_type": "npu",
        "npu": {
            "arch": info.get("arch"),
            "device_name": info.get("dev_name", device),
            "firmware": info.get("firmware"),
            "power_limit_reported": info.get("power_limit"),
            "governor": info.get("governor"),
            "processing_elements": snap.get("pe_count"),
            "memory_total_mb": _r(snap.get("hbm_total_mb"), 0),
            "telemetry_tool": "furiosa-smi",
        },
    }


def _runtime_version() -> str | None:
    try:
        from importlib.metadata import version

        return version("furiosa-llm")
    except Exception:  # noqa: BLE001
        return None


def _checkpoint(args, result: dict[str, Any]) -> None:
    Path(args.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


def _canonical_metrics(result: dict[str, Any], canon: tuple[int, int]) -> dict[str, Any]:
    """Populate canonical aihwbench metric keys from the canonical shape only."""
    m: dict[str, Any] = {}
    row = next((r for r in result.get("single_stream_isl_osl_matrix", [])
                if (r.get("input_tokens"), r.get("output_tokens")) == canon and not r.get("error")), None)
    idle = result.get("idle", {}).get("idle_power_w")
    if row:
        e2e = [p["e2e_ms"] for p in row.get("per_run", [])]
        m.update({
            "ttft_ms": row["ttft_mean_ms"],
            "ttft_stddev_ms": row["ttft_stddev_ms"],
            "tpot_ms": row["tpot_mean_ms"],
            "itl_ms": row["tpot_mean_ms"],
            "itl_p50_ms": row["itl_p50_ms"],
            "itl_p90_ms": row["itl_p90_ms"],
            "itl_p99_ms": row["itl_p99_ms"],
            "itl_max_ms": row["itl_max_ms"],
            "inter_token_samples": row["itl_samples"],
            "prompt_tokens_per_second": row["prefill_tps_mean"],
            "prefill_latency_ms": row["ttft_mean_ms"],
            "generation_tokens_per_second": row["decode_tps_mean"],
            "generation_tps_stddev": row["decode_tps_stddev"],
            "gen_tps_min": row["decode_tps_min"],
            "gen_tps_max": row["decode_tps_max"],
            "total_latency_ms": row["e2e_mean_ms"],
            "median_latency_ms": row["e2e_p50_ms"],
            "p50_latency_ms": row["e2e_p50_ms"],
            "min_latency_ms": row["e2e_min_ms"],
            "max_latency_ms": row["e2e_max_ms"],
            "stddev_latency_ms": row["e2e_stddev_ms"],
            "decode_duration_ms": _r(row["e2e_mean_ms"] - row["ttft_mean_ms"]) if row["e2e_mean_ms"] else None,
            "average_power_watts": row["avg_power_w"],
            "max_temperature_c": row["peak_temp_c"],
            "peak_vram_mb": row["peak_hbm_used_mb"],
            "avg_gpu_util_percent": row["avg_pe_util_pct"],
            "performance_per_watt": row["efficiency_tok_s_per_w"],
            "energy_joules_per_token": _r(row["avg_power_w"] / row["decode_tps_mean"], 4)
            if row["avg_power_w"] and row["decode_tps_mean"] else None,
            "throughput_inferences_per_second": _r(1000.0 / row["e2e_mean_ms"], 4) if row["e2e_mean_ms"] else None,
            "requests_per_second": _r(1000.0 / row["e2e_mean_ms"], 4) if row["e2e_mean_ms"] else None,
            "error_rate": 0.0,
        })
        if m.get("energy_joules_per_token"):
            m["energy_joules_per_1k_tokens"] = _r(m["energy_joules_per_token"] * 1000.0, 2)
        if row["avg_power_w"] and row["e2e_mean_ms"]:
            m["energy_joules_per_request"] = _r(row["avg_power_w"] * row["e2e_mean_ms"] / 1000.0, 2)
        if e2e and len(e2e) >= 2 and row["e2e_mean_ms"]:
            m["cv_latency"] = _r(row["e2e_stddev_ms"] / row["e2e_mean_ms"], 4)
    pool = [r for r in result.get("pooling_batch_sweep", []) if not r.get("error")]
    if pool and not row:
        b1 = next((r for r in pool if r["batch_size"] == 1), None)
        best = max(pool, key=lambda r: r["tokens_per_second"])
        m.update({
            "total_latency_ms": b1["latency_mean_ms"] if b1 else None,
            "p50_latency_ms": b1["latency_p50_ms"] if b1 else None,
            "throughput_inferences_per_second": best["requests_per_second"],
            "requests_per_second": best["requests_per_second"],
            "prompt_tokens_per_second": best["tokens_per_second"],
            "average_power_watts": best["avg_power_w"],
            "max_temperature_c": max((r["peak_temp_c"] for r in pool if r.get("peak_temp_c")), default=None),
            "peak_vram_mb": max((r["peak_hbm_used_mb"] for r in pool if r.get("peak_hbm_used_mb")), default=None),
            "error_rate": 0.0,
        })
    if idle is not None:
        m["idle_power_watts"] = idle
        if m.get("average_power_watts"):
            m["incremental_power_watts"] = _r(m["average_power_watts"] - idle)
    m["load_time_ms"] = result.get("load_time_ms")
    return {k: v for k, v in m.items() if v is not None}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model", required=True)
    ap.add_argument("--task", choices=["generate", "vlm", "embed", "score"], required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--vendor", default="furiosaai")
    ap.add_argument("--device", default="npu1")
    ap.add_argument("--sdk-channel", default="release", help="release | beta (beta results are labelled)")
    ap.add_argument("--no-overlap", action="store_true", help="disable overlap scheduling (not recommended)")
    ap.add_argument("--npu-queue-limit", type=int, default=None)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--warmup", type=int, default=1)
    ap.add_argument("--grid", default=None, help="comma list ISL/OSL, e.g. 128/128,1024/1024")
    ap.add_argument("--canonical", default="1024/1024")
    ap.add_argument("--concurrency", default=None)
    ap.add_argument("--conc-isl", type=int, default=1024)
    ap.add_argument("--conc-osl", type=int, default=1024)
    ap.add_argument("--conc-runs", type=int, default=2)
    ap.add_argument("--image-osl", type=int, default=1024)
    ap.add_argument("--slo", type=float, default=40.0, help="per-user decode tok/s SLO")
    ap.add_argument("--pool-seq", default=None)
    ap.add_argument("--pool-batch", default=None)
    ap.add_argument("--pool-runs", type=int, default=5)
    ap.add_argument("--timeout", type=float, default=600.0)
    ap.add_argument("--seed", type=int, default=20261021)
    ap.add_argument("--note", action="append", default=[], help="free-text note recorded in the result")
    args = ap.parse_args()

    slug = args.model.split("/")[-1].lower()
    try:
        from huggingface_hub import snapshot_download
        print(f"[prep] Ensuring model artifacts are present for {args.model}...", flush=True)
        snapshot_download(args.model)
    except Exception as e:
        print(f"[warn] snapshot_download for {args.model}: {e}", flush=True)

    canon = tuple(int(x) for x in args.canonical.split("/"))
    result: dict[str, Any] = {
        "schema_version": "2.1",
        "vendor_eval_version": "1",
        "runner": {"name": "aihwbench.vendor_eval.furiosa_llm_runner", "version": RUNNER_VERSION,
                   "argv": sys.argv[1:]},
        "run_id": f"{args.vendor}-{slug}-{args.sdk_channel}",
        "timestamp": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "vendor": args.vendor,
        "task": args.task,
        "system": _system_info(args.device),
        "runtime": {"name": "furiosa-llm", "backend": "furiosa_llm", "version": _runtime_version(),
                    "sdk_channel": args.sdk_channel, "device": "npu"},
        "model": _model_meta(args.model),
        "workload": {
            "suite": "vendor-eval",
            "input_tokens": canon[0] if args.task in ("generate", "vlm") else None,
            "output_tokens": canon[1] if args.task in ("generate", "vlm") else None,
            "measured_runs": args.runs if args.task in ("generate", "vlm") else args.pool_runs,
            "warmup_runs": args.warmup if args.task in ("generate", "vlm") else 1,
            "concurrency_runs": args.conc_runs if args.task in ("generate", "vlm") else None,
            "temperature": 0.0,
            "ignore_eos": True,
            "prompt_source": "distinct random token ids per request (no shared prefixes)",
            "slo_tok_s_per_user": args.slo,
        },
        "power_methodology": "total accelerator power from furiosa-smi sampled every ~0.25 s during measured runs; "
                             "efficiency = output tok/s / average accelerator W (no idle subtraction)",
        "notes": args.note,
        "errors": [],
    }
    result["idle"] = idle_baseline(args.device)
    _checkpoint(args, result)
    try:
        if args.task in ("generate", "vlm"):
            asyncio.run(run_generative(args, result))
        else:
            run_pooling(args, result)
    except Exception as e:  # noqa: BLE001
        result["errors"].append(traceback.format_exc()[-2000:])
        print(f"FATAL {e!r}", flush=True)
    result["model"].update({k: v for k, v in _model_meta(args.model).items() if k not in result["model"]})
    result["metrics"] = _canonical_metrics(result, canon)
    _checkpoint(args, result)
    print(f"[done] wrote {args.out}", flush=True)
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
