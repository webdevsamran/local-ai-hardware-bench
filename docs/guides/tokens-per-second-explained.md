# Tokens per second, explained — and why it is not the number you feel

Every local LLM benchmark leads with tokens per second. It is a real measurement
and it is not the whole story: two configurations with identical tok/s can feel
completely different to use, and the one with the *lower* number is sometimes
the better experience.

This page explains what each timing metric actually measures, which one you
notice, and how they come apart.

## The four numbers

| Metric | What it measures | What it tells you |
| --- | --- | --- |
| **Prompt processing (prefill) tok/s** | How fast the model reads your input | How long a long prompt or a big document takes to ingest |
| **Time to first token (TTFT)** | Request sent → first token arrives | How responsive it *feels* when you hit enter |
| **Generation tok/s** | Steady-state output rate once streaming starts | Whether you can read along, and how long a long answer takes |
| **Inter-token latency (ITL)** | Gap between consecutive tokens, as a distribution | Whether the stream is smooth or stuttering |

AIHWBench reports all four separately and refuses to collapse them into a single
composite score, because the composite hides exactly the trade-off that matters.

## Prefill and decode are different machines

Generating text has two phases with completely different performance
characteristics.

**Prefill** processes your entire prompt at once. It is *compute-bound*: the
GPU does large matrix multiplications over many tokens in parallel, and it is
very good at that. Prefill rates in the thousands of tokens per second are
normal.

**Decode** generates one token at a time, each depending on the last. It is
*memory-bandwidth-bound*: for every single token, the model's weights have to
be read from memory. Nothing about parallel compute helps, which is why decode
rates are one to two orders of magnitude lower than prefill rates on the same
hardware.

This single fact explains most surprising local-LLM results:

- A faster GPU with the same memory bandwidth barely improves generation speed.
- Quantization speeds up generation mostly because there are **fewer bytes to
  read**, not because there is less arithmetic to do.
- An NPU optimised for efficient sustained compute can lose to a GPU with more
  memory bandwidth, at token generation specifically. See
  [NPU vs GPU vs CPU](npu-vs-gpu-for-local-ai.md).
- Spilling even a few layers to system RAM is catastrophic, because system RAM
  bandwidth is far below VRAM bandwidth — the
  [offload cliff](../results/offload-cliff-rtx3080ti.md).

Because prefill and decode scale differently with prompt length, a single
"tokens per second" figure that averages them is a function of how long the
prompt happened to be. On this project's measurements, a long prompt shifted
the blended figure by around 5%, while a generation-dominated workload moved it
by roughly 1% — small, but entirely an artefact of workload shape rather than
of the hardware.

## How many tokens per second do you actually need?

It depends on what you are doing, which is why no honest benchmark hands you a
single threshold:

| Use | What matters | Rough guide |
| --- | --- | --- |
| Reading a streamed answer | Generation tok/s | **7–10 tok/s** keeps pace with a fast reader; 20+ feels instant |
| Chat that feels responsive | TTFT | Under ~500 ms feels immediate; over ~2 s feels broken |
| Code completion (FIM) | TTFT, overwhelmingly | Sub-200 ms or developers turn it off |
| Agentic / tool-calling loops | TTFT × number of turns | A 1 s TTFT across 20 turns is 20 s of pure latency |
| Batch processing | Generation tok/s and total throughput | TTFT is irrelevant |
| Long-document summarisation | Prefill tok/s | Ingest dominates; generation is a rounding error |

The concrete case where the headline number misleads: **a 200 ms TTFT at 30
tok/s feels faster than a 2 s TTFT at 80 tok/s**, for anything interactive.
Nobody perceives the second configuration as 2.7× faster, because they spent
two seconds looking at nothing.

## Why the average hides the stutter

Inter-token latency reported as a mean tells you almost nothing. What people
perceive as a stuttering stream is the *tail*: the p99 gap, not the average one.
A stream averaging 50 ms between tokens with occasional 800 ms stalls reads as
broken, while a steady 60 ms reads as smooth — and the mean says the first is
better.

AIHWBench records inter-token latency as a distribution (p50, p90, p99) for
exactly this reason, alongside the standard deviation and coefficient of
variation of the per-iteration latency.

## Why your number does not match someone else's

A published tok/s figure is a measurement of the model, the quantization, the
prompt, the sampling settings, the context length, the runtime build, the
device, the power profile and everything else running on the machine at the
time. Change any of those and the number changes.

That is not a caveat, it is the central problem:

- **Different quantization** — q4 versus q8 changes bytes read per token.
- **Different context length** — the KV cache grows, and so does the work.
- **Different runtime build** — a CUDA build and a Vulkan build of the same
  version are different programs.
- **Battery versus mains** — laptops cut clocks aggressively on battery.
- **Background load** — a 15% difference measured during this project's own
  development turned out to be background CPU contention.
- **In-process timing versus the serving path** — `llama-bench` measures kernel
  time in-process; a user waits on an HTTP round trip, tokenisation and
  streaming overhead as well. Both are valid. They are not the same number.

This is why every result here carries its full environment, and why comparisons
are [classified before a delta is printed](../comparability-rubric.md).

## Measure it yourself

```bash
aihwbench benchmark --runtime ollama --model qwen2.5:0.5b-instruct-q4_K_M
aihwbench report results/raw/<run_id>.json
```

To see how the numbers move with context length:

```bash
aihwbench sweep --runtime ollama --model <tag> --context-list 1024,2048,4096
```

And to check whether a difference you found is real rather than noise:

```bash
aihwbench self-test
```

## Further reading

- [How to benchmark a local LLM](how-to-benchmark-a-local-llm.md)
- [How much VRAM do I need?](vram-requirements-for-local-llms.md)
- [The offload cliff, measured](../results/offload-cliff-rtx3080ti.md)
- [Glossary](../../GLOSSARY.md) — every metric defined precisely
- [Methodology](../methodology.md)
