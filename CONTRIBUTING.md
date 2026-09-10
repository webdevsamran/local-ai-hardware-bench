# Contributing

Thanks for considering a contribution. This project optimizes for
**trustworthy engineering over appearance**: honest statuses, measured
metrics, reproducible results.

## Ground rules

1. Never fabricate hardware, benchmarks, metrics, or runtime support.
2. A "Tested" claim requires a committed result file produced by a real run.
3. Metrics that cannot be measured are `null` — never estimated.
4. Keep PRs focused; one backend/feature/fix per PR.
5. No copyright assignment — you keep copyright; contributions are
   Apache-2.0 licensed.

## Development setup

### Windows

```powershell
git clone https://github.com/webdevsamran/local-ai-hardware-bench.git
cd local-ai-hardware-bench
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

### Linux / macOS

```bash
git clone https://github.com/webdevsamran/local-ai-hardware-bench.git
cd local-ai-hardware-bench
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Contribution workflow

1. **Fork** the repository on GitHub.
2. **Clone** your fork locally.
3. **Branch** from `main`:

   ```bash
   git checkout -b feat/my-change
   ```

4. **Implement** your change (small, focused).
5. **Test**:

   ```bash
   pytest
   ruff check aihwbench tests
   ruff format --check aihwbench tests
   ```

6. **Commit** with a clear message (`feat:`, `fix:`, `docs:`, `test:`,
   `chore:` prefixes preferred).
7. **Push** your branch and **open a PR** against `main`.
8. Respond to review feedback; maintainers merge when checks pass.

## Adding a runtime backend

See [docs/guides/plugin-api.md](docs/guides/plugin-api.md) for the full
contract. Summary:

1. Implement `detect() -> BackendInfo` (never raises) and
   `run(config, system) -> dict` (raises `BackendError` cleanly when
   prerequisites are missing).
2. Register in `aihwbench/backends/__init__.py` or publish an external
   package with an `aihwbench.backends` entry point.
3. Add tests: detection without the runtime, clean failure of `run()`,
   and schema-valid output if you can run it locally.
4. Update README + compatibility matrix only after a real execution.

## Submitting a benchmark result

Full walkthrough:
[docs/contributing/benchmarking-your-hardware.md](docs/contributing/benchmarking-your-hardware.md).
Pipeline details: [docs/results/submission-pipeline.md](docs/results/submission-pipeline.md).

1. Run the benchmark with `--workload sustained_generation`, at least 5
   measured iterations after 2 warm-ups. Do **not** use the default chat
   prompt for a throughput submission: it asks for a two-sentence answer, so
   it generates about 29 tokens and measures the GPU's clock ramp rather
   than a sustained rate.
2. `aihwbench validate results/raw/<run>.json --formal`
3. `aihwbench quality results/raw/<run>.json` — all checks must pass. If
   `variance_acceptable` fails, see the troubleshooting section in the
   walkthrough; a monotonic decline is a real finding about your machine and
   worth reporting rather than hiding.
4. Open a PR adding the JSON to `results/published/`, a platform note
   under `platforms/<vendor>/`, and a matrix row update for what was
   actually tested.

Results arrive with trust state `unreviewed`; a measurement is not verified
by the machine that produced it. CI validates every result file against the
current schema automatically.

If you would rather have this reproducible and logged, the repository ships a
GitHub Action you can run on a self-hosted runner — see the walkthrough.

## Documentation contributions

Docs live in `docs/`. Fix inaccuracies first — documentation drift is a
bug. Use the [documentation issue template](https://github.com/webdevsamran/local-ai-hardware-bench/issues/new?template=documentation.yml).

## Code style

- Typed Python, stdlib-first; dependencies require justification.
- `ruff check` and `ruff format --check` must pass; line length 100.
- Tests required for behavior changes.

## Review process

- Maintainers/reviewers aim to respond within a few days (best-effort).
- Results, methodology, and schema changes require lead-maintainer
  review ([GOVERNANCE.md](GOVERNANCE.md)).
- Claim an issue by commenting before starting large work.

## Reporting bugs

Include: OS, CPU/GPU/NPU, driver versions, runtime version, the exact
command, and — if available — the sanitized detection dump
(`aihwbench detect`). Never include serial numbers, MACs, tokens, or paths
containing your username.