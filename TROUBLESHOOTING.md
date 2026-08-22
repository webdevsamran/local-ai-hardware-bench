# Troubleshooting

## CLI

**`aihwbench: command not found`**
Reinstall with `pip install .`, or invoke via `python -m benchmark.cli`.

**A command crashes with a stack trace**
This is a bug — please open an issue with the traceback and your OS/runtime versions.

## Detection

**GPU shows as None but I have one**
- NVIDIA: ensure the driver is installed (`nvidia-smi` works)
- Intel iGPU: install OpenVINO; detection uses its device query
- Check `aihwbench detect` output for partial info

**cpu_cores_physical looks wrong on Linux**
Fixed in recent versions (counts socket×core pairs). Update your checkout.

## Ollama

**Connection refused**
Start Ollama: `ollama serve` (or launch the desktop app), then retry.

**Model not found**
`ollama pull <model>` first; use the exact tag in `--model`.

## llama.cpp

**Server failed to start**
Verify the `llama-server` binary path is discoverable (`PATH` or common
install dirs) and the GGUF path exists.

**Port already in use**
Stop other llama-server instances; the backend binds a local port per run.

## ONNX Runtime / OpenVINO

**Provider/device missing**
Install the matching package variant (`onnxruntime-directml` for Windows
GPU, `openvino` for Intel devices) and re-run `aihwbench runtimes`.

## Results

**Validation fails on my result**
Run `aihwbench validate <file>` — errors list exact field problems.
Common causes: hand-edited timestamps (must be ISO-8601 UTC) or negative metrics.

**Comparison says NOT_COMPARABLE**
That's the safety system working. Match model checksum/workload/protocol
for strict comparability, or read the printed reasons.

## Still stuck?

Open an issue using the bug template: include `aihwbench doctor` output,
OS, and runtime versions. See [SUPPORT.md](.github/SUPPORT.md).