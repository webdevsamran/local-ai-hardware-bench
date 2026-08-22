# Citing AIHWBench

If you use AIHWBench in research, please cite the project. The canonical
citation lives in [CITATION.cff](../../CITATION.cff):

```bibtex
@software{aihwbench,
  title = {AIHWBench: Open Local AI Hardware Benchmark},
  author = {Samran (@webdevsamran) and contributors},
  year = {2026},
  url = {https://github.com/webdevsamran/local-ai-hardware-bench},
  license = {Apache-2.0}
}
```

## Reproducibility statement

Published results carry:

- schema version, protocol version, framework git commit
- run UUID and UTC timestamp
- full hardware/runtime/model identity incl. model checksums
- workload parameters (prompt, token budget, sampling, seed)

A DOI will be minted via Zenodo once the dataset spans multiple hardware
classes (tracked in issue #23). No DOI exists today.