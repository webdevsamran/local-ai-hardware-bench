# KV-cache quantization on an RTX 3080 Ti Laptop

Raw data: [`results/sweeps/sweep-llama.cpp-kvcache.json`](../../results/sweeps/sweep-llama.cpp-kvcache.json)

Nine configurations, every combination of `f16`, `q8_0` and `q4_0` for the K
and V caches, at 32768 tokens of context. llama.cpp build 10578
(`369e1cd61`), qwen2.5-0.5B-instruct-q4_K_M, RTX 3080 Ti Laptop, 8 measured
iterations after warm-up at each point.

The raw file records the model as `sha256-c5396e06...`, because the run was
pointed at a blob rather than a named file. That is not a dead end: it
resolves through [the model zoo](../models/zoo.md) to
`qwen2.5-0.5b-instruct-q4_k_m`, Apache-2.0, obtainable with
`ollama pull qwen2.5:0.5b-instruct-q4_K_M`.

## The short version

**Use the same dtype for K and V.** On this build, `q4_0` for both is
strictly the best configuration measured: 71.9% less cache, the lowest device
memory of the nine, and a generation rate indistinguishable from `f16`.

Every asymmetric configuration is worse than both of the symmetric ones it sits
between, and worse in one of two different ways.

## The measurements

| K | V | cache | vs f16 | device VRAM | tok/s | vs f16 |
|---|---|---|---|---|---|---|
| q4_0 | q4_0 | 108 MiB | −71.9% | 748 MiB | 382.4 | +0.0% ~ |
| q8_0 | q4_0 | 156 MiB | −59.4% | 764 MiB | 145.1 | −62.1% |
| q4_0 | q8_0 | 156 MiB | −59.4% | 764 MiB | 141.5 | −63.0% |
| q8_0 | q8_0 | 204 MiB | −46.9% | 844 MiB | 373.5 | −2.3% ~ |
| f16 | q4_0 | 246 MiB | −35.9% | 854 MiB | 129.7 | −66.1% |
| q4_0 | f16 | 246 MiB | −35.9% | **1810 MiB** | 346.8 | −9.3% ~ |
| f16 | q8_0 | 294 MiB | −23.4% | 902 MiB | 133.0 | −65.2% |
| q8_0 | f16 | 294 MiB | −23.4% | **1858 MiB** | 358.4 | −6.3% ~ |
| f16 | f16 | 384 MiB | — | 1022 MiB | 382.3 | — |

`~` marks a throughput difference inside the 10% run-to-run noise floor this
machine was measured to have: indistinguishable from the baseline, which is
not the same as equal to it.

The cache column is computed from the model's attention geometry as its own
GGUF header states it — 24 layers, 2 KV heads, 64-wide — not estimated. The
device column is `nvidia-smi memory.used` with the server loaded.

## Finding 1: quantizing K alone costs memory — and one flag fixes it

`q8_0` for K with `f16` for V has a **smaller** cache than `f16`/`f16` — 294
MiB against 384 — and used **836 MiB more** device memory. `q4_0`/`f16` is the
same story: 138 MiB less cache, 788 MiB more memory.

The cause is `--flash-attn`, whose default is `auto`, and **auto is not a
synonym for on**. llama.cpp declines flash attention for kernel combinations it
does not cover, and the fallback path allocates far more.

All nine configurations, measured directly on an idle card (0 MiB before and
after), at the default and with flash attention forced on. Raw data:
[`results/measurements/kv-cache-flash-attention-vram.json`](../../results/measurements/kv-cache-flash-attention-vram.json).

| K | V | cache | predicted VRAM | `auto` | `on` |
|---|---|---|---|---|---|
| q4_0 | q4_0 | 108 MiB | 746 | 748 | 748 |
| q8_0 | q4_0 | 156 MiB | 794 | 764 | 764 |
| q4_0 | q8_0 | 156 MiB | 794 | 764 | 764 |
| q8_0 | q8_0 | 204 MiB | 842 | 844 | 844 |
| f16 | q4_0 | 246 MiB | 884 | 854 | 854 |
| **q4_0** | **f16** | 246 MiB | 884 | **1794** | **854** |
| f16 | q8_0 | 294 MiB | 932 | 902 | 902 |
| **q8_0** | **f16** | 294 MiB | 932 | **1842** | **902** |
| f16 | f16 | 384 MiB | 1022 | 1022 | 1022 |

Two things fall out of this table.

**With `-fa on`, the analytic model holds everywhere.** Every configuration
lands within 30 MiB of the size computed from the model's attention geometry —
a consistent offset from compute buffers, not noise, and it is +2 MiB for the
two dtypes with fast native CUDA paths.

