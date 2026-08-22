# Quickstart

Get from zero to a real benchmark result in under five minutes.

## 1. Install

```bash
pip install .
```

Or from a clone:

```bash
git clone https://github.com/webdevsamran/local-ai-hardware-bench.git
cd local-ai-hardware-bench
pip install -e .
```

The package has **zero runtime dependencies**. Everything works offline.

## 2. Check your machine

```bash
aihwbench doctor
```

This shows detected hardware (CPU, GPU, NPU, RAM) and the status of every
supported runtime, with actionable install hints for anything missing.

## 3. See what runtimes are available

```bash
aihwbench runtimes
```

## 4. Run a benchmark

With [Ollama](https://ollama.com) installed and a model pulled:

```bash
ollama pull qwen2.5:0.5b-instruct-q4_K_M
aihwbench benchmark --backend ollama --model qwen2.5:0.5b-instruct-q4_K_M --iterations 3
```

The result is written to `results/raw/` as schema-valid JSON with real,
measured metrics only.

## 5. Validate and inspect

```bash
aihwbench validate results/raw/<your-result>.json
aihwbench report results/raw/<your-result>.json
```

## 6. Compare two runs

```bash
aihwbench compare results/raw/a.json results/raw/b.json
```

Comparisons are classified STRICTLY_COMPARABLE, CONDITIONALLY_COMPARABLE,
or NOT_COMPARABLE. No delta table is produced for incomparable workloads.

## Next steps

- [Installation details](installation.md)
- [Benchmark suites](../../README.md#benchmark-suites)
- [Submitting results](../results/submission-pipeline.md)
- [Methodology](../methodology.md)