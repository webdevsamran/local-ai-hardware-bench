# llama.cpp Backend

## Prerequisites

- A `llama-server` binary (built or downloaded from llama.cpp releases)
- A GGUF model file with its SHA-256 checksum recorded

## Usage

```bash
aihwbench benchmark --backend llamacpp --model path/to/model.gguf --iterations 3
```

## What is measured

- **TTFT** and per-token timing from server responses
- **Throughput** from token counts and measured eval time
- **Model identity** — file SHA-256 checksum is recorded for reproducibility

## Known limitations

- Server startup/shutdown is managed automatically per run
- Context length must fit within available memory

## Troubleshooting

- **Server failed to start**: check the model path and that the port is free
- **Out of memory**: reduce context length or use a smaller quantization