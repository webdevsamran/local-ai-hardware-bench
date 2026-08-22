# Installation

## Requirements

- Python 3.10+ (Windows, Linux, macOS)
- No runtime dependencies; dev extras only for contributors

## Install

### From source (recommended today)

```bash
pip install .
```

### Editable (contributors)

```bash
pip install -e ".[dev]"
```

Dev extras add ruff, pytest, mypy and coverage tooling.

## Runtime prerequisites

AIHWBench benchmarks whatever runtimes you already have installed.
Nothing is downloaded or installed for you.

| Runtime | Status when missing | How to enable |
|---|---|---|
| Ollama | NOT_INSTALLED | Install from ollama.com |
| llama.cpp | NOT_INSTALLED | Build or download llama-server |
| ONNX Runtime | NOT_INSTALLED | `pip install onnxruntime` (or onnxruntime-directml) |
| OpenVINO | NOT_INSTALLED | `pip install openvino` |
| TensorRT / ROCm / QNN / HailoRT | HARDWARE_REQUIRED | Requires supported hardware |

Run `aihwbench doctor` at any time to see exact status and hints.

## Verify

```bash
aihwbench detect
aihwbench validate --help
```

## Troubleshooting

See [TROUBLESHOOTING.md](../../TROUBLESHOOTING.md).