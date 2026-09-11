# OpenVINO GenAI backend

Measured LLM pipelines on Intel CPU, integrated GPU and NPU — and, on recent
OpenVINO releases, on a discrete GPU too.

This is the one backend here that can put several devices in the same machine
on the same footing with the model held constant. Every other LLM runtime in
this project targets one vendor's silicon, so "is the iGPU worth using?" was a
question the dataset could not answer. It can now, and on the reference machine
the answer was not the obvious one.

## Prerequisites

```bash
pip install "aihwbench[openvino]"
```

You also need a model in OpenVINO IR format — a directory containing
`openvino_model.xml`. Either export one with
[optimum-intel](https://github.com/huggingface/optimum-intel), or download a
pre-converted model:

```bash
huggingface-cli download OpenVINO/Qwen2.5-Coder-0.5B-Instruct-int4-ov --local-dir ./qwen-ov
```

## Usage

```bash
aihwbench benchmark --runtime openvino_genai --model-path ./qwen-ov --device cpu
```

`--model-path` takes the directory. Pointing it at the `.xml` works too.

## Devices

```bash
aihwbench detect
```

Pass `--device cpu`, `gpu`, `npu`, `igpu`, or an exact OpenVINO name such as
`GPU.0` or `GPU.1`.

**`--device auto` is refused, on purpose.** OpenVINO's AUTO plugin chooses a
device when it compiles the model and `LLMPipeline` gives no way to ask what it
chose — `core.get_property("AUTO", "EXECUTION_DEVICES")` needs a compiled model
this API does not hand back. `runtime.device` is in the comparison-safety
classifier's strict set, so a guess there does not stay local: the classifier
would go on to rank a silently-CPU result against a GPU one. The error names
the visible devices instead.

## What is measured

The pipeline reports its own `PerfMetrics`, and those are recorded alongside
the caller's wall-clock view rather than instead of it:

| Field | Source |
|---|---|
| `ttft_ms` | first chunk of text reaching the caller |
| `runtime_ttft_ms` (per iteration) | the pipeline's own TTFT |
| `tpot_ms`, `itl_p50/p90/p99_ms` | inter-chunk gaps, via the shared metrics path |
| `generation_tokens_per_second` | the runtime's token count over its decode time |
| `load_time_ms` | compiling the IR for the chosen device |

The two TTFT figures differ because detokenisation sits between them. Reporting
only the runtime's flatters it; reporting only the caller's hides where the
time went.

**Quantization is read, not inferred.** NNCF stamps its settings into the IR's
`rt_info` at conversion time, so a result carries `quantization: int4_asym`
with `quantization_group_size: 128` — what the compressor actually applied,
rather than whatever the directory happened to be named. The optimum-intel
version and the OpenVINO release the IR was built with are recorded too; an IR
built with 2025.2 and run on 2026.3 is a difference worth being able to see.

## Limitations

- **One device per run.** Deliberate: see `--device auto` above.
- **Memory on an Intel GPU is not measured.** Telemetry reads `nvidia-smi`,
  which reports the NVIDIA card whatever the run was on, and an Intel iGPU
  allocates from shared system RAM where that tool cannot see it. Rather than
  publish an idle NVIDIA card's `0.0` as this run's memory use, the backend
  drops `peak_vram_mb` and `avg_gpu_util_percent` and records why in
  `metrics.metric_source`. Unmeasured is not zero. A run on the discrete GPU
  keeps them, because there they are real.
- **NPU is untested here.** The code path exists and the reference machine has
  no NPU, so it is detection plus an honest error rather than a validated
  result.
- **A compiled pipeline is cached per model and device** for the lifetime of
  the process, so an agentic workload does not pay the compile on every turn.
  Benchmarks are unaffected: `run()` compiles once and measures that compile.

## Measured results

See [Three devices, one model](../results/openvino-three-devices.md).
