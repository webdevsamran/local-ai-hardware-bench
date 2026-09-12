# Choosing a quantization: q4 vs q5 vs q8 vs FP16

Quantization is the single biggest lever on whether a model fits your hardware
and how fast it runs. It is also where local-LLM benchmarking is least honest,
because the speed column is easy to measure and the quality column is not — so
the quality column is usually missing.

This page covers what each level costs you in memory and speed, why the speed
gain comes from where it does, and what this project does about tables that
rank quantizations without measuring output quality.

## What quantization actually changes

A model's weights are stored at some precision. FP16 uses two bytes per
parameter; a 4-bit quantization uses roughly half a byte plus a little metadata
per block. Quantizing rounds the weights into a coarser grid, which:

1. **shrinks the file and the memory footprint** — directly, proportionally;
2. **speeds up token generation** — mostly because there are fewer bytes to
   read, not because there is less arithmetic;
3. **changes the model's output** — by an amount that depends on the model, the
   scheme and the task.

Point 2 is the one people get backwards. Decode is
[memory-bandwidth-bound](tokens-per-second-explained.md): for every token, the
weights get read from memory. Halve the bytes, roughly halve the time spent
moving them. That is the mechanism, and it is why quantization helps generation
speed far more than it helps prefill speed.

## The levels

| Scheme | Bytes/param | 7B size | Typical use |
| --- | ---: | ---: | --- |
| FP16 / BF16 | 2.0 | ~14 GB | Reference quality; the baseline others are measured against |
| q8_0 | ~1.06 | ~7.4 GB | Near-lossless; a sane default when memory allows |
| q6_K | ~0.82 | ~5.7 GB | Very close to q8 at meaningfully less memory |
| q5_K_M | ~0.71 | ~5.0 GB | The usual quality/size sweet spot |
| q4_K_M | ~0.64 | ~4.5 GB | The most-used level; the point where degradation becomes noticeable on hard tasks |
| q3_K_M | ~0.51 | ~3.6 GB | Only when it is this or nothing |
| q2_K | ~0.40 | ~2.8 GB | Usually not worth it — a smaller model at q4 is often better |

The `_K` schemes (k-quants) allocate bits non-uniformly across tensors,
spending more where it matters, which is why q4_K_M holds up better than a flat
4-bit scheme at the same size. `_S`/`_M`/`_L` denote small/medium/large
variants within a level.

**The usual practical answer:** the largest model you can fit at q4_K_M or
better, with room left for the KV cache. A 13B at q4_K_M generally beats a 7B at
q8_0 for the same memory — but "generally" is doing real work in that sentence,
and it is exactly the kind of claim that should be measured on your task rather
than repeated.

## The missing column

Here is the table almost every quantization comparison publishes:

| Quantization | Size | tok/s |
| --- | --- | --- |

And here is why it is not a comparison: **the smaller number is faster because
it is a different model.** Ranking q4 above q8 on tokens per second, with no
quality measurement, is ranking a shortcut above the thing it was a shortcut
for. Of course it is faster. The question was whether it was worth it.

AIHWBench's `quantization` command **refuses to render a speed-versus-quant
table with no quality column**:

```bash
aihwbench quantization --results-dir results/published
```

If the results it is given carry no quality measurement, it says so rather than
printing a ranking that reads as a recommendation. That refusal is deliberate,
and it is the same principle as
[refusing to compare incomparable results](../comparability-rubric.md).

## Measuring quality, not assuming it

To attach a quality column, evaluate the model's output on a task with a
defined scoring rule, on the same machine, and compare to an FP16 reference:

```bash
aihwbench evaluators
aihwbench evaluate --evaluator rouge_l --dataset responses.jsonl
aihwbench evaluate --evaluator multiple_choice --dataset mmlu-subset.jsonl
aihwbench perplexity --model-path <model>.gguf --dataset <corpus>.txt
```

Built-in evaluators cover exact match, token-level F1, ROUGE-L and
multiple-choice scoring; perplexity over a fixed corpus is the cheapest signal
that a quantization has damaged something. The dataset is yours — this project
scores it and, notably, reports an answer it cannot parse as **unknown** rather
than as **wrong**, because scoring a parsing failure as a wrong answer
systematically flatters whichever model happens to format its output the way the
parser expects.

Perplexity is a proxy, not a verdict. A quantization can hold perplexity nearly
constant and still lose the ability to follow a format, call a tool correctly or
stay coherent at long context. If you rely on a specific capability, measure
that capability.

## Do not confuse this with KV-cache quantization

Quantizing the **weights** is what this page is about: it shrinks the model and
speeds up generation.

Quantizing the **KV cache** is a different lever with a different effect — it
buys context length, not speed. Measured across all nine K/V dtype combinations
at 32K context on the reference machine, `q4_0` for both caches cut cache
memory by **71.9%** with a throughput difference inside the noise floor. It did
not make anything faster. And every *asymmetric* configuration was worse than
both symmetric ones around it, two of them losing over 60% of throughput for
less memory saved.

Full study: [KV-cache quantization](../results/kv-cache-rtx3080ti.md). The rule
that falls out of it is short: **use the same dtype for K and V.**

## A decision procedure

1. Work out what fits: [How much VRAM do I need?](vram-requirements-for-local-llms.md)
   or `aihwbench fit`.
2. Start at **q4_K_M** for the largest model that fits with KV-cache headroom.
3. Confirm it fits *entirely* on the accelerator — partial offload costs far
   more than a quantization step does. See
   [the offload cliff](../results/offload-cliff-rtx3080ti.md).
4. If quality is short on your actual task, move up a level before moving to a
   smaller model; if it is still short, try a different model rather than a
   different quantization.
5. If context length is the constraint rather than weights, quantize the KV
   cache symmetrically instead of dropping the weight precision further.
6. Measure the result, including quality. A speed number alone cannot tell you
   whether step 4 was necessary.

## Further reading

- [How much VRAM do I need?](vram-requirements-for-local-llms.md)
- [KV-cache quantization, measured](../results/kv-cache-rtx3080ti.md)
- [The offload cliff, measured](../results/offload-cliff-rtx3080ti.md)
- [Tokens per second, explained](tokens-per-second-explained.md)
- [Methodology](../methodology.md) — why a missing quality column is treated as
  a blocking defect rather than a caveat
