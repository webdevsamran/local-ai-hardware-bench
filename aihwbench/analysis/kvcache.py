"""KV-cache quantization: what it costs in memory, not what it buys in speed.

Quantizing the KV cache is widely presented as a performance tuning knob. It
is not one. It is a *memory* feature, and the honest question it answers is
"how much context fits on this card", not "how many tokens per second".

The distinction is not pedantic, because the two framings recommend opposite
things. Measured as speed, a quantized cache usually looks like a small loss
and the advice is "leave it on f16". Measured as memory, the same setting is
what makes a long conversation possible at all -- and on hardware where the
alternative is spilling weights to system RAM, it is the difference between
usable and unusable.

So this module leads with bytes. Throughput appears, because pretending it is
unaffected would be its own dishonesty, but it appears with the noise floor
attached: on the reference machine two runs of an *identical* configuration
differed by 10%, so a 3% throughput difference between cache types is not a
finding.

Two numbers are computed here and they answer different questions:

- The **analytic** size, from the model's own attention geometry. Exact,
  needs no measurement, and is the number that scales to a context length
  nobody has run yet.
- The **measured** VRAM from a sweep. Real, but device-wide: `nvidia-smi`
  reports what the whole card holds, including the compositor and anything
  else resident. At short contexts the cache is a few megabytes and the
  measurement cannot resolve it; the report says so rather than presenting
  the difference between two noisy readings as a saving.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "KV_CACHE_BYTES_PER_ELEMENT",
    "kv_cache_bytes_per_token",
    "kv_cache_bytes",
    "context_for_budget",
    "analyze_kv_cache_matrix",
    "BASELINE_CACHE_TYPE",
    "BYTES_PER_MB",
    "NOISE_FLOOR_FRACTION",
]

#: Bytes per cached element for each dtype llama.cpp accepts.
#:
#: The quantized entries are ggml block formats, not plain bit widths: a block
#: of 32 values carries its own scale (and for the `_1` variants a minimum),
#: so the real cost is above the nominal bits. `q4_0` is 18 bytes per 32
#: values, not 16 -- treating it as a flat 0.5 bytes understates the cache by
#: 12%, which is exactly the sort of error that makes a capacity estimate say
#: a context fits when it does not.
KV_CACHE_BYTES_PER_ELEMENT: dict[str, float] = {
    "f16": 2.0,
    "bf16": 2.0,
    "q8_0": 34 / 32,  # 32 int8 + one f16 scale
    "q5_1": 24 / 32,  # 32 x 5-bit + f16 scale + f16 min
    "q5_0": 22 / 32,  # 32 x 5-bit + f16 scale
    "q4_1": 20 / 32,  # 32 x 4-bit + f16 scale + f16 min
    "q4_0": 18 / 32,  # 32 x 4-bit + f16 scale
}

#: Bytes in a megabyte, as this project means it everywhere.
#:
#: `peak_vram_mb` comes from `nvidia-smi memory.used`, which reports MiB, and
#: `telemetry` converts system RAM with the same divisor. Computing the
#: analytic cache size in decimal MB and then comparing it against a measured
#: MiB figure would make the two disagree by 4.9% for no reason -- enough to
#: turn an exact match into an apparent discrepancy.
BYTES_PER_MB = 1024 * 1024

#: The dtype everything is compared against: llama.cpp's default.
BASELINE_CACHE_TYPE = "f16"

#: Throughput differences smaller than this are reported as indistinguishable.
#:
#: Measured, not chosen: sweeping `gpu_layers` on the reference machine gave
#: 247.06 tok/s at 24 layers and 222.80 at 99 for a 24-layer model -- the same
#: configuration twice, 10% apart. Anything under that is the machine, not the
#: setting.
NOISE_FLOOR_FRACTION = 0.10


def kv_cache_bytes_per_token(
    geometry: dict[str, Any],
    cache_type_k: str = BASELINE_CACHE_TYPE,
    cache_type_v: str = BASELINE_CACHE_TYPE,
) -> int | None:
    """Bytes of KV cache one token occupies, from the model's own geometry.

    K and V are sized separately because llama.cpp lets them differ, and they
    tolerate quantization differently: the K cache is the more sensitive of
    the two, so `q8_0` for K with `q4_0` for V is a real configuration rather
    than a curiosity.

    Returns None when the header did not state the geometry. A cache size
    derived from a guess would be quoted as fact.
    """
    layers = geometry.get("block_count")
    heads_kv = geometry.get("head_count_kv")
    head_dim = geometry.get("head_dim")
    if not layers or not heads_kv or not head_dim:
        return None

    bytes_k = KV_CACHE_BYTES_PER_ELEMENT.get(cache_type_k.lower())
    bytes_v = KV_CACHE_BYTES_PER_ELEMENT.get(cache_type_v.lower())
    if bytes_k is None or bytes_v is None:
        return None

    elements_per_token = int(layers) * int(heads_kv) * int(head_dim)
    return int(round(elements_per_token * (bytes_k + bytes_v)))


def kv_cache_bytes(
    geometry: dict[str, Any],
    context_length: int,
    cache_type_k: str = BASELINE_CACHE_TYPE,
    cache_type_v: str = BASELINE_CACHE_TYPE,
) -> int | None:
    """Total KV cache for a context length. Grows linearly; that is the point."""
    per_token = kv_cache_bytes_per_token(geometry, cache_type_k, cache_type_v)
    if per_token is None or context_length <= 0:
        return None
    return per_token * context_length


def context_for_budget(
    geometry: dict[str, Any],
    budget_bytes: int,
    cache_type_k: str = BASELINE_CACHE_TYPE,
    cache_type_v: str = BASELINE_CACHE_TYPE,
) -> int | None:
    """How many tokens of context a VRAM budget holds.

    This is the question a quantized cache actually answers, and the one a
    tokens-per-second table cannot.
    """
    per_token = kv_cache_bytes_per_token(geometry, cache_type_k, cache_type_v)
    if per_token is None or per_token <= 0 or budget_bytes <= 0:
        return None
    return int(budget_bytes // per_token)


def _throughput(row: dict[str, Any]) -> float | None:
    value = (row.get("metrics") or {}).get("generation_tokens_per_second")
    return float(value) if isinstance(value, int | float) else None


def _vram(row: dict[str, Any]) -> float | None:
    value = (row.get("metrics") or {}).get("peak_vram_mb")
    return float(value) if isinstance(value, int | float) else None


def _cache_types(row: dict[str, Any]) -> tuple[str, str]:
    params = row.get("params") or {}
    return (
        str(params.get("cache_type_k") or BASELINE_CACHE_TYPE).lower(),
        str(params.get("cache_type_v") or BASELINE_CACHE_TYPE).lower(),
    )


def analyze_kv_cache_matrix(
    sweep: dict[str, Any],
    geometry: dict[str, Any] | None = None,
    context_length: int | None = None,
) -> dict[str, Any]:
    """Turn a sweep over KV-cache dtypes into a memory report.

    Every configuration is compared against f16/f16. The comparison is stated
    in both currencies -- analytic cache bytes and measured device VRAM -- and
    where they disagree the report says which one to believe and why.
    """
    rows = [r for r in (sweep.get("matrix") or []) if not r.get("error")]
    if not rows:
        return {
            "configurations": [],
            "baseline": None,
            "unresolved": "the sweep contains no successful runs",
        }

    params = rows[0].get("params") or {}
    if context_length is None:
        raw = params.get("context_length")
        context_length = int(raw) if isinstance(raw, int | float) else None

    baseline_row = next(
        (r for r in rows if _cache_types(r) == (BASELINE_CACHE_TYPE, BASELINE_CACHE_TYPE)),
        None,
    )
    baseline_vram = _vram(baseline_row) if baseline_row else None
    baseline_tps = _throughput(baseline_row) if baseline_row else None
    baseline_cache = (
        kv_cache_bytes(geometry, context_length, BASELINE_CACHE_TYPE, BASELINE_CACHE_TYPE)
        if geometry and context_length
        else None
    )

    configurations: list[dict[str, Any]] = []
    for row in rows:
        type_k, type_v = _cache_types(row)
        entry: dict[str, Any] = {
            "cache_type_k": type_k,
            "cache_type_v": type_v,
            "is_baseline": (type_k, type_v) == (BASELINE_CACHE_TYPE, BASELINE_CACHE_TYPE),
            "peak_vram_mb": _vram(row),
            "generation_tokens_per_second": _throughput(row),
            "run_id": row.get("run_id"),
        }

        cache_bytes = (
            kv_cache_bytes(geometry, context_length, type_k, type_v)
            if geometry and context_length
            else None
        )
        entry["kv_cache_mb"] = round(cache_bytes / BYTES_PER_MB, 2) if cache_bytes else None
        if cache_bytes is not None and baseline_cache:
            saved = baseline_cache - cache_bytes
            entry["kv_cache_saved_mb"] = round(saved / BYTES_PER_MB, 2)
            entry["kv_cache_saved_percent"] = round(100.0 * saved / baseline_cache, 1)

        measured_vram = entry["peak_vram_mb"]
        if measured_vram is not None and baseline_vram is not None:
            delta = baseline_vram - measured_vram
            entry["measured_vram_saved_mb"] = round(delta, 1)
            # Device-wide VRAM moves for reasons that have nothing to do with
            # the cache. Where the analytic saving is smaller than the jitter
            # in the reading, the measurement cannot see it, and reporting the
            # difference as a result would be reporting noise.
            expected = entry.get("kv_cache_saved_mb")
            # The inversion worth naming outright: a setting taken to save
            # memory that spends it instead. Measured on the reference machine,
            # quantizing K while leaving V at f16 cost 820 MiB *more* than
            # leaving both at f16, against a predicted saving of 90 MiB --
            # reproducibly, across two sweeps and a direct check.
            #
            # The cause was `--flash-attn auto`, which is the default and is
            # not a synonym for `on`: llama.cpp declined flash attention for
            # that dtype pair and the fallback path allocated the difference.
            # Forcing `-fa on` brought the same configuration to 902 MiB, below
            # the f16 baseline and in line with the cache arithmetic. So the
            # note points at the flag, because unlike the inversion itself that
            # is something the reader can act on.
            if delta < 0 and expected is not None and expected > 0:
                entry["costs_more_than_baseline"] = True
                flash = (row.get("params") or {}).get("flash_attn")
                entry["measurement_note"] = (
                    f"this configuration used {-delta:.0f} MB MORE than "
                    f"{BASELINE_CACHE_TYPE}/{BASELINE_CACHE_TYPE}, against a predicted "
                    f"saving of {expected:.0f} MB. The cache is smaller and the device "
                    "total is larger, so the cost is outside the cache."
                    + (
                        " This run left --flash-attn at its default, which is `auto`, "
                        "and auto is not `on`: on this machine the same dtype pair cost "
                        "940 MB more at `auto` than at `on`. Re-measure with "
                        "--flash-attn on before concluding anything about the dtypes."
                        if flash in (None, "auto")
                        else " Flash attention was already requested, so this is not the "
                        "usual cause and the configuration is simply worse here."
                    )
                )
            elif expected is not None and abs(delta) > 0 and expected < abs(delta) / 2:
                entry["measurement_note"] = (
                    f"device VRAM moved {delta:.1f} MB while the cache should have "
                    f"changed by {expected:.1f} MB: the difference is dominated by "
                    "something other than the KV cache"
                )

        tps = entry["generation_tokens_per_second"]
        if tps is not None and baseline_tps:
            change = (tps - baseline_tps) / baseline_tps
            entry["throughput_change_percent"] = round(100.0 * change, 1)
            entry["throughput_distinguishable"] = abs(change) > NOISE_FLOOR_FRACTION
            if not entry["throughput_distinguishable"]:
                entry["throughput_note"] = (
                    f"within the {NOISE_FLOOR_FRACTION:.0%} run-to-run noise floor: "
                    "indistinguishable from the baseline, not equal to it"
                )
        configurations.append(entry)

    configurations.sort(key=lambda c: (c["kv_cache_mb"] is None, c["kv_cache_mb"] or 0))

    return {
        "context_length": context_length,
        "geometry": geometry,
        "baseline": {
            "cache_type_k": BASELINE_CACHE_TYPE,
            "cache_type_v": BASELINE_CACHE_TYPE,
            "peak_vram_mb": baseline_vram,
            "generation_tokens_per_second": baseline_tps,
            "kv_cache_mb": round(baseline_cache / BYTES_PER_MB, 2) if baseline_cache else None,
        }
        if baseline_row
        else None,
        "configurations": configurations,
        "framing": (
            "KV-cache quantization is a memory setting. Read the cache-size "
            "column first: it is exact, it scales to context lengths nobody "
            "has measured, and it is what decides whether a conversation fits. "
            "Throughput is reported for completeness with its noise floor "
            "attached, and a difference inside that floor is not a difference."
        ),
        "unresolved": None
        if baseline_row
        else ("no f16/f16 run in this sweep, so there is nothing to compare against"),
    }
