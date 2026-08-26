# Contributor Onboarding

Welcome! This walks you through your first contribution end-to-end.

## 1. Pick an issue

Browse issues labeled [`good first issue`](https://github.com/webdevsamran/local-ai-hardware-bench/labels/good%20first%20issue).
Comment to claim it so work isn't duplicated.

## 2. Set up your environment

**Windows**

```powershell
git clone https://github.com/<you>/local-ai-hardware-bench.git
cd local-ai-hardware-bench
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

**Linux/macOS**

```bash
git clone https://github.com/<you>/local-ai-hardware-bench.git
cd local-ai-hardware-bench
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Optional but recommended:

```bash
pip install pre-commit && pre-commit install
```

## 3. Branch and implement

```bash
git checkout -b fix/my-first-fix
```

Follow the coding standards in [CONTRIBUTING.md](../../CONTRIBUTING.md):
ruff-clean code, tests for behavior changes, honest documentation.

## 4. Test locally

```bash
ruff check aihwbench tests
ruff format --check aihwbench tests
mypy aihwbench
pytest
```

All four must pass before you push — CI enforces exactly this.

## 5. Commit, push, open PR

```bash
git add -A
git commit -m "fix: concise description"
git push -u origin fix/my-first-fix
```

Then open a pull request against `main`. The PR template includes a
checklist; fill it honestly. A maintainer will review within a few days.

## What reviewers look for

- Tests covering the change
- No fabricated metrics or unsupported claims
- Privacy-safe outputs
- Clear commit messages

## Getting help

See [SUPPORT.md](../../.github/SUPPORT.md) or ask in your claimed issue.