**`auto` disagrees with `on` in exactly two of nine cases**, and they are
precisely the two where K is quantized and V is not. Each costs **910 MiB**
more than the arithmetic predicts. Everywhere else `auto` already chooses `on`,
which is why the setting looks harmless until it isn't.

So the practical advice is two lines:

- Use the same dtype for K and V.
- If you use a mismatched pair anyway, pass `--flash-attn on` explicitly, or
  measure what your build's `auto` decided — because it may not be what you
  assumed, and the cost is close to a gigabyte.

This is a property of this llama.cpp build and this GPU, not of KV-cache
quantization as an idea. It is also the kind of thing only measurement finds:
the cache arithmetic says `q8_0`/`f16` saves 90 MiB, and it is right about the
cache and wrong about the machine.

## Finding 2: a quantized V that does not match K costs about 60% of throughput

The four configurations where K and V differ and V is quantized all lose
roughly two-thirds of their generation rate: −62.1%, −63.0%, −65.2%, −66.1%.
The four where K and V agree, or where V is `f16`, all sit within the noise
floor of the baseline.

The rule that fits every point measured is **K and V should have the same
dtype**, with `V = f16` as the only other configuration that keeps full speed —
and that one carries the memory penalty in Finding 1.

## Finding 3: at full context the cache is bigger than the model

This is a 0.5B model. Its weights are 379 MiB. Its `f16` KV cache at the 32768
tokens the model itself declares is **384 MiB** — larger than the weights it
serves. (Both in MiB, as `nvidia-smi` reports: the file is 397.8 MB decimal,
and mixing the two conventions is a 4.9% error in a comparison this close.)

That is what makes this a memory feature rather than a tuning knob. The cache
grows linearly with the conversation while the weights do not, so on any model
small enough to fit comfortably, the cache is what eventually does not.

Put the other way round: one gigabyte of VRAM holds 87,381 tokens of `f16`
cache for this model, and 310,689 tokens at `q4_0`. Three and a half times the
conversation, for memory that measurably costs nothing in speed.

## Why the analytic column exists beside the measured one

Sizing the cache from the header is exact and scales to context lengths nobody
has run. Measuring device VRAM is real but device-wide, and includes whatever
else the card is holding.

Checked against each other at five dtypes, symmetric, by starting
`llama-server` and reading VRAM directly:

| dtype | predicted saving | measured | difference |
|---|---|---|---|
| q8_0 | 180 MiB | 178 MiB | −2 |
| q4_0 | 276 MiB | 274 MiB | −2 |
| q5_1 | 240 MiB | 270 MiB | +30 |
| q5_0 | 252 MiB | 282 MiB | +30 |
| q4_1 | 264 MiB | 294 MiB | +30 |

Two repetitions gave identical readings to the MiB, so these are allocations
rather than noise. The model is exact to 2 MiB for the two dtypes with fast
native CUDA paths and 30 MiB conservative for the other three — because total
VRAM includes compute buffers that vary with cache type, and the cache is not
the only thing that changes when you change the cache.

Neither column is sufficient alone. Finding 1 is invisible to the analytic
column, which says `q8_0`/`f16` saves 90 MiB. Findings about context lengths
nobody has run are invisible to the measured one.

## Reproducing this

```bash
aihwbench sweep --runtime llama.cpp \
  --model-path <your>.gguf \
  --cache-type-k-list f16,q8_0,q4_0 \
  --cache-type-v-list f16,q8_0,q4_0 \
  --context-list 32768 --iterations-list 8 \
  --output-name sweep-llama.cpp-kvcache

aihwbench kv-cache results/sweeps/sweep-llama.cpp-kvcache.json \
  --model-path <your>.gguf
```

## What this does not tell you

**Nothing about output quality.** Quantizing the KV cache changes what the
model computes, and none of these numbers measure whether the answers got
worse. Findings 1 and 2 are about memory and speed only.

**Nothing about other hardware or other builds.** Finding 1 in particular is a
property of a kernel selection, and the version that ships next month may not
have it. The command above is here so you can check your own machine rather
than cite this one.

**Nothing about what `--flash-attn on` does to throughput.** Finding 1's
memory measurements were taken directly on an idle card and are clean. The
matching throughput sweep was interrupted by an unrelated GPU job on the same
machine and has been discarded rather than published, and the machine has not
since been quiet enough to repeat it: the throughput column above is at the
default `auto`. Memory and speed are separate questions here, and only the
memory one has been answered for `-fa on`.

**Nothing about longer contexts than 32768.** The cache column extrapolates
exactly; the device column does not, and Finding 1's penalty was not measured
at other context lengths.
