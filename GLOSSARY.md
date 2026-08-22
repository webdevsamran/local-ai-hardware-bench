# Glossary

| Term | Definition |
|---|---|
| **Backend** | Adapter connecting AIHWBench to a specific runtime |
| **TTFT** | Time To First Token — latency before generation begins |
| **ITL** | Inter-Token Latency — time between consecutive generated tokens |
| **Throughput** | Generated tokens per second during steady-state decoding |
| **Quantization** | Reduced-precision model weights (e.g. Q4_K_M) affecting size/speed/quality |
| **GGUF** | llama.cpp model file format |
| **IR** | Intermediate Representation (OpenVINO model format: .xml + .bin) |
| **Execution Provider** | ONNX Runtime hardware backend (DML, CUDA, CPU) |
| **Suite profile** | Versioned benchmark configuration under `configs/suites/` |
| **Fingerprint** | Deterministic hash identifying an experiment configuration |
| **Trust state** | VERIFIED / COMMUNITY_VALIDATED / UNVERIFIED provenance label |
| **Comparability class** | STRICTLY_COMPARABLE / CONDITIONALLY_COMPARABLE / NOT_COMPARABLE |
| **Regression gate** | CI check failing when a candidate result regresses past thresholds |
| **Warmup** | Untimed iterations that stabilize caches/JIT before measurement |
| **p95 latency** | 95th percentile of per-iteration latencies |
| **Coefficient of variation** | Stddev / mean — relative dispersion measure |
| **NPU** | Neural Processing Unit (Intel Core Ultra, AMD XDNA, Hexagon) |