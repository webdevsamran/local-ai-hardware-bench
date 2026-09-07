# AGENTS.md

Working notes for AI coding agents in this repository. Everything here is
checked against CI — if a command below disagrees with
`.github/workflows/ci.yml`, the workflow wins and this file is the bug.

## What this project is

`aihwbench` benchmarks local AI runtimes (llama.cpp, Ollama, ONNX Runtime,
OpenVINO, and others) across CPUs, GPUs and NPUs, and publishes results that
a stranger can reproduce. The product *is* the trustworthiness of the
numbers. That shapes every rule below.

## Setup

```bash
python -m venv .venv && .venv/Scripts/activate   # Windows
pip install -e ".[dev]"
```

Python 3.10 is the floor (`requires-python = ">=3.10"`). CI tests 3.10, 3.12
and 3.13 on Ubuntu, Windows and macOS. The package has **zero runtime
dependencies** — keep it that way; `[tool.ruff]` line length is 100.

## Commands CI runs

```bash
ruff check aihwbench tests
ruff format --check aihwbench tests
mypy aihwbench
pytest -q
pytest -q --cov=aihwbench --cov-branch --cov-fail-under=68
python scripts/check_docs_links.py
python scripts/verify_action_pins.py
cd web && npm ci && npm run lint && npm test && npm run build
```

Run the ruff, mypy and pytest ones before proposing any change. The coverage
floor is 68 and is enforced in CI only, so a local bare `pytest` will not
catch a regression in it.

## Rules that are not style preferences

**A metric that was not measured is `null`. Never an estimate, never
interpolated, never carried over from another run.** `schemas/README.md`
states this and `aihwbench/schemas.py` enforces it. Any change that makes an
absent measurement render as a number is a bug regardless of how good the
number looks.

**`performance_per_watt` is not one unit.** It is tok/s/W for generative
runtimes and inf/s/W for graph/vision ones. Always pair it with
`performance_per_watt_unit()`; never hardcode a unit label, and never rank
the two against each other in one column. See `tests/test_perf_per_watt_units.py`.

**Results are comparable only when the environment matches.** If you touch
`comparability.py` or `compare.py`, do not loosen a check to make two runs
compare — classify the mismatch instead.

**Trust states live in `aihwbench/trust.py`** and nowhere else. There are six.
`UNVERIFIED` is a deprecated alias of `unreviewed`; do not document it as a
state. `tests/test_docs_match_code.py` pins the docs to the code.

## Generated files — never hand-edit

| Path | Regenerate with |
| --- | --- |
| `web/public/data/*.json` | `python scripts/generate_frontend_data.py` |
| `results/dataset/{index.json,dataset.csv,LEADERBOARD.md}` | `aihwbench export results/published --output results/dataset` |
| `docs/reports/*.md` | `aihwbench report results/published/<run>.json` |

CI fails if `web/public/data` is stale, so regenerate and commit rather than
editing by hand.

## Do not touch without being asked

- `results/published/**` — published measurements. Adding, editing or deleting
  one changes the public record. Corrections go through the invalidation path
  (`aihwbench invalidate`), which preserves history.
- `schemas/result-*.schema.json` — a breaking change needs a new major schema
  version *and* a read path for already-published results.
- GitHub Actions SHA pins — `scripts/verify_action_pins.py` checks them, and
  `github/codeql-action/*` entries must all move together or CodeQL fails with
  a version-mismatch error.

## Conventions

Conventional-commit prefixes (`feat:`, `fix:`, `docs:`, `test:`, `chore:`).
Typed Python throughout; `mypy` must pass clean. Prefer the standard library —
a new dependency needs justification in the PR description.
