# Changelog

All notable changes to this project are documented here.
Format based on Keep a Changelog; versioning is SemVer.

## [Unreleased]

### Fixed — the trust layer now fails closed

- **`aihwbench regression` no longer passes a gate that ran no checks.** When
  the baseline and candidate were `NOT_COMPARABLE`, `evaluate_regression`
  returned `INCOMPARABLE` with zero checks executed and the CLI exited `0`. A
  candidate 110x slower than its baseline passed CI, because the runtime name
  had changed — the gate failed open exactly when the environment had drifted,
  which is when it exists to fire. It now exits `EXIT_NOT_COMPARABLE` (3), the
  code `aihwbench compare` already used for the same condition. `--force`
  evaluates the thresholds anyway and still reports the true classification, so
  a forced run cannot be mistaken for a comparable one.
- **The comparison-safety classifier no longer reads absent metadata as
  agreement.** `compare_classification({}, {})` returned `STRICTLY_COMPARABLE`
  — the strongest verdict, on no evidence. `_same(None, None)` is `True` by
  design (two results that both legitimately lack an optional field do agree
  about it), so the fix is a separate presence gate rather than a change to
  that rule: `model.name`, `runtime.name`, `runtime.backend`, `runtime.device`,
  `reproducibility.iterations` and `reproducibility.warmup_runs` must be
  present on both sides, or the verdict is `NOT_COMPARABLE` with a new
  `insufficient_metadata` machine reason. Fields that legitimately do not apply
  to a result — an image-classification run has no prompt, seed or temperature
  — are deliberately excluded, so honest sparse results still compare. No
  published result changes classification.

### Fixed — the auto-tuner no longer recommends noise

- **`aihwbench tune` swept axes that no backend applied.** `threads`,
  `batch_size`, `gpu_layers` and `concurrency` reached
  `BenchmarkConfig.extra` and were dropped there — every backend reads only
  `model_path` and `model_dir`. So `tune --gpu-layers-list 0,16,32,99
  --threads-list 1,2,4,8` ran 32 *identical* benchmarks and reported whichever
  repeat won on run-to-run variance as the optimal configuration, "citing
  measured values". Backends now declare what they actually apply in a
  module-level `TUNABLE_AXES` tuple, and the tuner refuses any axis absent
  from it rather than measuring noise.
- **`gpu_layers` is now a real llama.cpp parameter.** `-ngl` was hardcoded to
  `99` (or `0` for CPU) from `device` alone. It now honours the swept value
  and records it in the result's reproducibility block, so the offload sweep —
  the question behind every "will this fit in my VRAM" decision — measures
  something. The default is unchanged when no value is supplied.

### Added — privacy scrubbing, not just detection

- **`aihwbench redact <result>`** writes a scrubbed copy of a result, and
  `sanitize.redact_object()` / `redact_text()` back it. The scanner could only
  ever *report* a leak; there was no way to remove one. A contributor who
  found an identifier in their result had no supported path to fixing it, and
  a single leak in published data is unrecoverable.
- Redaction placeholders keep **nothing** of the matched value — `redact_match`
  deliberately keeps a short prefix so a CI finding stays recognisable, which
  is the wrong trade for data being published. Every occurrence is replaced
  (the scanner reports only the first per pattern, which is enough to fail CI
  but not enough to scrub), dictionary keys are scrubbed as well as values,
  colliding keys are suffixed rather than dropped, and the command fails
  closed rather than writing a file that still scans dirty.

### Fixed — the published JSON Schema is now enforced

- **`aihwbench validate --formal`** applies the versioned JSON Schema in
  `schemas/`. The machinery existed and correctly failed closed, but nothing
  could reach it: `validate_file` defaulted to `formal=False`, the CLI
  registered no flag, and `jsonschema` was declared in neither the
  dependencies nor the dev extra. The schema downstream consumers code
  against was never checked against the data.
- This is not only defence in depth. `schemas.py` asserts `trust_state` is a
  `str`; the enum of real lifecycle states lives only in the schema file, so a
  schema-2.0 result claiming `"trust_state": "totally_trusted"` passed
  validation completely. It is now rejected.
- `jsonschema` is available as the `schema` extra (matching `parquet` and
  `telemetry`) and is included in `dev`. The CI data-quality job installs it
  and validates every published result formally as well as semantically.

### Fixed — documentation that outran the code

`ROADMAP.md` marked as done several capabilities that exist as library
functions no code path calls, and understated one that works. A project whose
value proposition is honesty about what was measured cannot carry that.

- Sustained-load thermal analysis and the advanced streaming metrics are now
  `[~]` with the specific gap named: `analyze_thermal_stability` has no
  producer because nothing persists the telemetry trace it consumes, and of
  the streaming metrics only `itl_ms` is computed (as a scalar mean, not a
  distribution) while `tpot_ms`, `time_to_second_token_ms`,
  `inter_chunk_latency_ms`, `prefill_latency_ms` and `decode_duration_ms` are
  registered vocabulary that nothing writes. A marker legend now records that
  shipped-but-unreachable is not done.
- Ollama model load time was listed as *not* done in `ROADMAP.md` and as
  unmeasurable in `docs/methodology.md`; it has been measured from the API's
  `load_duration` counter for some time. A null now honestly means "the model
  was already resident".
- `docs/methodology.md` linked issue #21 as an open invitation for external
  review; `ROADMAP.md` records that it was closed because a reviewer cannot be
  summoned by leaving an issue open.
- `docs/results/schema-2.0-proposal.md` declared "not implemented, schema 1.0
  remains authoritative" while `versions.py` sets 2.0 as the current writer
  version. It is now marked as a design note, distinguishing the parts that
  shipped from the parts that did not.
- `reproducibility_score()` now returns `score_percent` alongside `score`.
  `quality.reproducibility_completeness` is validated within [0, 100] while
  the function returned a [0, 1] fraction and nothing bridged them, so a
  producer writing the fraction would record 0.8 for an 80%-complete result
  and pass validation.

### Fixed — the leaderboard now uses the classifier it ships

