"""Background telemetry sampling during benchmark runs.

Samples system RAM, CPU utilization, and GPU memory/utilization/
temperature/power while a benchmark executes. Metrics that cannot be
measured on the current platform are reported as None — never estimated.

Every sample carries explicit scope/source metadata so consumers can
tell system-wide measurements from per-process ones:

- RAM/CPU are SYSTEM-WIDE (scope ``system``).
- GPU metrics come from the first NVIDIA GPU reported by ``nvidia-smi``
  (scope ``device``) when that tool is present.
"""

from __future__ import annotations

import platform
import subprocess
import threading
import time
from collections.abc import Callable
from typing import Any

from .vendors import (
    battery_sample,
    parse_rapl_energy,
    powermetrics_sample,
    read_rapl_counter,
    rocm_sample,
)

__all__ = [
    "TelemetrySampler",
    "measure",
    "sample_idle_power",
    "trace_series",
    "MAX_TRACE_SAMPLES",
]

# Cap on samples published in a result document. At the default 0.5 s interval
# this is roughly 40 minutes of full-resolution sampling; longer soaks are
# downsampled uniformly rather than truncated, and the fact is recorded.
MAX_TRACE_SAMPLES = 5000


def _gpu_probes() -> tuple[tuple[str, Callable[[], dict[str, Any] | None]], ...]:
    """GPU telemetry probes, in the order they are tried.

    Built per call rather than held in a module-level tuple. A tuple would
    capture the function objects at import time, which makes them unpatchable
    -- tests that substitute a synthetic probe would silently exercise the
    real one instead. Referencing them inside a function body resolves them
    from module globals at call time and keeps them visible to the linter,
    which a name-based lookup does not.

    A machine has one GPU vendor in practice, so the first probe that answers
    wins; probing the rest every half second would cost more than it measures.
    NVIDIA is first because it is the only one confirmed on real hardware here.
    """
    return (
        ("nvidia-smi", _nvidia_smi_sample),
        ("rocm-smi", rocm_sample),
        ("powermetrics", powermetrics_sample),
    )


class RaplPowerReader:
    """CPU-package power from Intel RAPL, without blocking the sampler.

    ``vendors.rapl_power_sample`` sleeps for its own interval to get two
    counter readings. Calling that from a loop that already ticks every
    half second would double the sampling interval, so this keeps the previous
    reading instead and derives power from consecutive ticks. The first tick
    returns None because a cumulative counter says nothing until it is read
    twice.

    This exists because RAPL is the *only* power source on a machine with no
    discrete GPU -- an Intel or AMD laptop running on integrated graphics,
    which is most of the consumer hardware this project is aimed at. Without
    it those machines publish no energy data at all, and the joules-per-token
    figures the project treats as a differentiator would only ever exist for
    people who already own an NVIDIA card.

    Its scope is narrower than a GPU probe's and every sample says so: it
    measures the CPU package and excludes a discrete GPU entirely, so it must
    never be presented as whole-system power.
    """

    DOMAIN = "/sys/class/powercap/intel-rapl:0"

    def __init__(self, domain: str = DOMAIN) -> None:
        self._domain = domain
        self._previous: tuple[float, float] | None = None  # (energy_uj, monotonic)
        self._max_energy_uj: float | None = None
        self._checked_max = False

    def available(self) -> bool:
        """Whether this machine exposes the counter at all (Linux only)."""
        return read_rapl_counter(f"{self._domain}/energy_uj") is not None

    def sample(self) -> dict[str, Any] | None:
        """Power since the previous call, or None if that cannot be derived."""
        now = time.monotonic()
        energy_uj = read_rapl_counter(f"{self._domain}/energy_uj")
        if energy_uj is None:
            self._previous = None
            return None
        if not self._checked_max:
            self._max_energy_uj = read_rapl_counter(f"{self._domain}/max_energy_range_uj")
            self._checked_max = True

        previous = self._previous
        self._previous = (energy_uj, now)
        if previous is None:
            return None
        elapsed = now - previous[1]
        if elapsed <= 0:
            return None
        return parse_rapl_energy(previous[0], energy_uj, elapsed, max_energy_uj=self._max_energy_uj)


#: Extra keys a vendor probe may contribute beyond the common sample shape.
_GPU_EXTRA_KEYS = frozenset(
    {"telemetry_vendor", "vram_percent", "cpu_power_watts", "gpu_power_watts", "power_basis"}
)

