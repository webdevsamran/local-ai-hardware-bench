# ONNX Runtime Backend

## Prerequisites

```bash
pip install onnxruntime          # CPU
pip install onnxruntime-directml # Windows GPU (DirectML)
```

Plus an ONNX-format model.

## Usage

```bash
aihwbench benchmark --backend onnxruntime --model path/to/model.onnx
```

## Execution providers

The backend reports detected providers (e.g. `DmlExecutionProvider`,
`CUDAExecutionProvider`, `CPUExecutionProvider`) in the result document.

## What is measured

- Inference latency percentiles over real runs
- Provider/device identity recorded for reproducibility

## Limitations

- Token-level LLM metrics require a tokenizer-integrated pipeline;
  generic graph inference reports latency only.