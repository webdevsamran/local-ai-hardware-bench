# Results

- `raw/` — output of local benchmark runs (gitignored except published copies)
- `normalized/` — results normalized for cross-run comparison
- `published/` — validated, committed results with reproducibility blocks.
  Every file here is schema-validated in CI.

Publish a result by copying it here after `aihwbench validate` passes,
together with its markdown report in `docs/reports/`.