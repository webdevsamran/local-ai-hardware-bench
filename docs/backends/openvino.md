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
aihwbench benchmark --backend openvino --model path/to/model.xml --device GPU.0
```

## What is measured

- Real inference latency across warmup + timed iterations
- Device identity (CPU/GPU/NPU index) recorded

## Limitations

- LLM token metrics require an IR-converted chat pipeline
  (OpenVINO GenAI integration tracked separately)
- NPU telemetry hooks are future work