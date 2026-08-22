"""Load generator for capacity and serving-style benchmarking.

Implements deterministic request-arrival patterns (#7):

- ``closed_loop``   — a fixed pool of workers; each submits the next
                      request as soon as it finishes (no open queue).
- ``constant_rate`` — evenly spaced arrivals at a fixed requests/second.
- ``poisson``       — memoryless exponential inter-arrivals.
- ``gamma``         — burstier/smoothed arrivals via Gamma inter-arrivals.
- ``burst``         — bursts of N requests every interval.

All randomness is seeded; identical configs produce identical arrival
sequences on any machine. The scheduler drives a caller-provided
``execute`` callable (the runtime adapter) and records per-request timing:
submit time, start time, end time, queue latency, and success.

Queue latency, request latency, and error rate are *measured* here; they
are never inferred from other metrics.
"""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "LoadgenConfig",
    "RequestRecord",
    "Recorder",
    "generate_arrivals",
    "run_load",
    "PATTERNS",
]

PATTERNS = ("closed_loop", "constant_rate", "poisson", "gamma", "burst")


@dataclass(frozen=True)
class LoadgenConfig:
    """Deterministic load specification."""

    pattern: str = "closed_loop"
    concurrency: int = 1
    rate_per_second: float = 1.0
    requests: int | None = None  # total requests to submit
    duration_s: float | None = None  # alternative stop condition
    gamma_shape: float = 2.0
    burst_size: int = 10
    burst_interval_s: float = 1.0
    seed: int = 42

    def __post_init__(self) -> None:
        if self.pattern not in PATTERNS:
            raise ValueError(f"pattern must be one of {PATTERNS}, got {self.pattern!r}")
        if self.concurrency < 1:
            raise ValueError("concurrency must be >= 1")
        if self.rate_per_second <= 0:
            raise ValueError("rate_per_second must be > 0")
        if self.requests is None and self.duration_s is None:
            raise ValueError("set either requests or duration_s")
        if self.requests is not None and self.requests < 1:
            raise ValueError("requests must be >= 1")


@dataclass
class RequestRecord:
    """One measured request."""

    request_id: int
    submit_time: float
    start_time: float
    end_time: float
    success: bool
    result: dict[str, Any] = field(default_factory=dict)

    @property
    def queue_latency_ms(self) -> float:
        return (self.start_time - self.submit_time) * 1000.0

    @property
    def request_latency_ms(self) -> float:
        return (self.end_time - self.start_time) * 1000.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "submit_time": self.submit_time,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "queue_latency_ms": self.queue_latency_ms,
            "request_latency_ms": self.request_latency_ms,
            "success": self.success,
            "result": self.result,
        }


class Recorder:
    """Thread-safe collector of RequestRecords."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: list[RequestRecord] = []

    def add(self, record: RequestRecord) -> None:
        with self._lock:
            self._records.append(record)

    @property
    def records(self) -> list[RequestRecord]:
        with self._lock:
            return list(self._records)


def generate_arrivals(config: LoadgenConfig) -> Iterator[float]:
    """Yield absolute submit times (seconds since call) for open patterns."""
    rng = random.Random(f"aihwbench-loadgen-{config.pattern}-{config.seed}")
    t = 0.0
    count = 0
    limit_requests = config.requests
    limit_duration = config.duration_s
    while True:
        if limit_requests is not None and count >= limit_requests:
            return
        if limit_duration is not None and t > limit_duration:
            return
        yield t
        count += 1
        if config.pattern == "constant_rate":
            t += 1.0 / config.rate_per_second
        elif config.pattern == "poisson":
            t += rng.expovariate(config.rate_per_second)
        elif config.pattern == "gamma":
            # Gamma(shape, scale=1/rate): shape>1 smooths, shape<1 bursts.
            t += rng.gammavariate(config.gamma_shape, 1.0 / config.rate_per_second)
        elif config.pattern == "burst":
            position_in_burst = count % config.burst_size
            if position_in_burst == 0 and count > 0:
                t += config.burst_interval_s
            else:
                t += 0.001  # tiny spacing inside a burst


def run_load(
    config: LoadgenConfig,
    execute: Callable[[int], dict[str, Any]],
) -> list[RequestRecord]:
    """Drive ``execute(request_id)`` under the configured load pattern.

    ``execute`` is called from worker threads and must be thread-safe. It
    returns an arbitrary dict of measured details (tokens, ttft_ms, ...).
    Exceptions are recorded as failed requests, never propagated mid-run.
    """
    recorder = Recorder()
    lock = threading.Lock()
    next_id = 0

    origin = time.perf_counter()

    def _worker() -> None:
        nonlocal next_id
        while True:
            with lock:
                if stop_event.is_set():
                    return
                if config.requests is not None and submitted[0] >= config.requests:
                    return
                if (
                    config.duration_s is not None
                    and time.perf_counter() - origin >= config.duration_s
                ):
                    return
                request_id = next_id
                next_id += 1
                submitted[0] += 1
            submit = time.perf_counter()
            start = submit  # closed-loop workers start immediately
            try:
                detail = execute(request_id)
                end = time.perf_counter()
                recorder.add(RequestRecord(request_id, submit, start, end, True, detail))
            except Exception as exc:  # noqa: BLE001 - record, don't crash the run
                end = time.perf_counter()
                recorder.add(
                    RequestRecord(request_id, submit, start, end, False, {"error": str(exc)})
                )

    submitted = [0]
    stop_event = threading.Event()

    if config.pattern == "closed_loop":
        threads = [threading.Thread(target=_worker, daemon=True) for _ in range(config.concurrency)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return recorder.records

    # Open patterns: schedule arrivals on a timeline with a worker pool.
    work_available = threading.Semaphore(0)
    pending: list[tuple[float, int]] = []  # (submit_at, request_id)
    pending_lock = threading.Lock()

    def _pool_worker() -> None:
        while True:
            work_available.acquire()
            if stop_event.is_set():
                return
            with pending_lock:
                if not pending:
                    continue
                _, request_id = pending.pop(0)
            start = time.perf_counter()
            try:
                detail = execute(request_id)
                end = time.perf_counter()
                recorder.add(RequestRecord(request_id, start, start, end, True, detail))
            except Exception as exc:  # noqa: BLE001
                end = time.perf_counter()
                recorder.add(
                    RequestRecord(request_id, start, start, end, False, {"error": str(exc)})
                )

    threads = [
        threading.Thread(target=_pool_worker, daemon=True) for _ in range(config.concurrency)
    ]
    for t in threads:
        t.start()

    origin = time.perf_counter()
    for submit_offset in generate_arrivals(config):
        delay = submit_offset - (time.perf_counter() - origin)
        if delay > 0:
            time.sleep(delay)
        with pending_lock:
            pending.append((origin + submit_offset, next_id))
            next_id += 1
        work_available.release()

    # Drain: wait until every submitted request has been recorded.
    total_submitted = next_id
    while True:
        with pending_lock:
            outstanding = len(pending)
        if outstanding == 0 and len(recorder.records) >= total_submitted:
            break
        time.sleep(0.005)
    stop_event.set()
    for _ in threads:
        work_available.release()
    for t in threads:
        t.join(timeout=5.0)
    return recorder.records
