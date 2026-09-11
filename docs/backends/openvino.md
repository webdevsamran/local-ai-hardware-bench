# OpenVINO Backend

## Prerequisites

```bash
pip install openvino
```

## Devices

Detected devices are reported (CPU, GPU.x, NPU where present):

```bash
aihwbench detect
```

## Usage

```bash
aihwbench benchmark --runtime openvino --model-path path/to/model.xml --device GPU.0
```

## What is measured

- Real inference latency across warmup + timed iterations
- Device identity (CPU/GPU/NPU index) recorded

## Limitations

- This backend measures graph inference. For LLM token metrics — tokens per
  second, time to first token, inter-token latency — use the
  [`openvino_genai` backend](openvino-genai.md), which drives an
  `LLMPipeline` over the same IR
- NPU telemetry hooks are future work