- **`LEADERBOARD.md` is grouped by comparison safety.** Every result was
  listed in one table under a shared `Gen tok/s` column, guarded by a prose
  footnote saying cross-runtime comparisons need identical workloads. None of
  the six published results is comparable with any other, so the table's own
  shape asserted a ranking the classifier rejects — the first two rows read as
  a 3.25x win between two runtimes measuring different things. Results are now
  grouped into cliques under `comparability.py` (every member comparable with
  every other member, not merely with the first) and ranked only within a
  group. With today's dataset the leaderboard says plainly that no two results
  are comparable yet.
- **`scripts/build_dataset_views.py` no longer overwrites that file.** It
  called `export_dataset` and then rewrote `LEADERBOARD.md` with a second,
  simpler renderer — silently reintroducing two already-fixed defects: one
  `tok/s/W` column mixing generative tok/s/W with graph inf/s/W, and a single
  ranked table of incomparable results. The duplicate generator is gone and
  the HTML view now publishes the perf/W unit too.

### Added — the dashboard is now indexable

- **Real URLs and prerendered HTML.** The dashboard used `HashRouter`, so every
  one of its 20 routes lived under `/#/...`. To a crawler that is a single URL
  with a single title, so no page could rank for its own subject however good
  its content was. It now uses `BrowserRouter`, and `npm run build`
  prerenders every route — including one page per model, per GPU, per runtime
  and per result — to static HTML containing that page's real content and its
  own `<head>`.
- Each route gets a distinct `<title>`, meta description, canonical URL and
  Open Graph/Twitter tags from a single source (`src/lib/seo.ts`) shared by the
  prerenderer and client-side navigation, so the two cannot drift. The home
  page carries schema.org `Dataset` JSON-LD.
- `sitemap.xml`, `robots.txt`, `.nojekyll` and a `404.html` fallback (GitHub
  Pages cannot rewrite server-side, so deep links recover through it).
- **Fixed in passing:** dataset JSON was fetched with a relative path. That
  worked only because `HashRouter` kept the browser at the site root; under
  real paths `data/results.json` would resolve to `/models/data/results.json`
  and 404. It is now anchored to the deploy base.

### Fixed — the dashboard no longer ranks incomparable results

- The web leaderboard assigned a global rank across every result, so the two
  runtimes measuring different things appeared as #1 and #2. Worse, the
  performance-per-watt view ranked six rows 1-6 while mixing `tok/s/W` with
  `inf/s/W` — the same defect fixed for the Markdown leaderboard in 0.2.0,
  still live on the more visible surface.
- `scripts/generate_frontend_data.py` now carries the comparison group, its
  label, its size and the perf/W unit on every leaderboard row, and ranks
  within a group rather than across the dataset. The dashboard renders one
  table per group and states plainly when nothing is comparable. The
  fail-closed dataset validator requires the new fields, so a regression to
  ungrouped data breaks the build rather than quietly restoring a false
  ranking.

### Added — "Will this run on my PC?"

- A new `/will-it-run` page answers the question every local-AI newcomer asks:
  enter VRAM, RAM, model size and quantization, and see the estimated memory
  footprint, how much would spill out of VRAM, and — where the dataset has one
  — the measured result for that configuration, which always beats the
  estimate.
- The estimate is the same arithmetic as `aihwbench fit`, and the two cannot
  drift: `scripts/generate_frontend_data.py` emits the bits-per-weight table,
  the overhead factor **and reference vectors computed by the Python function**
  into `data/constants.json`, and the frontend test suite replays every vector
  through the TypeScript implementation. A change to either side that alters an
  answer fails the build.
- Like the Python original it refuses to guess: an unknown quantization or a
  missing parameter count returns no verdict and says why, rather than
  inventing a bits-per-weight figure.
- The spill percentage is called out deliberately. Measured reports put a model
  fully resident in VRAM at roughly 5x the throughput of the same model with a
  third of its layers offloaded, and that cliff is the single most consequential
  thing a buyer needs to know.

### Added — the energy and thermal analyzers finally have a producer

- **Every result now publishes its telemetry time series.** The summary
  aggregates in `metrics` cannot show a throttling curve or a power spike, so
  `analysis/thermal.py` and `analysis/energy.py` — both shipped, both tested,
  both marked done — could only ever run in tests. The trace is attached to the
  `telemetry` block, downsampled uniformly above 5000 samples with the fact
  recorded, and keeping the final sample because the tail is where throttling
  shows.
- **`runner.run_benchmark` attaches `energy` and `thermal` blocks**, computed
  centrally so all five backends get them and a sixth would too.
- **Idle power is measured before the load starts**, so
  `energy_joules_per_token` is net of the machine's own idle draw — a 200 W
  reading on a card idling at 150 W is a very different result from the same
  reading on one idling at 20 W. Set `idle_baseline_seconds: 0` to skip it; a
  skipped measurement yields null figures rather than an assumed baseline.
- Both blocks are declared in `schemas/result-2.0.schema.json` and validated
  semantically. A metric absent from the schema is one nobody can query.
- `thermal_from_trace` reports only what a trace supports — time to throttle,
  temperature slope, peak and final temperature — and returns the throughput
  degradation fields as null with a reason, because a telemetry trace records
  no per-sample throughput.

### Added — a quality signal on every generative run

Publishing tokens-per-second across quantization levels with nothing said
about output quality walks a reader into a worse configuration while looking
like measured data. Lower precision is faster *and* changes what the model
says; the speed half was measured and the other half was not.

- **Every generative run now records an output-fidelity probe**: whether
  repeated iterations of an identical request produced identical text
  (determinism — at temperature 0 with a fixed seed, anything else means the
  run is not reproducible), and a SHA-256 fingerprint of what was generated.
  Neither needs a reference dataset, so both are measured for free on every
  run. Evaluator scores stay null until a dataset is actually supplied,
  because a fabricated accuracy number is worse than an absent one.
- The generated text is **not** published — unbounded in size and content, and
  a hash answers everything the dataset needs to ask of it.
- **`aihwbench quantization` refuses to emit a speed-only table.** When no
  compared result carries a quality signal it exits non-zero and explains why;
  `--allow-missing-quality` overrides it explicitly.
