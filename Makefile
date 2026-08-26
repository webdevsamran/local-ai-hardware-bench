# Convenience task runner for aihwbench development.
# Windows contributors: use the commands from CI (ci.yml) or pyproject extras
# if `make` is unavailable.

.PHONY: install install-dev lint format typecheck test coverage frontend frontend-test frontend-build data docs-check results-pipeline clean

install:
	pip install .

install-dev:
	pip install -e ".[dev]"

lint:
	ruff check aihwbench tests
	ruff format --check aihwbench tests

format:
	ruff format benchmark tests
	ruff check --fix benchmark tests

typecheck:
	mypy aihwbench

test:
	pytest

coverage:
	pytest --cov=aihwbench --cov-report=term-missing --cov-fail-under=55

frontend:
	cd web && npm ci --no-fund --no-audit && npm run lint && npm run test && npm run build

frontend-test:
	cd web && npm run test

frontend-build:
	cd web && npm run build

data:
	python scripts/generate_frontend_data.py

docs-check:
	python scripts/check_docs_links.py

results-pipeline:
	python scripts/check_docs_links.py
	python -m pytest tests/test_schemas.py -q

clean:
	rm -rf build dist *.egg-info .pytest_cache .ruff_cache .mypy_cache .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
