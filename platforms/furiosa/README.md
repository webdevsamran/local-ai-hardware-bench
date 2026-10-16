# FuriosaAI Platforms

**Status: Tested** — benchmarked live on a single **FuriosaAI RNGD (48GB HBM3)** PCIe accelerator card across 11 models (Generative LLMs, MoE, Reasoning, Multimodal VLMs, Embeddings, and Rerankers).

## Benchmarked Hardware Profiles

- **[FuriosaAI RNGD (48GB HBM3 PCIe Server)](rngd.md)** — 2nd-generation NPU with 8 Tensor Contraction Processor (`TCP`) PE cores (`pe:0..pe:7`), 48 GB HBM3, 300 W TDP ceiling, running `furiosa-llm 2026.4.0-release`.
- **[Comprehensive Flagship Benchmark Study](../../docs/results/furiosa-rngd-48gb-flagship-study.md)** — Full single-stream `(ISL, OSL)` scaling matrices (`128` to `8K` tokens), multi-stream concurrency sweeps (`C=1..64`), multimodal vision sweeps (`224x224` to `1024x1024`), embedding/reranker batch sweeps (`B=1..64`), RAG pipelines, and agentic tool-use loops.
