# Sponsor AIHWBench

**AIHWBench needs hardware more than it needs money, and it needs benchmark
results more than either.**

This is the full version of the appeal summarised in the
[README](README.md#sponsor-this-project). It says what the project is short of,
what each kind of help would concretely unlock, and — just as importantly —
what sponsorship does not buy.

## The situation, stated plainly

AIHWBench publishes **9 benchmark results**. All of them come from **one
laptop**: an Intel Core i9-12900H with an NVIDIA RTX 3080 Ti Laptop GPU.

Meanwhile the repository contains complete, unit-tested backends for AMD ROCm,
AMD Ryzen AI (Lemonade), Qualcomm QNN, NVIDIA TensorRT, Apple MLX, Hailo
HailoRT, ExLlamaV2, Vulkan, SYCL and WebGPU — plus NPU utilisation counters for
Windows and Linux.

**None of those has ever executed on the silicon it targets.** Not because the
work is unfinished, but because the machines are not here. That is the whole
bottleneck, and it is not one that more engineering time solves. (The
Windows ML / DirectML path is the exception that proves it is worth doing: that
one *did* have hardware here, and running it end to end is how accelerator node
placement got verified at all.)

## Ways to help, most valuable first

### 1. Lend or donate hardware

One machine turns a written backend into a measured result. Concretely:

| Hardware | Unlocks | What gets published |
| --- | --- | --- |
| AMD Ryzen AI / Ryzen AI Max laptop or mini PC | `lemonade`, `rocm` backends; AMD NPU telemetry | NPU vs iGPU vs dGPU on one SoC, on battery and plugged in |
| Intel Core Ultra (Meteor Lake / Lunar Lake) | Intel NPU counters; OpenVINO GenAI on NPU | NPU vs iGPU vs CPU on identical silicon, same IR |
| Qualcomm Snapdragon X (ARM64 Windows) | `qnn` backend, ARM64 Windows validation | Hexagon NPU throughput and the x64-emulation penalty |
| Apple Silicon Mac (M-series) | `mlx` backend, unified-memory pressure, `powermetrics` | Unified memory behaviour, which no x86 result can stand in for |
| NVIDIA desktop GPU (any recent) | `tensorrt` backend verification | Desktop vs laptop thermal behaviour on the same architecture |
| Hailo-8 / Hailo-10 module | `hailo` backend | Edge accelerator inference per watt |
| Raspberry Pi 5, Orange Pi, Jetson | ARM SBC coverage | The low end, where perf-per-watt actually decides the design |

Remote SSH access to a machine for a weekend is enough for a first result. So
is mailing a device that has been sitting in a drawer. Details, including what
each target answers and what gets written up:
[docs/hardware-needed.md](docs/hardware-needed.md).

Vendors: [docs/vendor-collaboration.md](docs/vendor-collaboration.md) sets out
the terms — evaluation units are listed publicly with their source, and results
are published whichever way they come out.

### 2. Run one benchmark on the machine you already have

Five minutes, no hardware donation, no code:

```bash
pip install -e ".[dev]"
aihwbench doctor
ollama pull qwen2.5:0.5b-instruct-q4_K_M
aihwbench benchmark --runtime ollama --model qwen2.5:0.5b-instruct-q4_K_M
```

Then open a pull request with the result file. CI checks the schema, the
privacy scan and the integrity hashes for you. Full walkthrough:
[docs/contributing/benchmarking-your-hardware.md](docs/contributing/benchmarking-your-hardware.md).

A result from a machine nobody here owns is worth more to this dataset than
almost any code contribution, because the code is ahead of the data.

### 3. Sponsor maintenance time

[GitHub Sponsors → @webdevsamran](https://github.com/sponsors/webdevsamran),
configured in [`.github/FUNDING.yml`](.github/FUNDING.yml).

*If the Sponsor button is not visible on the repository yet, GitHub Sponsors
enrollment has not completed — this document would rather say so than leave a
dead button to explain itself. Hardware and benchmark results are the more
useful contribution regardless.*

Funded time is spent in a fixed order, which will not be reordered for a
sponsor: **correctness first, hardware coverage second, features third.** The
reasoning is in [SUSTAINABILITY.md](SUSTAINABILITY.md) — a benchmark dataset's
entire value is trust, so anything that saves time at the cost of credibility
is a net loss.

### 4. Fund a specific backend, study or port

If an organisation wants a particular runtime supported, a particular hardware
class covered, or a specific question measured, that work can be funded
directly. Conditions, without exception:

- the funding is disclosed in the pull request and the release notes;
- the methodology is published in full alongside the result;
- the result is published whichever way it comes out.

## What sponsorship does not buy

Written down here so it can be held against the project later:

- **Not** favourable results, or any influence over how a result is framed.
- **Not** removal, delay or embargo of a published number.
- **Not** exclusion of a competitor from the dataset or the leaderboard.
- **Not** advance notice of a result before it is public.
- **Not** a comparability verdict. The classifier applies the same rules to a
  sponsor's hardware as to anything else, and it has no idea who paid for what.

Negative results are published like any other result. A benchmark that can be
bought is not a benchmark.

## Where the money would go

In order, if funding existed:

1. **Hardware acquisition** — buying the machines above outright, so coverage
   does not depend on who happens to lend what.
2. **Maintenance time** — triage, review, keeping backends working across
   runtime releases. This is the cost that quietly kills open-source
   benchmarks: runtimes ship breaking changes and nobody is paid to notice.
3. **Dataset infrastructure** — a DOI-minted archival snapshot, and the
   long-term hosting that makes published results citable years later.
4. **Independent methodology review** — the methodology in this repository
   [has not been externally reviewed](docs/methodology.md), and it says so.
   Paying qualified outside reviewers to attack it would be money well spent.

## Credit

Everyone who has helped — upstream projects, contributors, hardware providers —
is credited in [CREDITS.md](CREDITS.md), [AUTHORS.md](AUTHORS.md) and
[CONTRIBUTORS.md](CONTRIBUTORS.md). Hardware providers are additionally listed
with the machine they provided, because a reader evaluating a result deserves
to know where the machine came from.

If you contributed and are not credited, that is a bug. Please open an issue.