#: Keys carried through from a RAPL sample. `scope` travels with the reading
#: because CPU-package power and GPU power are different quantities, and a
#: result that does not say which it measured invites them to be compared.
_RAPL_KEYS = ("power_watts", "energy_joules", "counter_wrapped", "telemetry_vendor", "scope")


def _nvidia_smi_sample() -> dict[str, Any] | None:
    """One sample of GPU telemetry via nvidia-smi. None if unavailable.

    Queries the device index and name alongside the metrics so results
    state *which* device was measured (audited defect: previously the
    fields could read like generic "the GPU" metrics).
    """
    cmd = [
        "nvidia-smi",
        "--query-gpu=index,name,memory.used,utilization.gpu,temperature.gpu,power.draw",
        "--format=csv,noheader,nounits",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5.0,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode != 0:
            return None
        parts = [p.strip() for p in proc.stdout.strip().splitlines()[0].split(",")]
        if len(parts) < 6:
            return None
        device_index, device_name, vram_mb, gpu_util, temp_c, power_w = parts[:6]

        def _num(value: str) -> float | None:
            try:
                return float(value)
            except ValueError:
                return None

        return {
            "vram_mb": _num(vram_mb),
            "gpu_util_percent": _num(gpu_util),
            "temperature_c": _num(temp_c),
            "power_watts": _num(power_w),
            "gpu_device_index": device_index,
            "gpu_device_name": device_name or None,
        }
    except (OSError, subprocess.TimeoutExpired, IndexError):
        return None


def _system_ram_sample() -> tuple[float | None, str | None]:
    """Used system RAM in MB as (value, source). Platform-safe fallback."""
    try:
        import psutil

        vm = psutil.virtual_memory()
        return (
            vm.total / (1024 * 1024) - vm.available / (1024 * 1024),
            "psutil.virtual_memory",
        )
    except ImportError:
        pass
    # Fallback: Windows GlobalMemoryStatusEx. Guarded by platform so the
    # ctypes.windll access never runs on Linux/macOS (audited defect:
    # previously attempted on every non-psutil platform).
    if platform.system() != "Windows":
        return None, None
    try:
        import ctypes
        import ctypes.wintypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.wintypes.DWORD),
                ("dwMemoryLoad", ctypes.wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return (
            (stat.ullTotalPhys - stat.ullAvailPhys) / (1024 * 1024),
            "windows-globalmemorystatus",
        )
    except (OSError, AttributeError, ImportError, ValueError):
        # ImportError/ValueError: ctypes.wintypes does not exist on
        # non-Windows builds; AttributeError: no windll. Fail soft to
        # (None, None) on every platform.
        return None, None


def _cpu_util_sample() -> tuple[float | None, str | None]:
    """System-wide CPU utilization percent as (value, source)."""
    try:
        import psutil

        return psutil.cpu_percent(interval=None), "psutil.cpu_percent"
    except ImportError:
        return None, None


class TelemetrySampler:
    """Sample hardware telemetry at a fixed interval in a daemon thread."""

    def __init__(self, interval_seconds: float = 0.5) -> None:
        self.interval = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._samples: list[dict[str, Any]] = []
        self._sources: dict[str, str | None] = {}
        # Probed once. On a machine without the sysfs counter -- anything not
        # Linux, and Linux on non-Intel silicon -- this stays None and costs
        # the loop nothing per tick.
        reader = RaplPowerReader()
        self._rapl: RaplPowerReader | None = reader if reader.available() else None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval * 4 + 2)

    _SCOPE = {
        "ram_mb": "system",
        "cpu_util_percent": "system",
        "vram_mb": "device",
        "gpu_util_percent": "device",
        "temperature_c": "device",
        "power_watts": "device",
    }

    #: Scope overrides keyed by the source that actually answered. Power is
    #: the one field whose scope depends on where it came from: a GPU probe
    #: reports device power, while RAPL reports the CPU package and excludes a
    #: discrete GPU entirely. Publishing both as "device" would invite them to
    #: be compared, which is the error this project exists to prevent.
    _SCOPE_BY_SOURCE = {
        ("power_watts", "intel-rapl"): "cpu-package",
    }

    def summary(self) -> dict[str, Any]:
        """Aggregate collected samples into peak/average metrics.

        Keys are stable across versions; provenance (scope/source/device)
        lives in :meth:`provenance` so summaries stay merge-compatible
        with historical ``metrics`` blocks.
        """
        with self._lock:
            samples = list(self._samples)
        if not samples:
            return {
                "peak_ram_mb": None,
                "peak_vram_mb": None,
                "avg_cpu_util_percent": None,
                "avg_gpu_util_percent": None,
                "max_temperature_c": None,
                "average_power_watts": None,
            }

        def peak(key: str) -> float | None:
            values = [float(v) for s in samples if (v := s.get(key)) is not None]
            return max(values) if values else None

        def avg(key: str) -> float | None:
            values = [float(v) for s in samples if (v := s.get(key)) is not None]
            return round(sum(values) / len(values), 2) if values else None

        return {
            "peak_ram_mb": peak("ram_mb"),
            "peak_vram_mb": peak("vram_mb"),
            "avg_cpu_util_percent": avg("cpu_util_percent"),
            "avg_gpu_util_percent": avg("gpu_util_percent"),
            "max_temperature_c": peak("temperature_c"),
            "average_power_watts": avg("power_watts"),
        }

    def provenance(self) -> dict[str, Any]:
        """Scope/source/device metadata for the collected telemetry.

        Returned separately from :meth:`summary` so result documents can
        carry a top-level ``telemetry`` block that states *what was
        measured* (system-wide vs device), *how* (psutil / Windows API /
        nvidia-smi), and *which device* was actually sampled — without
        changing the shape of ``metrics`` summaries.
        """
        with self._lock:
            samples = list(self._samples)
        device: dict[str, Any] | None = None
        for sample in samples:
            if sample.get("gpu_device_index") is not None:
                device = {
                    "gpu_device_index": sample.get("gpu_device_index"),
                    "gpu_device_name": sample.get("gpu_device_name"),
                }
                break
        block: dict[str, Any] = {
            "source": "aihwbench-telemetry",
            "interval_seconds": self.interval,
            "scope": {
                key: self._SCOPE_BY_SOURCE.get((key, self._sources.get(key)), value)
                for key, value in self._SCOPE.items()
            },
            "sources": dict(self._sources),
            "samples": len(samples),
            # The measured time series. Aggregates alone cannot show a
            # throttling curve or a power spike, so the analyzers that read
            # those had no producer until this was published.
            "trace": self.trace_for_result(),
        }
        if device is not None:
            block["device"] = device
        npu_block = npu_snapshot_safe()
        if npu_block is not None:
            block["npu"] = npu_block
        return block

    def trace_for_result(self, max_samples: int = MAX_TRACE_SAMPLES) -> dict[str, Any]:
        """The time series, shaped for inclusion in a result document.

        The summary aggregates in ``metrics`` cannot answer "did it throttle?"
        or "when did power spike?" -- those need the series. Without one, the
        thermal and energy analyzers in :mod:`aihwbench.analysis` have no
        producer and can only ever run in tests.

        Long soak runs are downsampled uniformly to ``max_samples`` so a result
        document stays a reasonable size. Downsampling is recorded rather than
        hidden: ``downsampled`` says whether it happened, and ``samples_total``
        keeps the true count.
        """
        samples = self.raw_trace()
        total = len(samples)
        if total > max_samples > 0:
            # Uniform stride keeps the shape of the curve, including its
            # endpoints, rather than truncating the tail where throttling shows.
            step = total / max_samples
            kept = [samples[min(int(i * step), total - 1)] for i in range(max_samples)]
            if kept[-1] is not samples[-1]:
                kept[-1] = samples[-1]
            samples = kept
        return {
            "samples_total": total,
            "samples_kept": len(samples),
            "downsampled": len(samples) < total,
            "interval_seconds": self.interval,
            "series": samples,
        }

    def raw_trace(self) -> list[dict[str, Any]]:
        """Timestamped raw samples (epoch seconds), oldest first.

        Optional storage: attach to result artifacts that want the full
        time series instead of only the summary aggregates. Never
        required — summaries remain the canonical published metrics.
        """
        with self._lock:
            return [dict(sample) for sample in self._samples]

    def _loop(self) -> None:
        while not self._stop.is_set():
            started = time.time()
            ram_mb, ram_source = _system_ram_sample()
            cpu_util, cpu_source = _cpu_util_sample()
            sample: dict[str, Any] = {
                "timestamp": started,
                "ram_mb": ram_mb,
                "cpu_util_percent": cpu_util,
                "vram_mb": None,
                "gpu_util_percent": None,
                "temperature_c": None,
                "power_watts": None,
                "gpu_device_index": None,
                "gpu_device_name": None,
            }
            self._sources["ram_mb"] = ram_source
            self._sources["cpu_util_percent"] = cpu_source

            # First vendor that answers wins; see _gpu_probes.
            gpu = None
            gpu_source = None
            for source_name, probe in _gpu_probes():
                gpu = probe()
                if gpu is not None:
                    gpu_source = source_name
                    break

            if gpu is not None:
                sample.update({k: v for k, v in gpu.items() if k in sample or k in _GPU_EXTRA_KEYS})
                for key in ("vram_mb", "gpu_util_percent", "temperature_c", "power_watts"):
                    self._sources[key] = gpu_source if gpu.get(key) is not None else None
            else:
                for key in ("vram_mb", "gpu_util_percent", "temperature_c", "power_watts"):
                    self._sources[key] = None

            # Power of last resort. On a machine with no discrete GPU no probe
            # above reports any, and without this the run carries no energy
            # data at all -- which is most consumer laptops. It is a fallback
            # rather than a peer: RAPL measures the CPU package only, so where
            # a GPU probe answered, its reading is the better one.
            if sample.get("power_watts") is None and self._rapl is not None:
                rapl = self._rapl.sample()
                if rapl is not None:
                    sample.update({k: rapl[k] for k in _RAPL_KEYS if k in rapl})
                    self._sources["power_watts"] = "intel-rapl"

            # Battery, where there is one. Sampled per point rather than once,
            # because the drain rate over a sustained run is the number laptop
            # owners want and a single reading cannot give it.
            battery = battery_sample()
            if battery is not None:
                sample.update(battery)
                self._sources["battery_percent"] = "psutil"
            with self._lock:
                self._samples.append(sample)
            time.sleep(self.interval)


