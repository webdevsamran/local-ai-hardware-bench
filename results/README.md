# Results

- `raw/` — output of local benchmark runs (gitignored except published copies)
- `normalized/` — results normalized for cross-run comparison
- `published/` — validated, committed results with reproducibility blocks.
  Every file here is schema-validated in CI.

Publish a result by copying it here after `aihwbench validate` passes,
together with its markdown report in `docs/reports/`. `aihwbench quality`
should report every check passing; a result that fails one is not ready.

## The graph-runtime results are noisy

With variance now measured for them — it was not, because ONNX Runtime and
OpenVINO record per-iteration timing as `latency_ms` where the check looked
for `total_latency_ms` — the ONNX Runtime CPU result shows a latency
coefficient of variation of **0.4997**, passing the 0.5 threshold by three
ten-thousandths. The DirectML result sits at 0.32.

They are published as they are rather than re-run to a nicer number: the
threshold is not being moved to accommodate them, and a result sitting on the
line is worth seeing. Graph inference of a small vision model takes single-
digit milliseconds per iteration, where scheduling noise is a large share of
the measurement, and more iterations would help more than a re-run would.

## Results that predate a field

The schema gains fields as the tool learns to measure more, and older results
do not acquire them retroactively — a provenance hash written today attests to
the file as it is now, not to the run that produced it.

The four ONNX Runtime and OpenVINO results currently score 5/6 rather than 6/6
because they predate `provenance`. They are correct measurements taken on a
quiet machine, and they stay as they are until they can be re-measured on one.

That caveat is not incidental. Re-measuring them under a background antivirus
scan produced 2.53 inferences per second where the same model on the same
machine had done 299.92 — a 118x error that passed every other quality check.
Those numbers were discarded and the originals restored: a missing derived
hash is a metadata gap, where a 118x wrong number is not. `aihwbench` now
records machine load on every run and refuses to publish a contended one, so
the mistake cannot repeat silently.