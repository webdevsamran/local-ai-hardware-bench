"""Running one runtime's measurement through another's engine, honestly.

Most of the "backends" in this project are not separate inference engines.
Vulkan, SYCL, ROCm and HIP are *build variants* of llama.cpp; QNN, TensorRT and
DirectML are *execution providers* of ONNX Runtime; Lemonade speaks the same
OpenAI-compatible HTTP API vLLM and SGLang do. Each of them selects different
silicon and different kernels, which is exactly what this project exists to
measure — but the loop that issues the requests and times them is the same loop
every time.

So they delegate, and this module is where the delegation rules live. Nine
private copies of "start the server, time the tokens, build the document" is
the failure mode: they drift, and the ones nobody can run are the ones that
drift furthest, because no test on the maintainer's machine ever executes them.

Two rules, and both of them are about not lying:

**Say what ran it.** A delegated result records `runtime.delegated_to`, so a
reader can tell that a row labelled `rocm` was produced by llama.cpp's HIP
build rather than by some separate AMD runtime. The label is not a disguise.

**Never fall back.** If the requested device or provider is not there, refuse.
Falling back to CPU produces a result labelled `qnn` that measured an x86 core,
and `runtime.name` is in the comparison-safety classifier's strict set — so a
mislabelled result does not merely misinform someone reading it, it licenses
the classifier to rank it against real QNN runs. A refusal costs a user five
minutes; a fabricated row costs the dataset its point.
"""

from __future__ import annotations

from typing import Any

from .base import BackendError, BenchmarkConfig


def relabel(
    result: dict[str, Any],
    *,
    name: str,
    backend: str,
    delegated_to: str,
    device: str | None = None,
) -> dict[str, Any]:
    """Stamp a delegated result with the runtime it represents.

    `runtime.name` becomes the delegating backend's name because the compute
    path genuinely differs: llama.cpp on Vulkan and llama.cpp on CUDA run
    different kernels with different numerics, and two such runs must not be
    strictly comparable. Since `runtime.name` is in the classifier's strict
    set, relabelling is what keeps them apart.

    `delegated_to` is added rather than hidden, because the difference between
    "AMD shipped a runtime" and "llama.cpp has a HIP build" matters to anyone
    deciding what the number means.
    """
    runtime = result.setdefault("runtime", {})
    runtime["name"] = name
    runtime["backend"] = backend
    runtime["delegated_to"] = delegated_to
    if device is not None:
        runtime["device"] = device
    return result


def with_extra(config: BenchmarkConfig, **extra: Any) -> BenchmarkConfig:
    """A copy of `config` with `extra` keys added, caller's values winning.

    A sweep that pinned `gpu_layers` means it, and a delegating backend
    quietly overriding it would measure a configuration nobody asked for.
    """
    merged = {**{k: v for k, v in extra.items() if v is not None}, **(config.extra or {})}
    return BenchmarkConfig(**{**config.__dict__, "extra": merged})


def require_llama_device(prefix: str, label: str, config: BenchmarkConfig) -> str:
    """The llama.cpp device id for a backend, or a refusal naming what is there.

    Device ids come from `llama-server --list-devices` (`CUDA0`, `Vulkan0`,
    `SYCL0`, `ROCm0`), which is the binary's own answer rather than a guess
    made here. Asking it has a second benefit: a build lacking the backend
    enumerates no such device, so this catches "your hardware can, your build
    cannot" before a server is started.

    Hardcoding `"Vulkan0"` — which is what the Vulkan backend did — assumes
    both that the build has the backend and that its first device is the one
    wanted. The first assumption is exactly the one that fails.

    A caller-supplied `extra["device"]` is honoured but *checked* against the
    prefix, and this is the one place the caller does not simply win. Running
    `--device CUDA0` through the ROCm backend would measure CUDA and label the
    result `rocm`, which is the same mislabelling by a more deliberate route.
    """
    from ..devices import device_inventory

    requested = (config.extra or {}).get("device")
    if requested is not None:
        value = str(requested).strip()
        if not value.upper().startswith(prefix.upper()):
            raise BackendError(
                f"{label}: --device {value!r} is not a {prefix} device. A run "
                f"offloaded to {value!r} would be labelled {label!r} while "
                "measuring something else; pick a "
                f"{prefix} device or use the backend that owns {value!r}."
            )
        return value

    inventory = device_inventory(rpc_servers=(config.extra or {}).get("rpc_servers"))
    devices = inventory.get("devices") or []
    for device in devices:
        if str(device.get("id", "")).upper().startswith(prefix.upper()):
            return str(device["id"])

    if inventory.get("unresolved"):
        raise BackendError(f"{label}: {inventory['unresolved']}")
    seen = ", ".join(str(d.get("id")) for d in devices) or "none"
    raise BackendError(
        f"{label}: llama.cpp enumerates no {prefix} device (it sees: {seen}). "
        f"The build has no {prefix} backend, or no {prefix}-capable device is "
        "present. Refusing rather than offloading to a different device and "
        "labelling the result as this one."
    )


def run_via_llama_cpp(
    config: BenchmarkConfig,
    system: dict[str, Any],
    *,
    name: str,
    device_prefix: str,
    backend: str,
) -> dict[str, Any]:
    """Measure through llama.cpp with a specific compute backend selected."""
    from . import llama_cpp

    device = require_llama_device(device_prefix, name, config)
    result = llama_cpp.run(with_extra(config, device=device), system)
    return relabel(
        result,
        name=name,
        backend=backend,
        delegated_to="llama.cpp",
        device=device,
    )


def run_via_onnxruntime(
    config: BenchmarkConfig,
    system: dict[str, Any],
    *,
    name: str,
    device: str,
    backend: str,
) -> dict[str, Any]:
    """Measure through ONNX Runtime with a specific execution provider.

    `device` is this project's device vocabulary (`qnn`, `tensorrt`, `dml`),
    which `onnxruntime._providers_for_device` maps to a provider and then
    verifies actually loaded. That verification is the part that matters: ONNX
    Runtime silently falls back to CPU when a provider cannot initialise, and a
    CPU measurement labelled `qnn` is the exact failure this module exists to
    prevent.
    """
    from . import onnxruntime as ort_backend

    result = ort_backend.run(BenchmarkConfig(**{**config.__dict__, "device": device}), system)
    return relabel(result, name=name, backend=backend, delegated_to="onnxruntime")
