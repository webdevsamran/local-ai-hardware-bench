# Contributing

Thanks for considering a contribution. This project optimizes for
**trustworthy engineering over appearance**: honest statuses, measured
metrics, reproducible results.

## Ground rules

1. Never fabricate hardware, benchmarks, metrics, or runtime support.
2. A "Tested" claim requires a committed result file produced by a real run.
3. Metrics that cannot be measured are `null` — never estimated.
4. Keep PRs focused; one backend/feature/fix per PR.

## Development setup

```bash
git clone https://github.com/webdevsamran/local-ai-hardware-bench.git
cd local-ai-hardware-bench
pip install -e ".[dev]"
pytest
ruff check benchmark tests
```

## Adding a runtime backend

1. Copy the structure of an existing backend (see `benchmark/backends/ollama.py`).
2. Implement `detect() -> BackendInfo` and `run(config, system) -> dict`.
   - `detect()` must never raise.
   - `run()` must raise `BackendError` with an actionable message when
     prerequisites are missing.
3. Register in `benchmark/backends/__init__.py` (`BACKENDS`, optional `ALIASES`).
4. Add tests: detection on a machine without the runtime, clean failure of
   `run()`, and schema-valid output if you can run it locally.
5. Update README + compatibility matrix only after a real execution.

## Adding a result

1. Run the benchmark with default workload parameters where possible.
2. `aihwbench validate results/raw/<run>.json`
3. Submit a PR adding:
   - the JSON to `results/published/`
   - a platform note under `platforms/<vendor>/`
   - a matrix row update in `docs/compatibility-matrix.md`

CI validates every result file against schema 1.0 automatically.

## Code style

- Typed Python, stdlib-first; dependencies require justification.
- `ruff check` must pass; line length 100.
- Tests required for behavior changes.

## Reporting bugs

Include: OS, CPU/GPU/NPU, driver versions, runtime version, the exact
command, and — if available — the sanitized detection dump
(`aihwbench detect`). Never include serial numbers, MACs, tokens, or paths
containing your username.