#: GPU utilization above which a "baseline" sample is not an idle reading at
#: all but a measurement of someone else's work. Subtracting it would
#: understate the benchmark's own consumption, so the baseline is refused
#: instead. A genuinely idle card reads 0-3%; desktop compositing adds a few
#: points, so the threshold sits above that and well below real compute.
IDLE_MAX_GPU_UTIL_PERCENT = 15.0


def sample_idle_power(seconds: float = 2.0, interval: float = 0.5) -> dict[str, Any]:
    """Measure GPU power while the benchmark's own load is not running.

    Energy per token is only meaningful against a baseline: a 200 W reading on
    a card that idles at 150 W is a very different result from the same reading
    on one that idles at 20 W. Without this, ``incremental_power_watts`` is
    always None and every joules-per-token figure silently includes the idle
    draw of the whole card.

    This is the machine's idle draw immediately before load, not a
    manufacturer figure. Returns ``watts: None`` when no power sensor is
    readable, which is honest -- it never substitutes a nominal TDP.

    Two things beyond the wattage are recorded, both learned from a reading
    taken on real hardware that produced 0.0009 J/token where a previous run of
    the same workload on the same machine produced 0.0777 J/token:

    * **Utilization**, because a card that is busy is not idle. Above
      ``IDLE_MAX_GPU_UTIL_PERCENT`` the baseline is refused rather than
      returned, since subtracting another process's draw makes the benchmark
      look more efficient than it is. Refusing costs the incremental figures;
      returning a wrong one corrupts them.
    * **Resident VRAM**, because it is what explains the 84x swing above. A
      card holding a model from an earlier run sits at high clocks and draws
      far more at rest than the same card after the model is evicted. Both
      readings are honest measurements of different machine states -- and two
      energy figures measured in different states are not comparable. Stating
      the state is what lets a consumer see that, rather than reading the gap
      as a hardware difference.
    """
    readings: list[float] = []
    utils: list[float] = []
    vram: list[float] = []
    deadline = time.time() + max(0.0, seconds)
    source: str | None = None
    # The same last-resort power source the sampler uses. Without it a machine
    # with no discrete GPU would measure power under load and have nothing to
    # measure it against, so every energy figure would stay null.
    rapl = RaplPowerReader()
    rapl_reader = rapl if rapl.available() else None
    if rapl_reader is not None:
        rapl_reader.sample()  # prime: a cumulative counter needs two readings
    while time.time() < deadline:
        sample = _nvidia_smi_sample()
        if sample is not None and sample.get("power_watts") is not None:
            readings.append(float(sample["power_watts"]))
            source = "nvidia-smi"
            if sample.get("gpu_util_percent") is not None:
                utils.append(float(sample["gpu_util_percent"]))
            if sample.get("vram_mb") is not None:
                vram.append(float(sample["vram_mb"]))
        elif rapl_reader is not None:
            rapl_sample = rapl_reader.sample()
            if rapl_sample is not None and rapl_sample.get("power_watts") is not None:
                readings.append(float(rapl_sample["power_watts"]))
                source = "intel-rapl"
        time.sleep(interval)
    if not readings:
        return {
            "watts": None,
            "samples": 0,
            "source": None,
            "quiescent": None,
            "reason": "no readable power sensor",
        }

    util_mean = round(sum(utils) / len(utils), 2) if utils else None
    util_max = round(max(utils), 2) if utils else None
    mean_watts = sum(readings) / len(readings)
    # The baseline's own variation.
    #
    # A card at rest is not at a constant draw. Measured on the reference
    # machine within one session: 14.9 W, 29.3 W, 30.3 W and 31.4 W, all
    # honestly sampled as "idle" -- and with a model resident it oscillated
    # between 14 W and 21 W at 0% utilization, a 50% swing across which a
    # two-second window can land anywhere.
    #
    # Published without this, `incremental_power_watts` looks equally precise
    # whether the thing subtracted was steady or swinging, and a workload
    # drawing less than the baseline's own spread produces a difference that
    # is not a measurement.
    spread = max(readings) - min(readings)
    baseline: dict[str, Any] = {
        "watts": round(mean_watts, 3),
        "watts_min": round(min(readings), 3),
        "watts_max": round(max(readings), 3),
        "watts_spread": round(spread, 3),
        "samples": len(readings),
        "source": source,
        "gpu_util_mean_percent": util_mean,
        "gpu_util_max_percent": util_max,
        # Resident VRAM at rest. Non-zero means something was already loaded,
        # which raises the idle draw and makes this baseline specific to that
        # state.
        "resident_vram_mb": round(sum(vram) / len(vram), 1) if vram else None,
        "quiescent": True,
        "reason": None,
    }

    if util_mean is not None and util_mean > IDLE_MAX_GPU_UTIL_PERCENT:
        baseline["quiescent"] = False
        baseline["reason"] = (
            f"GPU averaged {util_mean}% utilization during the baseline window, "
            f"above the {IDLE_MAX_GPU_UTIL_PERCENT}% idle threshold: this "
            "measures other work, not an idle machine"
        )
        # The measurement is kept under its own key for diagnosis, but it is
        # not offered as a baseline. Fail closed: no incremental figure is
        # better than one that flatters the benchmark.
        baseline["observed_watts"] = baseline["watts"]
        baseline["watts"] = None

    return baseline