- The comparison now marks each variant against the **highest-precision
  variant in its family**: `same_output_as_reference` is true, false, or null
  when unknown — never assumed. A q4_K_M run that is fastest but changed the
  output is now visibly different from a q8_0 run that is slower and identical.

### Added — inter-token latency as a distribution

- The Ollama backend records per-chunk arrival times, and `metrics` now carries
  `itl_p50_ms`, `itl_p90_ms`, `itl_p99_ms` and `itl_max_ms` alongside
  `tpot_ms`, `time_to_second_token_ms` and `decode_duration_ms` — schema slots
  and registry entries that previously had no producer at all.
- `itl_ms` was a single mean derived from total eval seconds over token count.
  A mean cannot show a stall, and one long pause partway through a response
  reads far worse than a uniformly slower stream at the same average rate.

### Added — the offload cliff and the KV-cache axis

The largest performance discontinuity in local inference is the point where a
model stops fitting in VRAM: throughput does not taper, it collapses. Where
that happens depends on the machine — PCIe generation, memory bandwidth, what
else is holding VRAM — which makes it the question a crowdsourced benchmark
can answer and a vendor benchmark cannot.

- **`aihwbench sweep --gpu-layers-list 0,8,16,24,99`** maps the offload curve,
  now that `gpu_layers` genuinely reaches llama.cpp. The sweep refuses an axis
  the backend does not apply, for the same reason the tuner does.
- **`aihwbench cliff <sweep.json>`** reports the largest throughput drop
  between adjacent configurations, the layer counts it sits between, and the
  slowdown factor a user would feel. It measures drops between measured
  points; it does not fit a curve or predict an unmeasured configuration.
  Failed runs are excluded and counted, never read as a throughput of zero.
- **KV-cache quantization** is a first-class llama.cpp axis
  (`cache_type_k` / `cache_type_v`, settable independently because K and V
  tolerate quantization differently). Values are validated against what
  llama.cpp accepts and refused before the server starts, rather than failing
  a benchmark partway. Quantizing the cache is a *memory* feature — it buys
  context length or headroom when f16 does not fit — and is documented as one.

### Added — agentic workloads, with the timing actually decomposed

`ROADMAP.md` and this changelog have claimed "deterministic agentic tool-call
benchmarks" since 0.1.0, while `agentic` existed only as a permitted string in
a workload validation set. The claim is now backed by an implementation.

- **`aihwbench agentic --runtime ollama --workload agentic_swe`** runs a
  scripted agent loop and reports **LLM inference time and tool execution time
  separately**, plus the unattributed remainder as `overhead_ms`. An agent
  loop's two halves scale with unrelated things, so a single end-to-end number
  cannot distinguish a slow GPU from a slow tool.
- Two scenarios ship: a software-engineering agent (search and file reads) and
  a data-analyst agent (table summary).
- The tools are **local and deterministic** — they answer from a bundled
  corpus and import no networking module, enforced by a test that inspects the
  module's imports. A benchmark whose results depend on DNS or a rate limit is
  not reproducible.
- The tool sequence is **scripted rather than model-chosen**. Small local
  models emit tool calls unreliably; letting the model drive would measure its
  function-calling accuracy — a real thing to measure, but not hardware
  performance — and would make the loop differ between runs.
- Backends opt in by implementing `generate_text`. A graph runtime that emits
  no tokens is told it cannot run the workload rather than silently skipped.

### Fixed — the compare view now applies the classifier

- **`/compare` renders a verdict, and withholds deltas it should not show.**
  It previously computed a percentage change between *any* two selected runs,
  guarded by a footnote asking the reader to check the workload parameters
  themselves. A percentage between two different experiments is not a
  comparison; it is a number with a `%` sign. The page now shows the
  `STRICTLY` / `CONDITIONALLY` / `NOT_COMPARABLE` verdict with the specific
  reasons, and withholds the delta column when the pair is not comparable.
  Both runs stay visible — the measurements are real, only the comparison is
  not.
- The browser reaches the **same verdict as `aihwbench compare`**. The rule
  tables are generated from `aihwbench/comparability.py` into
  `data/comparability.json`, together with a reference verdict for every
  published pair, and the frontend test suite replays each one through the
  TypeScript implementation. A divergence fails the build rather than showing
  a reader the wrong badge.

### Added — model licences, with their sources

- Every tier in `configs/models.json` now records its licence, **the URL the
  licence was read from, and the date it was read**. An uncited licence is an
  assertion; a cited one is something a reader can check. Verified 2026-09-09
  against each upstream model card.
- The default comparison tier is under the Llama 3.2 Community License — a
  custom commercial agreement requiring acceptance before download — and now
  says so instead of sitting unlabelled beside Apache-2.0 tiers.
- Tests require a licence, a source URL, an ISO check date and a statement of
  commercial terms for every tier, and assert that no model weights are
  committed to the repository. This project distributes no weights, but it
  does tell people to download them, which carries the same obligation to
  state the terms.

### Added — leaderboard filtering, shareable by URL

- The leaderboard now filters by runtime, model, GPU, VRAM tier,
  quantization, device and trust state. Options are derived from the rows
  actually present, so a filter can never offer a value that matches nothing,
  and a facet with only one distinct value is hidden — a control that cannot
  change the result is noise.
- VRAM is bucketed into the tiers cards are actually sold in (8 GB, 12 GB,
  16 GB, 24 GB) rather than exposed in megabytes, so the filter answers "does
  this fit a 12 GB card" instead of asking the reader to do the arithmetic.
- Filter state lives in the query string, so a filtered leaderboard is a
  shareable link and survives a reload. When a combination matches nothing the
  page says so and offers to clear it, rather than showing an empty table.

### Added — a written dispute process, and fingerprints on the CLI

