# Experiment manifests

A manifest describes an experiment declaratively — models, runtimes, devices,
workloads, repetitions, telemetry and an optional sweep — so a run is
reproducible from a file under version control rather than a shell command
someone has to remember.

```bash
aihwbench run experiments/my-experiment.json
```

JSON always works. TOML works on Python 3.11+ (stdlib `tomllib`), and YAML
works when PyYAML is installed.

`my-experiment.json` is a runnable starting point, not a benchmark result. It
names `qwen2.5:0.5b-instruct-q4_K_M` on `ollama` because that pair is small
enough to pull quickly — check `aihwbench runtimes` and change both fields to
something your machine actually has.

Unknown top-level keys are rejected rather than ignored, so a typo fails
loudly instead of silently changing what gets measured. The accepted keys are
`name`, `description`, `models`, `model_paths`, `runtimes`, `devices`,
`workloads`, `repetitions`, `telemetry` and `sweep`.
