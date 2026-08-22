# Ollama Backend

## Prerequisites

- [Ollama](https://ollama.com) installed and running (`ollama serve` or the desktop app)
- A model pulled locally, e.g. `ollama pull qwen2.5:0.5b-instruct-q4_K_M`

## Usage

```bash
aihwbench benchmark --backend ollama --model qwen2.5:0.5b-instruct-q4_K_M --iterations 3
```

## What is measured

- **TTFT** — time to first token from the streaming API response
- **Generation throughput** — completion tokens / eval seconds (reported by Ollama)
- **Prompt throughput** — prompt tokens / prompt eval seconds
- **Token counts** — from the API response, never estimated

## Known limitations

- Model load time is not yet measured (tracked in issue #5)
- Power/temperature telemetry depends on platform support; null when unavailable

## Troubleshooting

- **Connection refused**: ensure Ollama is running on `localhost:11434`
- **Model not found**: run `ollama pull <model>` first
- **Insufficient VRAM/RAM**: pick a smaller quantization