- **[`docs/disputes.md`](docs/disputes.md)** sets out how a published result
  is challenged, reviewed and resolved, before anyone needs it. The moment a
  leaderboard matters, someone will want a result changed; a process written
  in advance lets a decision be checked against a rule rather than a mood.
  It states what can be disputed (anything factual), what cannot ("this makes
  our hardware look bad" is not a defect), that nothing is ever deleted or
  silently edited, that automated flags are review requests and not
  accusations, and how a maintainer conflict of interest is handled.
- **`aihwbench fingerprint`** exposes the experiment fingerprint for a single
  result and duplicate detection across a directory. Both existed in
  `aihwbench/fingerprint.py` and in CI, with no way for a contributor to run
  either before submitting.

### Added — the VRAM cliff, drawn

- The feasibility wizard now plots the share of a model that would sit outside
  VRAM across the range of card sizes people actually own, marking where it
  becomes fully resident and where the reader's own card falls. The shape is
  the point: offload is flat at zero until the model stops fitting, then
  climbs — and that transition is where throughput collapses. A "fits / does
  not fit" verdict cannot show a discontinuity.
- The curve is computed from the same estimate as the headline verdict, so the
  chart and the text cannot disagree, and the caption states plainly that it
  is arithmetic on an estimate rather than measured throughput.
- The chart carries an accessible label naming the fully-resident threshold,
  so a screen reader gets the number rather than "chart", and its draw-in
  animation is behind `prefers-reduced-motion`.

### Added — local ownership against cloud API spend

- **`aihwbench cost`** exposes the cost analysis, which had no CLI surface at
  all, and adds the missing half: a comparison between buying hardware and
  paying a cloud API, with a break-even point in months.
- Power and throughput are read from a **measured result** by default, so the
  electricity figure reflects the machine that was actually benchmarked rather
  than a nameplate rating.
- **Cloud pricing is supplied by the caller and never bundled.** Provider
  prices change frequently, and a stale price table inside a benchmark keeps
  producing confident wrong answers long after anyone thinks to check it — the
  same reason the competitor landscape is fetched rather than hardcoded. A
  test asserts no vendor pricing is present in the module.
- Hardware that never pays for itself at the given volume is reported as
  such, rather than as a break-even figure in the hundreds of months. The
  calculator can and does conclude that the cloud is cheaper.

### Added — a local-vs-cloud page on the dashboard

- `/local-vs-cloud` answers the decision the dataset exists to inform: whether
  buying a GPU costs less than paying per token. It uses **measured** power
  draw and throughput from a published result rather than a nameplate rating,
  and names which result it read them from.
- The reader supplies the cloud price. Nothing is bundled, for the same reason
  as on the CLI side, and the page says so.
- When no published result measured both power and throughput, the page says
  the local running cost is not computable rather than assuming a figure.
- The estimator matches the Python one case for case: reference vectors are
  generated by `compare_local_vs_cloud` and replayed through the TypeScript
  implementation in the frontend tests.
- It also states what it ignores — time, cooling, failure rates, and the fact
  that an API needs no capital up front.

### Fixed — the recommender contradicted its own fit check

- `recommend_configuration` sized weights against the whole memory budget
  while the fit estimator applies a 1.15x allowance for KV cache, activations
  and runtime overhead. The two disagreed: for a 24 GB card it proposed 36.5B
  parameters and then reported, in the same response, that this needed 25.4 GB
  and fitted only against system RAM. It now sizes against the same overhead,
  and a test asserts that a GPU machine's recommendation always fits in VRAM.
- The assumed quantization is named in the output rather than implied by a
  magic constant, and `_fit_example` is now `fit_check` — it is a check, and
  a private-looking key made it easy to ignore.

### Added — recommendations for hardware you do not own

- `aihwbench recommend --vram-mb 24576 --ram-gb 64` describes a machine other
  than the current one. "What could I run on the card I am about to buy" is a
  far more common question than "what can I run on this", and it was
  unanswerable while the system was always detected.

### Added — telemetry beyond NVIDIA, and battery drain

Only NVIDIA GPUs supplied power and thermal context; every AMD, Intel and
Apple result carried nulls. Energy and thermals on consumer hardware is one of
the few things no competing local-AI benchmark measures at all, so a
vendor-shaped hole in it was the wrong hole to have.

- **AMD** via `rocm-smi --json`, **Intel** via RAPL energy counters, **Apple**
  via `powermetrics`. The sampler tries vendors in order and the first that
  answers wins.
- **Battery telemetry** is sampled per point, so a sustained run yields the
  drain rate that laptop owners want and nobody publishes. Tested on the
  reference laptop.
- **Parsing is separated from probing.** Each vendor has a pure parser tested
  against captured output, plus a probe that needs the hardware. That is also
  the honesty boundary: the parsers are verified, the formats are from vendor
  documentation and have **not** been confirmed against a real driver, and
  `vendors.VENDOR_STATUS` records exactly that per vendor — the same treatment
  the compatibility matrix gives untested backends. A parser that meets output
  it does not recognise returns nothing rather than a guess.
- Two traps handled explicitly: ROCm reports both `memory use (MB)` and
  `Memory Allocated (VRAM%)`, so the parser matches on the unit rather than
  reporting 41 MB for a card holding 9.8 GB; and RAPL counts joules rather
  than watts, so a wrapped counter is corrected where the wrap point is known
  and reported as unmeasurable where it is not, never as negative power.

### Added — battery drain during sustained inference

- Results now carry a `battery` block: discharge rate per hour and a projected
  runtime, measured from the telemetry trace. A laptop's throughput is only
  half the story; how long it sustains that unplugged is the other half, and
  no local-AI benchmark publishes it.
- Samples taken on mains power are **excluded rather than averaged in** — a
  charging machine folded into a discharge rate understates it or inverts its
  sign. A run made while plugged in reports that, not a rate of zero.
- A discharge smaller than the battery gauge can resolve (most step in whole
  percent) is refused with the actual figures, rather than reported as a rate
  derived from gauge noise.
- The projected runtime is labelled an upper bound: it extrapolates a constant
  rate from a full charge, and real batteries do worse near empty.

### Added — the statistical policy is now enforced, not just stated

`docs/methodology.md` has said "minimum 5 measured iterations after 2 warm-ups
for published results" since 0.1.0, and nothing checked it. A single
measurement renders as `110.93 tok/s` exactly like a five-iteration median
does, so an under-measured result was indistinguishable from a careful one.

- `statistical_confidence()` labels every result `compliant`, `single_run`,
  `below_policy`, or `unstated` — the last because a protocol that was never
  recorded cannot be reproduced or weighed.
- The leaderboard carries a **Runs** column: a compliant result shows its
  iteration count, anything short of the policy is marked in bold. Results are
  still published — losing real data from contributors whose hardware cannot
  sit through a long run would be worse — but they no longer look identical to
  results that met the policy.
- A run with many iterations but no warm-ups is `below_policy` too: repeating
  a measurement does not remove the cold-start cost baked into it.
- `data_quality_report` reports the label alongside its other checks.

### Added — implausible-value detection, and provenance on every result

- **`aihwbench.plausibility`** flags values that are impossible (more VRAM
  than the card has, utilisation above 100%, a first token arriving after the
  last) or self-contradictory (percentiles out of order, an energy figure that
  does not follow from the power and throughput beside it). It runs in the
  data-quality report and in CI over the published dataset.
- It deliberately asserts **no performance ceiling per hardware class.** "A
  3080 Ti cannot exceed N tok/s" is a claim about hardware this project has
  not measured across the range, and a false accusation costs far more than a
  missed one. Statistical outliers stay the job of `flag_anomalies`, which
  compares against a like-for-like cohort rather than a guessed bound. Every
  finding is a review request, never a fraud verdict.
- **`compute_provenance` is now called by the runner.** It was only ever
  invoked by `aihwbench bundle`, so every result produced by a benchmark run
  carried no hash and could not be checked for tampering — which is why the
  data-quality provenance check failed on all six published results. The hash
  is computed last, so it covers the derived energy, thermal and battery
  blocks too.

### Added — submitted results are validated on the pull request

- A new workflow checks every result a pull request adds and **comments the
  verdict on the PR**: schema and formal-schema errors, privacy findings,
  impossible values, statistical confidence, and how many published results
  the submission can actually be compared with.
- `benchmark-validation.yml` had existed as a reusable workflow with no
  callers, so a submission was checked only by the repository-wide
  data-quality job — which reports into a log nobody reading the PR sees.
- **What blocks is deliberately narrow**: schema errors, privacy findings and
  impossible values. An under-measured run or one comparable with nothing yet
  is reported and merged. Losing a real measurement from a contributor whose
  hardware cannot sit through a long run is a worse outcome than publishing it
  with a label, and "comparable with nothing" is what genuinely new hardware
  looks like.
- The logic lives in `scripts/validate_pr_results.py`, not inline in YAML, so
  it is unit-tested — including that the public comment never echoes a leaked
  identifier, and that every already-published result would pass the gate it
  holds submissions to.

### Added — context-depth scaling curves

A benchmark at one context length is a single point on a curve, and usually
the flattering one. Prefill cost and the KV cache both grow with input length,
and where a machine falls off is what someone needs before committing to a
long-prompt workflow.

- **`aihwbench context-scaling <sweep.json>`** reports prefill superlinearity
  (attention is quadratic, so the flag marks where that stops being a detail),
  the depth at which VRAM stops growing, and the deepest context still above a
  throughput floor the caller sets.
- Memory saturation is explained rather than just reported: VRAM that stops
  climbing on a constrained machine usually means the run began spilling, not
  that it stopped needing memory.
- Nothing is extrapolated. A context depth that was not benchmarked has no
  entry, because the entire reason the curve exists is that it cannot be
  predicted from one point.

### Added — a page per model-on-GPU pair

- `/models/<model>/on/<gpu>` gives every measured model-and-card combination
  its own indexable URL. "How fast is this model on that card" is the query
  people actually type, and it is a different question from "how fast is this
  model" or "how fast is this card" — answering it inside a page about
  something else is the difference between ranking for it and not.
- Routes are generated only for pairs that were actually benchmarked. A page
  promising a number it does not have is worse than no page.
- Results from different runtimes appear together but are explicitly **not**
  ranked against one another, with a pointer to the comparison-safety
  classifier explaining why.

### Added — efficiency frontiers

- `/frontiers` plots throughput against power draw, peak VRAM and time to
  first token, marking the Pareto-optimal points. A leaderboard says which
  result is fastest; a frontier says which are **not beaten on both axes at
  once** — a card that is 10% slower for half the power has not lost, and no
  single ranked column can express that.
- Optimal points are drawn as diamonds as well as in a different colour, so
  the distinction survives for a reader who cannot separate the two hues.
- Results that measured only one axis are excluded and counted, not plotted
  at zero — which would place them at a corner of the chart they did not earn.
- The frontier is computed by the same `pareto_frontier` the CLI uses and
  shipped as data, so the site and the CLI agree on what is optimal.

### Fixed — the prerenderer was missing two data files

`comparability.json` was never added to the prerenderer's list when the
compare view started needing it. That does not crash: `seedDataset` bypasses
the runtime validator, so the page renders its *empty state* into the static
HTML and the deployed site ships wrong content. A test now checks the
prerenderer loads every file the browser loads.

### Added — cold-start vs warm load time

- Results now carry `cold_start_ms`, `warm_load_ms` and
  `cold_start_penalty_ms`. The first request after a model is not resident
  pays to load it; every request after does not, and "how long until this is
  usable" is a real part of using a local model that throughput benchmarks
  ignore entirely.
- The measurement came free: warm-up runs were being discarded outright, and
  the first warm-up is the *only* run that can have loaded the model. It is
  still excluded from the published throughput metrics — it is now simply read
  before being dropped.
- A model that was already resident reports the cold figure as **absent, not
  zero**: the run did not measure a fast load, it measured no load at all.

### Added — the dataset is a documented, versioned API

The generated JSON files were already a public API: served from a stable path,
fetchable by anyone, and people will build against them whether or not they
are described. `web/public/api/openapi.json` turns that accident into a
contract.

- Eleven endpoints, each carrying an explicit **stability** marker. Result
  documents, hardware, models, runtimes and the comparability rules are
  `stable` and change only through a versioned schema bump with a migration.
  The dashboard's convenience views are marked `unstable` and may be reshaped.
- The leaderboard endpoint states plainly that its rank is **within a
  comparison group, never across the dataset** — a consumer reading it as a
  global ranking would make exactly the mistake this project exists to prevent.
- Generated from the real files, so the description cannot claim a shape they
  do not have, and checked in CI. Tests assert both directions: nothing
  documented is missing, and nothing served is undocumented.
- No server is implied. A benchmark dataset behind a running service stops
  existing when someone stops paying for it; a set of files in a public
  repository does not.

### Added — bundle signing is reachable

- `aihwbench bundle --sign` signs a bundle with cosign and writes the
  signature beside it; `aihwbench verify-bundle --verify-signature` requires a
  valid one rather than accepting matching checksums alone.
- `sign_bundle_cosign` and `verify_bundle_cosign` had shipped with no callers
  outside tests, so a bundle could carry checksums and never a signature.
  Checksums only show a bundle is internally consistent — anyone who edits the
  contents can recompute them. The signature is the part that carries
  authorship.
- Signing without cosign installed exits `EXIT_CONFIGURATION_ERROR` and says
  the bundle was still written and is still valid. The artifact is fine; the
  environment is not, and conflating the two would be wrong.
- A bundle whose checksums pass but whose signature fails verification is
  reported as **invalid**. That combination is precisely what signature
  checking exists to catch.

### Added — package-manager manifests, generated from the artifact

- The release workflow now emits Homebrew, Scoop and winget manifests built
  from the sdist it just produced. Install friction directly suppresses
  submission volume, which is this project's real bottleneck — the framework
  exists, the hardware coverage does not.
- **Generated, never hand-written.** Each manifest carries a version and the
  SHA-256 of one specific file; typing those by hand produces a manifest that
  installs nothing, or silently pins an old release. Tests assert the digest
  matches the real archive, that all three manifests agree on version and URL,
  and that two sdists in the directory is an error rather than a guess.
- winget's uppercase digest requirement is handled, because a lowercase one is
  rejected at submission rather than at build time.

## [0.2.0] - 2026-09-07

### Changed — BREAKING
- **The import package is `aihwbench` (was `benchmark`).** The console script
  and `python -m aihwbench.cli` are unchanged; update external imports from
  `benchmark.*` to `aihwbench.*`. This landed before any release, so no
  published version is affected — it is called out because the CHANGELOG
  described it as unreleased for two weeks.

### Fixed — measurement integrity
- **Performance-per-watt now publishes its unit.** The value is tok/s/W for
  generative runtimes and inf/s/W for graph runtimes, but the metric registry
  declared a single unit, so `results/dataset/LEADERBOARD.md` ranked both in
  one column and every per-run report printed "(tok/s/W)" — including runs
  that produced zero tokens. The unit now travels with the value and the
  leaderboard states that the two are not comparable. No measurement changed.
- Leaderboard values were published to 16 significant figures from a division
  of two 2-decimal inputs; now rounded to measured precision. Missing metrics
  render as "not measured" rather than the literal "None".
- `ROADMAP.md` was committed with a UTF-8 BOM and mojibake, so GitHub rendered
  every track heading as "## Track 1 â€" Benchmark Core".
- Documentation reconciled with the code: three documents described the trust
  states three different ways (none matching `trust.py`), a duplicated schema
  file advertised another file's `$id`, and `README` documented an
  `experiments/` workflow that shipped no example manifest.

### Added
- `AGENTS.md`, `experiments/` with a runnable manifest, and
  `docs/methodology-review.md` — a review packet with five specific questions,
  since the methodology has never been externally reviewed (#21).
- A PyPI publish job in `release.yml`, which previously had none, so
  `pip install aihwbench` could not have worked from any tag.

### Changed
- **Schema writer emits 2.0 via `aihwbench.versions`** — the single
  authoritative source for package/schema/protocol versions. All backends
  stamp `CURRENT_SCHEMA_VERSION`; readers still accept 1.0 and migrate
  forward. Migrations are pure (deep-copy, canonical `aihwbench.migrations`
  migrator name); `domain` parsing is strict by default (MISSING/null/
  INVALID separated, wrong-typed values no longer silently become `None`);
  anomaly detection cohorts results by comparability profile
  (protocol/runtime/model/device) with robust median/MAD statistics and a
  minimum cohort size.

### Added
- **Fingerprint algorithm v2** (`FINGERPRINT_ALGORITHM_VERSION`): result
  identity now includes `protocol_version`, the typed workload block,
  runtime version, OS and RAM, distinguishing distinct machines/systems
  that share a CPU string; algorithm version is embedded in every digest.
- **Capacity methodology pinned**: `sustainable_concurrency()` extracted
  as a pure, documented rule (min p95 across zero-error measured levels)
  with dedicated tests; docstring no longer ambiguous about "lowest".
- Web runtime validators (`web/src/lib/validate.ts`) with Vitest contract
  tests; `index.json` fetched once instead of twice; `trust_state` exposed
  in TypeScript types; CI adds a dependency-review job and a raised
  coverage gate; ADR-0008 (HashRouter) records the routing decision.
- mypy strict mode applied module-by-module (`versions`, `fingerprint`,
  `capacity`).

### Changed
- Generated-data hardware fingerprint is now versioned (`hwfp-v2-…`),
  normalized and includes OS/RAM; regenerated `web/public/data`.
- SECURITY.md now reflects reality: release SBOM is generated *and
  verified*; Dependabot alerts/fixes and secret scanning enabled;
  Dependency Review advisory until the repo's Dependency graph toggle is
  flipped (UI-only).

### Fixed
### Fixed
- **Audit remediation (Phase A — P0 data-integrity/security):** see
  `docs/audit/REPOSITORY_AUDIT.md` for evidence on every item.
- Trust states unified on one canonical lowercase lifecycle
  (`unreviewed→verified/community_validated→flagged→invalidated/superseded`);
  legacy aliases and `reproducibility.trust` mapping preserved; the dataset
  export no longer mislabels verified results as `UNVERIFIED` (#trust).
- Open-loop loadgen records scheduled submit time (real queue latency);
  gamma arrivals now honor `rate_per_second` independent of shape.
- Telemetry platform-safe: Windows `ctypes` fallback guarded; per-metric
  `scope`/`source`/`device` provenance + timestamped raw trace exposed.
- `.aihwbench` verification is fail-closed: unmanifested members,
  malformed/duplicate manifest entries, oversized/high-ratio archives all
  invalidate the bundle.
- Privacy scanning unified (one recursive structured scanner in
  `sanitize.py`); findings are redacted — full secret values are never
  echoed; `quality.py` delegates.
- Backends:
  - llama.cpp uses usage-object token counters (never SSE chunk counts);
    port is OS-allocated (ephemeral) with robust cleanup.
  - LM Studio separates engine-counter metrics from client wall-clock
    rates via `metric_source`.
  - ONNX Runtime / OpenVINO feed **all** declared inputs, normalize
    dtypes, record model SHA-256 and a `graph_inputs` manifest.
- Metric vocabulary unified: canonical `METRIC_REGISTRY` in
  `metrics.py`; alias-tolerant readers in SDK/domain/exporters; the
  aggregator and CSV/SQLite/Markdown exporters emit canonical names.
- Publishing/dataset pipelines fail closed: `export --strict`, snapshot
  integrity, frontend data generation validates schema and aborts (exit 2)
  on any corrupt file.
- CI/release gates fail closed: the reusable validation workflow's
  `verdict=fail` now fails the job (configurable); regression candidate is
  selected deterministically; the release SBOM is mandatory and verified.
### Earlier unreleased work
### Changed
- **Package renamed:** the import package is now `aihwbench` (was
  `benchmark`). The console script and `python -m aihwbench.cli` behave
  identically; update any external imports from `benchmark.*` to
  `aihwbench.*`.

### Added
- CLI restructured into a package (`aihwbench/cli/`) with focused
  command-group modules; all subcommands and exit codes preserved.
- **LM Studio backend** (`--runtime lmstudio`): benchmarks via its
  OpenAI-compatible local server with streamed TTFT measurement; token
  counts come only from reported usage — never estimated.
- **Apple MLX backend** (detection): honest HARDWARE_REQUIRED /
  CONFIGURATION_REQUIRED states off Apple Silicon.
- **`aihwbench score` command** + `score.py`: optional composite score
  with fully published reference points, weights and component breakdown;
  renormalized when telemetry is missing, refused when throughput is
  missing. Explicitly labeled heuristic.
- New suite profiles: `rag.json` (grounded retrieval-style query) and
  `long_context.json` (8k-context comprehension).
- Makefile task runner mirroring CI commands; Dependabot now also covers
  the `web/` npm ecosystem.


### Added — top-50 platform transformation (phases 1–7)
- Collision-resistant UUID-backed run IDs with regression tests (#1).
- Corrected Linux physical-core counting and richer CPU topology
  detection with synthetic fixture tests (#2).
- Typed workload engine and registry under benchmark/workloads/ with
  id/version/input-output profiles/capability requirements (#3) and the
  aihwbench.workloads entry-point plugin API (#4).
- Parameter sweep engine (aihwbench sweep) producing structured JSON+CSV
  matrices (#5); declarative experiment manifests in JSON/TOML/YAML via
  aihwbench run (#6).
- Load generator (benchmark/loadgen/) with constant-rate, closed-loop,
  Poisson, Gamma and burst arrivals, deterministic seeds, scheduler,
  workers and recorder (#7).
- Capacity ladder (aihwbench capacity): req/s, throughput, p95/p99
  latency, TTFT, error rate, sustainable concurrency (#8).
- Advanced streaming metrics: TPOT, ITL, time-to-second-token,
  inter-chunk latency, prefill latency, decode duration, queue latency
  where measurable (#9).
- Expanded statistics: median, p50-p99.9, min/max, stddev, coefficient of
  variation, optional bootstrap CIs that refuse to fabricate confidence
  from too few samples (#10).
- Prefill/decode separated workloads and reporting (#11), standardized
  ISL/OSL length profiles (#12), weighted mixed traffic distributions
  (#13), growing-context multi-turn workloads (#14), deterministic
  agentic tool-call benchmarks (#15).
- Accuracy/evaluation framework with evaluator abstractions and small
  redistributable datasets (#16) plus the aihwbench.evaluators plugin API
  (#17); performance-quality Pareto frontier without opaque composite
  scores (#18).
- Quantization comparison (aihwbench quantization) across speed, TTFT,
  memory, power and optional quality (#19); model-fit estimator
  (aihwbench fit) clearly labeled as estimate vs fact (#20);
  recommendation engine with evidence and uncertainty (#21); bottleneck
  analyzer with explicit reasoning rules (#22); thermal stability
  analysis (peak vs steady-state, time-to-throttle) (#23).
- Energy metrics (joules/request, joules/token) with telemetry source and
  measurement tier where hardware supports it (#24); optional idle
  baseline power separating gross vs incremental power (#25); user-
  supplied cost/TCO analysis — never scraped prices (#26).
- Normalized hardware identifiers/aliases without PII (#27); device
  topology detection (PCIe, NUMA, instruction sets) (#28); multi-GPU
  representation with per-device telemetry (#29); NUMA-aware metadata
  (#30); runtime showdown comparisons (#31); runtime/driver regression
  history tracking (#32).
- env-diff (#33), reproduce prerequisite checks (#34), transparent
  reproducibility completeness score explicitly not a validity claim
  (#35), portable .aihwbench bundles with SHA-256 integrity (#36),
  provenance hashing + tamper verification (#38), thin cosign sign/verify
  interfaces that report unavailability honestly (#39).
- schema_version/protocol_version/workload_version fields with migration
  machinery preserving readers for published schema 1.0 results (#40);
  versioned dataset snapshot manifests (#41); invalidation records that
  preserve history with reasons and replacement references (#42);
  machine-readable data-quality checks (#43); z-score anomaly flags
  requesting manual review, never asserting fraud (#44).
- Public Python SDK (benchmark/sdk.py): BenchmarkResult, SystemInfo,
  RuntimeInfo, ModelInfo, MetricSet, Workload, BenchmarkRunner,
  RegressionReport (#46). Exporter plugin architecture with
  aihwbench.exporters entry points; JSON/CSV/Markdown/SQLite built-ins;
  optional Parquet behind an extra (#47). Reusable benchmark-validation
  GitHub workflow with machine-readable verdicts (#48). self-test command
  measuring timer resolution, telemetry availability, background load,
  battery vs AC, power profile, thermal state, runtime readiness (#49).
  Auto-tuner (aihwbench tune) identifying fastest/most-efficient/
  lowest-memory/balanced Pareto configurations (#50).
- Production React + TypeScript dashboard under web/: 20 routes
  (leaderboard, hardware/runtime/model/result explorers and details,
  compare, dataset explorer, methodology, compatibility matrix, docs,
  community, hardware-needed, planned enterprise/certification pages,
  about with creator attribution, 404); dependency-free SVG charts;
  accessible sortable/paginated tables; URL-shareable filters; trust
  badges; light/dark themes; skeleton/empty/error states; downloadable
  result JSON. Deterministic static dataset generation
  (scripts/generate_frontend_data.py) with CI freshness enforcement.
- CI additions: frontend lint/test/build job, generated-data freshness
  job, Pages deployment rebuilt for the Vite bundle.

### Added
- Formal JSON Schema (schemas/result_schema.schema.json, draft 2020-12)
  alongside the dependency-free semantic validator.
- Strengthened validation: run-id format, ISO-8601 UTC timestamps,
  metric range checks (non-negative; utilisation 0-100), reproducibility
  typing, iterations array checks, new optional metrics (p90/p99 latency,
  inferences/s throughput, energy per token).
- Comparison safety classifier (benchmark/comparability.py):
  STRICTLY_COMPARABLE / CONDITIONALLY_COMPARABLE / NOT_COMPARABLE with
  machine-readable reasons; compare refuses deltas for incompatible
  workloads unless --force (exit code 3).
- Backend plugin API v1: BACKEND_API_VERSION, BenchmarkMetadata, and
  third-party registration via the aihwbench.backends entry-point group.
- CLI: stable exit-code contract, doctor command, suite command with
  versioned profiles under configs/suites/, export command generating
  index.json / dataset.csv / LEADERBOARD.md from published results.
- Trust states (VERIFIED / COMMUNITY_VALIDATED / UNVERIFIED) and a
  documented community result submission pipeline.
- Fail-closed privacy scanner (benchmark/sanitize.py) covering MACs,
  IPs, SSNs, tokens, home paths, serials.
- Deterministic result fingerprints + duplicate detection.
- Statistical expansion: median/stddev/min/max latency, TTFT and TPS
  dispersion, per-metric coverage counts.
- Community infrastructure: issue templates, PR template with honesty
  checklist, CODEOWNERS, Dependabot, SUPPORT.md.
- Governance files: NOTICE, AUTHORS.md, MAINTAINERS.md, CONTRIBUTORS.md,
  GOVERNANCE.md, TRADEMARKS.md, BRANDING.md, ARCHITECTURE.md,
  docs/certification.md, docs/enterprise/overview.md,
  docs/guides/plugin-api.md, docs/results/submission-pipeline.md.

### Changed
- CI hardened: GitHub Actions pinned to immutable commit SHAs;
  ruff format --check no longer masked by '|| true'; test matrix now
  covers Python 3.10-3.13 on Ubuntu, Windows and macOS; result-schema
  job reports the number of validated files.
- Creator attribution added across CITATION.cff, pyproject metadata,
  README, NOTICE and AUTHORS.md (@webdevsamran - Original Creator).
- README restructured with audience navigation, comparison-safety and
  trust-state documentation.
- ROADMAP rewritten around nine parallel tracks.

### Fixed
- Cross-runtime comparisons no longer silently produce delta tables:
  differing runtime/backend/device/model identity is classified
  NOT_COMPARABLE (previously only model name was checked).
- llama.cpp backend executed end-to-end on CUDA (b10578 prebuilt build):
  TTFT 14.52 ms, 360.87 tok/s generation, 13.49 tok/s/W; result published.
- ONNX Runtime real benchmarking backend: model load time, latency
  percentiles, inferences/s throughput, telemetry; execution-provider
  mismatch now fails loudly instead of silently falling back.
- OpenVINO real benchmarking backend with CPU and GPU device support;
  dynamic input shapes pinned deterministically.
- Five new validated published results: llama.cpp CUDA, ONNX Runtime CPU,
  ONNX Runtime DirectML, OpenVINO CPU, OpenVINO GPU.

### Changed
- CLI `--model` is now optional; per-runtime argument validation
  (`--model` for ollama, `--model-path` for file-based runtimes).
- README runtime table and compatibility matrix updated to reflect six
  genuinely tested runtime/device combinations.

## [0.1.0] - 2026-08-22

### Added
- Cross-platform hardware detection: OS, CPU, RAM, GPU (+VRAM/driver),
  NPU enumeration, platform name — sanitized output.
- Runtime detection for 9 runtimes with explicit status states
  (AVAILABLE, NOT_INSTALLED, NOT_AVAILABLE, UNSUPPORTED_PLATFORM,
  HARDWARE_REQUIRED, CONFIGURATION_REQUIRED).
- Ollama backend: real streamed benchmarking over the local HTTP API
  (TTFT, prompt/generation tok/s from runtime statistics).
- llama.cpp backend: managed `llama-server` lifecycle + OpenAI-compatible
  streaming benchmarking with SHA-256 model checksums.
- Background telemetry sampler: peak RAM/VRAM, CPU/GPU utilization,
  temperature, power draw (psutil / nvidia-smi), performance-per-watt.
- Result schema 1.0 with dependency-free validation.
- Reproducibility block in every result (prompt, sampling params, seed,
  context length, warm-up/iterations, power profile, git commit).
- CLI: `system-info`, `detect`, `runtimes`, `benchmark`, `validate`,
  `report`, `compare`.
- Comparison tooling with comparability warnings.
- Test suite (35 tests) and GitHub Actions CI.
- Documentation: methodology, compatibility matrix, vendor collaboration,
  hardware coverage gaps, roadmap.

[0.1.0]: https://github.com/webdevsamran/local-ai-hardware-bench/releases/tag/v0.1.0