def trace_series(result: dict[str, Any]) -> list[dict[str, Any]]:
    """The telemetry time series from a result document, or an empty list.

    Tolerates results written before traces were published, and results whose
    telemetry block is absent or malformed: an analyzer that cannot find a
    series must report having nothing to analyze, never invent one.
    """
    telemetry = result.get("telemetry")
    if not isinstance(telemetry, dict):
        return []
    trace = telemetry.get("trace")
    if not isinstance(trace, dict):
        return []
    series = trace.get("series")
    if not isinstance(series, list):
        return []
    return [s for s in series if isinstance(s, dict)]


def measure(fn: Callable[[], Any]) -> tuple[Any, float]:
    """Run fn and return (result, elapsed_ms)."""
    start = time.perf_counter()
    result = fn()
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return result, elapsed_ms


def npu_snapshot_safe() -> dict[str, Any] | None:
    """Best-effort NPU telemetry block (#18); None when no NPU is detected.

    Never raises. Uses the structured hook contract from
    :mod:`aihwbench.npu`: fields always exist, values stay ``None`` until
    a real driver counter is wired — nothing is fabricated.
    """
    try:
        from .npu import npu_telemetry

        block = npu_telemetry()
    except Exception:  # pragma: no cover - host-hardware dependent
        return None
    return block if block.get("npu_device") else None
