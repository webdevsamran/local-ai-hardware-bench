# Frequently Asked Questions

Questions about running, measuring and comparing local AI models on your own
hardware. Longer answers live in the [guides](docs/guides/); this page is the
short version of each.

## General

**Is AIHWBench free? Can I use it commercially?**
Yes. The core is Apache-2.0 — free for personal and commercial use.
Future Enterprise/Cloud offerings will add scale and governance, never
artificially lock basic benchmarking. See [SUSTAINABILITY.md](SUSTAINABILITY.md).

**Does it send my data anywhere?**
No. Everything runs locally and works offline. Results are published
only when you explicitly submit them, after privacy scanning.

**Is my hardware supported?**
Run `aihwbench doctor`. Runtimes without the required hardware report
`HARDWARE_REQUIRED` honestly rather than pretending.

**How is this different from MLPerf Client, LocalScore or llama-bench?**
MLPerf Client certifies approved models on approved hardware. LocalScore
collapses everything into one composite score. `llama-bench` measures
in-process kernel time, not the serving path a user waits on. AIHWBench
measures any supported backend on the hardware you actually own, publishes the
raw data, and states when two numbers cannot honestly be compared. Full
comparison: [docs/competitive-analysis.md](docs/competitive-analysis.md).

**Which runtimes does it support?**
llama.cpp, Ollama, ONNX Runtime, OpenVINO, OpenVINO GenAI, LM Studio, vLLM,
SGLang, TensorRT, ROCm, Lemonade (Ryzen AI), QNN, MLX, ExLlamaV2, HailoRT and
Windows ML/DirectML. Which of those have run on real silicon here, and which
have not, is stated per runtime in the [README](README.md#supported-runtimes-and-hardware).

## Choosing hardware

**How much VRAM do I need to run a 7B, 13B or 70B model?**
Roughly 4.5 GB, 8.3 GB and 45 GB respectively at q4_K_M, plus a KV cache that
grows with context and 1–2 GB of overhead. Use `aihwbench fit` for an estimate,
clearly labelled as one. Full table and caveats:
[How much VRAM do I need?](docs/guides/vram-requirements-for-local-llms.md)

**What happens if the model does not fit in VRAM?**
Throughput falls off a step, not a slope. Measured on an RTX 3080 Ti Laptop,
one adjacent step in offloaded layers cost **39.6%**, and the full curve spanned
**5.8×**. Where that step sits depends on your PCIe generation, memory bandwidth
and what else is using the card:
[the offload cliff](docs/results/offload-cliff-rtx3080ti.md).

**Is an NPU faster than a GPU for running LLMs?**
For token generation on a machine that also has a discrete GPU, generally no —
decode is memory-bandwidth-bound and NPUs are built for efficiency rather than
peak bandwidth. NPUs win on performance per watt and on leaving the GPU free.
No NPU machine has been available to this project, and that page says so:
[NPU vs GPU vs CPU](docs/guides/npu-vs-gpu-for-local-ai.md).

**Is local inference cheaper than a cloud API?**
It depends on volume, electricity price and what you would have paid per token.
The [local-vs-cloud calculator](https://webdevsamran.github.io/local-ai-hardware-bench/local-vs-cloud)
works the break-even out from measured power draw rather than from a datasheet
TDP.

**Should I buy more VRAM or a faster GPU?**
Usually more VRAM. A model that fits entirely in VRAM on a slower card beats a
faster card that has to spill layers to system RAM — by far more than the gap
between the two cards. See the offload cliff study above.

## Performance

**How many tokens per second do I need?**
About 7–10 tok/s keeps pace with a fast reader; 20+ feels instant. For chat,
code completion or agentic loops, time to first token matters more than
throughput — a 200 ms TTFT at 30 tok/s feels faster than a 2 s TTFT at 80 tok/s.
[Tokens per second, explained](docs/guides/tokens-per-second-explained.md).

**Does KV-cache quantization make generation faster?**
No — it is a memory feature. Across nine K/V dtype combinations at 32K context,
`q4_0` for both caches cut cache memory by 71.9% with a throughput difference
inside the noise floor, while two asymmetric configurations lost over 60% of
throughput. The rule: use the same dtype for K and V.
[KV-cache quantization](docs/results/kv-cache-rtx3080ti.md).

**Which quantization should I use?**
The largest model that fits *entirely* on the accelerator, at q4_K_M or better,
with room for the KV cache. Moving up a precision level is usually a better
trade than accepting partial offload.
[Choosing a quantization](docs/guides/choosing-a-quantization.md).

**Why does my number not match a benchmark I read online?**
Almost always because the two runs were never comparable: different
quantization, context length, runtime build, power profile, or background load.
During development of this project a 15% difference between two devices turned
out to be background CPU contention. Run `aihwbench self-test` to see your own
noise floor before trusting a difference.

**Why are some metrics null?**
Because the runtime or the operating system didn't expose them. AIHWBench never
estimates unavailable data, and never writes `0` where it means "unknown".

## Benchmarks

**Why can't I compare two results?**
The comparison classifier refuses comparisons when model identity,
workload parameters, or protocol differ. This prevents misleading
"winner" claims. See [methodology](docs/methodology.md) and the
[comparability rubric](docs/comparability-rubric.md).

**What if both results are missing the same field — are they comparable?**
No. Missing on both sides is treated as *unknown*, not as agreement, and the
classifier returns `INSUFFICIENT_METADATA`. Two results that both omit a field
look identical to a naive comparison, which is the failure this rule exists to
prevent.

**What does "Tested" mean?**
Real execution on that hardware produced a validated result. Anything
else is labeled NOT_INSTALLED / HARDWARE_REQUIRED / CONFIGURATION_REQUIRED.

**What do trust states mean?**
The canonical values are lowercase and defined in `aihwbench/trust.py`:

- `verified` — executed on a maintainer-controlled reference machine
- `community_validated` — independently reproduced by a community member
- `unreviewed` — submitted, not yet reproduced (the default for new results)
- `flagged` — statistically anomalous; queued for human review, never auto-rejected
- `invalidated` — withdrawn with a recorded reason; history is preserved
- `superseded` — replaced by a referenced newer result

`UNVERIFIED` appears in older code as a deprecated alias of `unreviewed`; new
code should use `unreviewed`.

**Can I use this in CI to catch performance regressions?**
Yes. The regression gate exits with code 5 when a regression is detected, and
with code 3 when the two results were not comparable — so a gate that *cannot*
compare fails rather than passing silently. Exit codes are a stable contract:
[docs/exit-codes.md](docs/exit-codes.md).

## Privacy and security

**What is stripped from a published result?**
Serial numbers, MAC addresses, IP addresses, usernames, Windows and macOS home
paths, cloud access key ids, API keys and email addresses. The scan fails
closed: any match blocks publication. See
[docs/security/privacy.md](docs/security/privacy.md).

**Can I check a result before submitting it?**
Yes — validation, the privacy scan and integrity hashing all run locally, and
the same checks run again in CI on the pull request.

**How do I report a vulnerability?**
Privately, through GitHub Security Advisories — see [SECURITY.md](SECURITY.md).
Please do not open a public issue for a vulnerability.

## Contributing

**What is the most useful thing I can contribute?**
A benchmark result from hardware nobody here owns. Nine published results all
come from one laptop, while ten backends are written and have never executed
on the silicon they target. See
[docs/hardware-needed.md](docs/hardware-needed.md) and
[SPONSORS.md](SPONSORS.md).

**How do I add a runtime backend?**
See the [Plugin API guide](docs/guides/plugin-api.md) and
[backend docs](docs/backends/overview.md). Third-party backends ship as
separate packages via entry points.

**Do I have to sign a CLA?**
No. Contributions remain Apache-2.0; you keep copyright (see
[GOVERNANCE.md](GOVERNANCE.md)).

**Can I sponsor the project or lend hardware?**
Yes, and hardware is worth more than money right now. Terms — including what
sponsorship explicitly does not buy — are in [SPONSORS.md](SPONSORS.md) and
[docs/vendor-collaboration.md](docs/vendor-collaboration.md).
