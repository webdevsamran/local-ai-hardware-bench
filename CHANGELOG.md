# Changelog

All notable changes to this project are documented here.
Format based on Keep a Changelog; versioning is SemVer.

## [Unreleased]

### Added — OpenVINO GenAI: one model, three kinds of silicon

- **The `openvino_genai` backend measures instead of refusing.** It was
  detection-only: it could tell you OpenVINO GenAI was installed and then
  raised on `run()`, which was the right thing to do while no measured path
  existed. It drives a real `LLMPipeline` now.

  It earns its place by being the only backend here that can hold the model
  constant across an Intel CPU, an Intel iGPU and — on recent OpenVINO
  releases — a discrete GPU. Every other LLM runtime in this project targets
  one vendor's silicon, so "is the iGPU worth using?" was a question the
  dataset could not answer.

- **Both TTFT figures, because they measure different things.** The pipeline
  reports its own; the streaming callback reports what the caller waited for.
  Detokenisation sits between them. Reporting only the runtime's flatters it,
  and reporting only the caller's hides where the time went.

- **Quantization is read out of the IR, not inferred from the path.** NNCF
  stamps its settings into `rt_info` at conversion time, so a result carries
  `int4_asym` with `group_size: 128` — what the compressor applied — rather
  than whatever someone named the directory. The optimum-intel version and the
  OpenVINO release the IR was built with come along too: this model's IR was
  built with 2025.2 and run on 2026.3, which is a difference worth being able
  to see.

- **`--device auto` is refused.** OpenVINO's AUTO plugin picks a device when it
  compiles and `LLMPipeline` offers no way to ask what it picked. Since
  `runtime.device` is in the comparison-safety classifier's strict set, a guess
  there would not stay local — the classifier would go on to rank a silently-CPU
  result against a GPU one. The error names the visible devices instead.

### Fixed — OpenVINO detection re-initialised the GPU plugins every time

- **One `Core` for the process, not one per call.** Constructing an OpenVINO
  `Core` costs about a millisecond, but the first `get_available_devices()` on
  each one costs ~900 ms, because that is where the GPU plugins initialise.
  Both OpenVINO backends built a fresh `Core` on every detection, so each paid
  it again: ~220 ms per `detect()`, twice over, on every `aihwbench detect`,
  `runtimes` and `doctor`.

  Two module-level caches would not have fixed it — the cost is per `Core`, so
  the two backends keeping their own would still enumerate twice. It has to be
  one `Core` for the process, and it now lives in `backends/base.py` where both
  reach it. Repeated detection went from ~440 ms a pair to 0.1 ms.

### Fixed — a shipped feature the docs called planned

- **Release artifacts have carried signed build provenance for some time**, and
  nothing said so. `docs/security/supply-chain.md` listed attestation under
  "Planned" and the roadmap box was unticked, while
  `actions/attest-build-provenance` was signing every wheel and sdist in the
  release workflow. Understating what exists is a smaller failure than
  overstating it, and it still leaves a reader unable to tell what a download
  actually carries.

  The docs now say what it is and how to check it, which was also missing: a
  checksum proves the bytes did not change in transit and says nothing about
  where they came from, since anyone can publish a checksum for anything.
  `gh attestation verify` is the half that ties an artifact to the workflow run
  that built it.

- **The roadmap understated itself twice in one pass.** Artifact attestation
  and the independent report template were both shipped and both unticked; the
  template has nine filled-in reports sitting beside it. Corrected, and worth
  recording as a pattern: this project audits hard for features claimed but not
  built, and had not been looking in the other direction.

- **Nothing guarded the attestation step.** It is six lines in a workflow that
  only runs on a tag, so a removal would go unnoticed until someone tried to
  verify a release and found nothing there — after the unattested artifacts
  were already published. A test now asserts the step exists, is pinned to a
  commit, covers both the wheel and the sdist, runs before upload, and that the
  workflow holds the two permissions it needs to sign at all.

### Fixed — a zero that meant "not measured"

- **GPU metrics that describe a different GPU are dropped.** Telemetry reads
  `nvidia-smi`, which reports the NVIDIA card whatever the run was actually on.
  A run on the Intel iGPU therefore came back with `peak_vram_mb: 0.0` and
  `avg_gpu_util_percent: 0.0` — both true statements about an idle NVIDIA card,
  and both reading as "this run used no graphics memory". The iGPU allocates
  from shared system RAM, where that tool cannot see it at all.

  The numbers go and the reason stays, in `metrics.metric_source`. A CPU run
  keeps them, because there the zeroes are a correct statement about this run.

  The first version of the device comparison would have thrown away the good
  case: OpenVINO says "NVIDIA GeForce RTX 3080 Ti Laptop GPU (dGPU)" where
  nvidia-smi says the same name without the suffix, so the card failed to match
  itself and the one genuine VRAM measurement available was discarded. A test
  caught it.

- **Generation throughput counted prefill as generation.** `eval_seconds` used
  the pipeline's `get_inference_duration()`, which counts every forward pass
  the request made — prefill included — so the resulting rate described work
  that was partly not generation. Decode is now tokens times the runtime's own
  time-per-output-token, with the total kept alongside.

  The definition matters more than the size here, and the size was measured
  rather than assumed: within about 1% either way when generation dominates
  (33-token prompt, 64 generated) and 5% when it does not (994-token prompt,
  8 generated). Neither figure is pure decode — TPOT comes from the generate
  loop and carries sampling and detokenisation with it — but it is the one
  that answers "how fast do tokens arrive".

- **A compiled pipeline is cached per model and device.** Compiling an IR takes
  around 2 seconds on a CPU and 17 on a discrete GPU, and an agentic workload
  calls `generate_text` once a turn — so the backend was nominally able to run
  those workloads and far too slow to actually use.


### Fixed — every prerendered page was being thrown away on load

- **The client called `createRoot`, not `hydrateRoot`.** `createRoot` discards
  whatever is in the container and renders from scratch, so 53 pages of
  prerendered HTML were built, shipped, painted and then destroyed on every
  single visit. The static output was doing its job for crawlers and nothing
  at all for readers: the server's content appeared, React wiped it, and the
  page fell back to a loading skeleton until 14 JSON files arrived.

  Nothing caught it because nothing looked. Every frontend test rendered
  components directly; none asked whether the server's markup and the client's
  first render agree — which is the only question hydration turns on. This is
  the project's commonest defect class in its purest form: built, tested,
  documented, and not wired into the path that matters.

  It shows up as a measurement, not an opinion: `renderToString` emits
  `<!-- -->` comment nodes between adjacent text nodes and a client render
  emits none. The live pages had zero of the server's 75.

- **The Suspense boundary was inside the browser-only branch.** Once hydration
  was switched on, every page still failed, and the reason is the kind that
  survives review: a boundary that never suspends renders no DOM, so wrapping
  only the client's tree looks free. Hydration does not compare DOM, it
  compares elements — the client had a `<Suspense>` where the server had the
  route's `<div>`. The boundary is now outside the branch, which costs the
  prerenderer nothing because its components are all preloaded.

- **Hydration also needs the data and the route's own chunk in hand.** Absent
  either, the first client render is a skeleton or the route fallback, neither
  of which is what the server sent. The entry point awaits the dataset and
  exactly one route chunk — `preloadRoute`, not `preloadRoutes`, so the code
  splitting survives — and `lazyRouteElements` renders an already-resolved
  module directly, because `React.lazy` suspends on first render even when the
  chunk is in memory.

- **A test that agreed with itself.** The first version of the hydration test
  passed against the broken code. `useEager()` decided the branch with
  `typeof window === 'undefined'`, and jsdom defines `window` — so the
  "server" render in the test took the browser's branch and was compared to
  itself. It is a prop now, passed explicitly by `entry-server.tsx`, and the
  regression was reintroduced to confirm 4 of 8 cases fail without the fix.

- **Four numbers were formatted in the host's locale.** `toLocaleString()`
  with no argument formats with the build machine's locale on the server and
  the reader's in the browser, so `32768` renders as `32,768` for whoever
  built the site and `32.768` for a reader in much of Europe — a hydration
  mismatch nobody who builds it can reproduce. A test now rejects the bare
  call anywhere in `web/src`, alongside one for `Date.now()` and
  `Math.random()` in render paths.

### Fixed — touch targets the test said were fine

- **The test was `assert "44px" in css`.** The string was there, on form
  fields and filter chips, and nothing checked it reached anything else.
  Measured in a browser at 320px: the column sort buttons were 13x23, the
  navigation toggle 66x23 — and below 900px that toggle is the only way to
  reach the navigation at all — the theme toggle 67x33, the header home link
  124x29. The sort buttons were under WCAG 2.2's 24x24 floor, not just under
  this project's own 44px bar; `all: unset` had stripped every default the
  button had, size included, leaving a target as wide as its label.

  The sort control is now the whole header cell rather than a 44px-tall
  button, which would have pushed every header row down by half its height on
  desktop too. The cell was already 43px; it costs two pixels of padding and a
  pseudo-element.

  `.field input` claimed 44px through `padding: 11px 12px` and a comment
  asserting the arithmetic — true for the current font size and border width
  and silently false after either changes. It states a minimum now.

  The test reads the effective `min-height` per control and compares it
  numerically, so deleting a rule fails it. Two controls stay under 44 and the
  reasons are recorded: links inside prose, which WCAG 2.2 exempts, and the
  sort button's *width* in the narrowest column, where a wider target would
  overlap the next column's and sort the wrong one.

### Added — an accessibility gate, and the site's first favicon

- **`npm run a11y` runs axe-core over all 54 prerendered pages** and fails the
  build on a violation. It reads `dist/`, not a mocked component render,
  because the prerendered HTML is the artifact a crawler indexes and a screen
  reader receives before hydration. CI runs it after the build. Six seconds.

  It found that the nine embed pages had no `<main>` and no `<h1>`. The embed
  shell drops the site chrome deliberately — the card sits inside someone
  else's article — but it dropped the landmark and the heading with it, and an
  iframe is its own document, so a reader entering one inherited no structure
  at all. Fixed at the source, and the heading is pinned to the card's own
  font size so an accessibility fix did not ship as a visible redesign.

  The report names what it could *not* check. jsdom has no layout engine, so
  `color-contrast` cannot return a verdict and is listed as unevaluated rather
  than folded into the pass count — "we did not look" and "we looked and it
  was fine" are different claims. Two rules that error under jsdom but need no
  layout (`landmark-one-main`, `page-has-heading-one`) are checked directly
  instead of being written off; they are the two that caught the embed bug.

- **A favicon**, which the site had never had. Every page load requested
  `/favicon.ico`, got a 404, and logged a console error — Lighthouse scored
  Best Practices 96 on an otherwise clean page because of it. The SVG follows
  the reader's theme; `favicon.ico` is the fallback for browsers that ignore
  SVG icons and is generated by `scripts/generate_favicon.py --check`, because
  a committed binary with no source is a thing nobody can edit later.

- **Lighthouse measured and recorded** in `docs/research/dashboard-performance.md`:
  100 across performance, accessibility, best practices and SEO on four
  routes, with CLS at 0. Recorded with its conditions, including that the
  machine was at 38% CPU — above this project's own 20% publish threshold —
  and why that makes a perfect score a stronger claim rather than a weaker
  one. It is not a CI gate, and the file says why.


### Added — the dashboard quality bar: code splitting, three chart shapes, print

- **Routes are code-split.** 34 routes shared one 372 KB bundle, so someone
  landing on `/about` downloaded the offload-cliff chart, the TCO calculator
  and the KV-cache page before anything appeared. The entry is now 252 KB
  across 37 chunks.

  The hard part was keeping the static site intact. `renderToString` cannot
  suspend, so a `React.lazy` route would write its loading fallback into the
  prerendered HTML — the one copy a crawler and a first-time visitor read, and
  the copy that looks fine while carrying nothing. Both renderers are derived
  from one route table: the prerenderer awaits every import and renders
  synchronously, the browser takes the split chunks. Two hand-written lists
  would have worked and then drifted, so a route in one and not the other is a
  page that works when clicked and 404s when shared.

  Each prerendered page now also carries a `modulepreload` for its own chunk,
  so hydration does not wait for the entry script to parse before discovering
  it. One per page, not all of them — preloading thirty chunks would undo the
  splitting.

- **Area, heatmap and violin charts**, still hand-rolled SVG with no runtime
  dependency. The heatmap is wired into the KV-cache page, where nine cells
  over K and V dtype put both memory inversions in one column; the table reads
  a row at a time and the grid shows the pattern. Every chart carries the
  numbers behind it for anyone who cannot see the picture, and an unmeasured
  cell reads `—` rather than taking the colour of a minimum.

- **`prefers-contrast: more` and print styles.** Tints that carry meaning
  become outlines for a reader who asked for more contrast. On paper the
  navigation and theme toggle go, link destinations are spelled out, and the
  table behind each chart is revealed — on paper the numbers are the artifact,
  and hovering a cell is not available.

### Fixed — a heatmap that failed WCAG AA in dark mode

- **The darkest cell measured 3.4:1 against its text in dark mode**, under the
  4.5:1 AA needs for normal text; light mode passed at 5.0:1. The accent sits
  brighter against a dark surface, so one tint cap cannot serve both themes.

  Underneath it was a cascade bug: the light default was declared *after* the
  dark override, and `:root` and `[data-theme='dark']` have equal specificity,
  so source order silently won and the dark cap did nothing. Both themes now
  measure 5.0:1 and 7.3:1, and `tests/test_heatmap_contrast.py` recomputes the
  blend from the tokens rather than trusting that someone checked.

- **The reduced-motion rule named the animations it stopped, one at a time.**
  Every new animation therefore shipped moving until somebody remembered to
  add it, and the person who needed it stopped was the last to find out. It is
  a blanket rule now, covering transitions, animations and smooth scrolling.

### Added — a desktop shell, and everything for the DOI except the account

- **Tauri desktop scaffold** (`desktop/`). Deliberately thin: every command
  shells out to `aihwbench` and returns its JSON unchanged, and the command
  that ran is returned to the UI so a result can be reproduced by hand. A GUI
  that computed its own metrics would be a second implementation of the
  benchmark, drifting in the direction nobody checks -- because the GUI is what
  people use and the CLI is what has tests. The frontend is the existing
  `web/dist`, not a second copy of the UI.

  Subcommands reachable from the renderer are allowlisted. A text field wired
  to a subprocess is an arbitrary-execution hole.

  **It has not been compiled.** Rust 1.98.1 is installed on the reference
  machine and `link.exe` fails: the Visual Studio "C++ build tools" workload is
  absent. The tests check that the config parses, that its paths resolve to the
  real dashboard build, that the version matches the package, and that the Rust
  source shells out rather than computing anything. A valid configuration is
  not a working binary, and the README says so.

- **DOI runbook and Zenodo metadata** (`.zenodo.json`,
  `docs/research/minting-a-doi.md`). Minting needs the maintainer's Zenodo
  account, so everything up to that point is prepared: valid metadata, the
  precondition that the corpus should span more than one hardware class before
  a DOI invites citation as representative, and the instruction to cite the
  *version* DOI rather than the concept DOI -- the concept DOI resolves to the
  newest snapshot and reintroduces exactly the mutability a DOI removes.

  A test asserts no DOI is claimed anywhere until one exists, because a
  placeholder in `CITATION.cff` would be copied into a bibliography and resolve
  to nothing.

### Added — non-text modalities, each in its own unit

- **`aihwbench modalities`** says which of embedding, reranking,
  vision-language, ASR, TTS, image generation and speech-to-speech this machine
  can measure, and in what unit. **None of them is tokens per second**, and the
  inventory says so: a real-time factor read as a generation rate compares
  different quantities, and both look alike because both go up when things are
  good.

  Each declares the axis that dominates it, because a single figure at one
  point on the curve is the usual mistake. Embedding at batch 1 and at batch 64
  differ by more than most hardware differences do.

  Where a modality cannot be measured the report names the missing piece rather
  than calling it unsupported -- "a TTS model; the llama-tts runtime is
  present" is actionable in a way "unsupported" is not.

- **Embedding throughput across batch sizes**, measured through a runtime's
  embed endpoint. The warm-up call is discarded because the first embed here
  took 33.8 seconds against a fraction of a second warm, and reporting that as
  the embedding rate is the obvious way to get this wrong.

### Corrected

- **An earlier audit over-counted three items.** `grep` for "vision",
  "embedding" and "tts" matched substrings in unrelated prose -- "provision",
  an evaluator comment, and so on -- so #58, #60 and #63 were reported
  implemented when no such workload existed. They are implemented now; the
  earlier count was wrong and is corrected here rather than quietly.

### Added — multi-device support, and six backends for hardware this machine lacks

- **llama.cpp RPC and tensor-split are sweepable axes.** `--rpc-servers-list`,
  `--tensor-split-list`, `--split-mode-list` and `--main-gpu-list`, plus
  `aihwbench devices` to list what the *runtime* can offload to. That is a
  different question from what the machine has: this laptop has an Intel Iris
  Xe and an RTX 3080 Ti, Vulkan enumerates both, and a CUDA build of llama.cpp
  offloads to one.

  A split whose share count does not match the device count is refused before
  the run. llama.cpp ignores extra fractions and defaults missing ones rather
  than failing, so the alternative is a real measurement of a configuration
  nobody requested.

  Validated by running a two-device split against a local `ggml-rpc-server`,
  which joins the enumeration as a second device. Recorded under
  `results/measurements/` as a **code-path validation, not a performance
  result**: both devices there are the same card over TCP loopback, so any
  throughput ordering is an artifact. The three splits allocated 799, 867 and
  632 MiB, which a flag being ignored could not do.

- **Vulkan, SYCL, WebGPU, ExLlamaV2, Jetson and ARM SBC backends.** None can
  run here, and each says why in terms the user can act on. Vulkan is the
  example worth citing: two Vulkan devices are present and the build has no
  Vulkan backend, so the report says the hardware is not the limitation and
  names the CMake flag. "Not available" would have told the user their GPU was
  unsupported, which is false.

  Each refuses rather than falling back. A result labelled `sycl` that ran on
  the CPU, or `vulkan` produced by CUDA, would be mislabelled in the one way
  the comparison classifier is blind to: every field would agree while the
  numbers came from different silicon.

  Each also declares what its hardware does to a measurement — Jetson's
  unified memory and `nvpmodel` power mode, an SBC's throttle and
  power-delivery flags, ExLlamaV2's fractional bits per weight that do not map
  onto GGUF quantization labels, and the fields a browser sandbox cannot
  measure at all.

### Fixed

- **`--rpc` has to precede `--list-devices`.** llama.cpp acts on the list
  request as it parses it and exits, so a later `--rpc` was never read and the
  remote device was missing from a listing that looked complete.

### Added — four quality and capacity measurements that were missing

- **Perplexity, with the reason most perplexity comparisons are void.**
  `aihwbench perplexity` runs llama.cpp's `llama-perplexity` over a corpus you
  supply. Perplexity is a per-*token* quantity, so two models with different
  tokenizers compute it over different denominators and the comparison means
  nothing while looking exactly like one that does. Every measurement records
  the tokenizer identity, the corpus hash, the context length and the chunk
  count, and `perplexity_comparable` refuses a comparison that differs in any
  of them. Measured here: the chunk count alone moved the figure 23% on one
  model over one corpus.

- **Text-to-SQL scored by execution, not by string match.** `SELECT name FROM t
  WHERE age > 30` and `SELECT t.name FROM t WHERE 30 < t.age` are the same
  query and share almost no characters, so a text metric reports a correct
  model as wrong. The `sql_execution` evaluator runs both and compares results:
  row order matters only when the reference asked for it, duplicates are not
  collapsed, an invalid query is wrong, and a *reference* that fails to run is
  a broken dataset row rather than the model's fault. The database is opened
  read-only, enforced by SQLite rather than by pattern-matching the query --
  the SQL came from a model, and a benchmark that drops its own fixtures is
  one you cannot run twice.

- **Mixture-of-experts memory, which has two answers.** A model named
  "30B-A3B" advertises its *active* parameter count; read as a memory
  requirement it is off by a factor of sixteen. On Qwen3-30B-A3B's geometry, 8
  of 128 experts run per token, so 16.3 GB must be resident while 1.0 GB is
  active. Expert offload traffic is reported as best/expected/worst per token
  rather than an average, because which experts the router picks changes per
  token and an average hides the tail.

- **Cloud instance profiles as a TCO baseline.** Hardware specs are bundled
  with the URL and date they were read; prices are not, because an instance's
  GPU is a stable fact and its price varies by region, commitment and the spot
  market. No throughput is claimed for any of them: this project has measured
  none, and a measured local number beside an assumed remote one is the
  assumption dressed up as a comparison.

### Added — the flash-attention memory matrix, measured on an idle card

- **All nine KV-dtype configurations, at `--flash-attn auto` and `on`**
  ([`results/measurements/kv-cache-flash-attention-vram.json`](results/measurements/kv-cache-flash-attention-vram.json)).
  Two results fall out of it.

  With flash attention on, **the analytic cache model holds everywhere**: every
  configuration lands within 30 MiB of the size computed from the model's
  attention geometry, and the offset is consistent rather than scattered. The
  arithmetic is validated against the whole matrix rather than one convenient
  point.

  `auto` disagrees with `on` in **exactly two of nine** cases, and they are
  precisely the two where K is quantized and V is not. Each costs **940 MiB**
  more than the arithmetic predicts. Everywhere else `auto` already chooses
  `on`, which is why the default looks harmless until the one time it is not.

  Recorded as a memory measurement rather than a benchmark: no tokens were
  generated, because the question is how much memory a configuration needs.
  VRAM is a deterministic allocation -- repeated readings were identical to the
  MiB -- which is why it is trustworthy while a throughput figure taken on the
  same machine at the same time would not be. The throughput half is still
  unmeasured for `-fa on`, and the study says so.

### Added — a multiple-choice evaluator that refuses to guess

- **`multiple_choice`, for MMLU-shaped sets.** The scoring is a string
  comparison; the difficulty is deciding what the model picked from free-form
  output, and getting that wrong is how a benchmark ends up measuring output
  formatting and reporting it as accuracy.

  It reads a letter only when the model marked it ("the answer is B",
  "Answer: B", "Option C is correct"), gave it alone, or put a delimiter after
  it ("B) Paris"). It does not scan for capital letters: "A bird can fly
  south" does not answer "A".

  An answer it cannot read scores `None`, never `0.0`. Zero says "answered
  incorrectly", and conflating that with "answered unreadably" understates
  every model whose formatting differs from the one the harness expected --
  silently, and in a direction that looks like a quality difference. A
  response naming two different letters is likewise unread rather than
  resolved by taking the first, which would reward thinking out loud.

  The dataset stays yours: this repository bundles no restricted datasets.

### Fixed — a regex that matched nothing, and a guard for the whole class

- **An escape written into a non-raw string became a control character.** The
  answer-marker pattern began with a literal 0x08 where `` was meant, so it
  required an unprintable byte before the word "answer" and matched nothing.
  Every explicitly-marked answer scored as unreadable, which looks exactly
  like a model that formats badly rather than like a fault.

  ``, ``, `` and `` are all valid regex escapes *and* valid string
  escapes, so this fails silently by construction: the pattern compiles, runs,
  and never matches. A test now walks every module in the package and asserts
  that no compiled pattern contains a control character.

### Added — schema 2.1, which requires what the classifier has to read

- **Schema 2.0 accepted `{}` as a valid result.** `model` had no `required`
  and `additionalProperties: true`; `reproducibility` was a nullable object
  with two optional properties. So a document could omit every field the
  comparison-safety classifier reads and still validate -- and the classifier
  treats two absent fields as agreement, which made two empty documents
  compare as STRICTLY_COMPARABLE with zero reasons.

  `comparability._REQUIRED_PRESENT` closes that at comparison time. Schema 2.1
  closes it at the door: it requires model name, runtime name/backend/device
  and the iteration counts, rejects nulls and empty strings in them, and
  refuses a null `reproducibility` block -- which would otherwise satisfy any
  `required` list inside it, since JSON Schema applies `required` only to
  objects. `tests/test_schema_2_1.py` asserts the schema's requirements
  against the classifier's gate, so the two cannot drift.

  It requires nothing beyond that gate: a machine with no power sensor, no
  container and no evaluator still produces a publishable result.

- **Energy in the units people plan with, and carbon that says whose grid.**
  `tokens_per_kwh` and `watt_hours_per_1k_tokens` alongside joules per token,
  and `aihwbench cost --grid-intensity` for carbon. The intensity is required
  rather than defaulted, as `analysis.cost` already requires an electricity
  price: the same run in France and Poland differs roughly tenfold, so an
  assumed figure would be confidently wrong nearly everywhere. With no
  intensity the report still gives the kWh, which is what every published grid
  figure multiplies.

- **A numeric quality delta per quantization.** `same_output_as_reference`
  answers yes/no, which is the right question for a determinism check and the
  wrong one for choosing a quantization: every useful quantization answers
  "no" and the answer carries no magnitude. `quality_delta_vs_reference` gives
  the size of the gap against the highest-precision *scored* variant -- chosen
  separately from the output-hash reference, since a run may carry one and not
  the other.

### Fixed — two migration defects, one latent and one live

- **`validate --formal` had never passed on a migrated 1.0 result.** Schema
  2.0 requires `protocol_version` and the 1.0 -> 2.0 migration did not supply
  it, so every migrated 1.0 document failed formal validation on a field the
  migration was meant to add. It now states protocol 1 -- a statement of fact
  rather than a default, since protocol 1 is the only one that has existed.

- **A migrator stamped `CURRENT_SCHEMA_VERSION` instead of its own target.**
  Harmless while 2.0 was current; the moment it was not, the 1.0 -> 2.0 step
  would have jumped straight to 2.1, `migrate` would have seen the target
  reached, and the intervening migration would never have run. Each migrator
  now stamps the version it produces.

- **A multi-step migration erased where the document came from.** Each step
  overwrote `from_version`, so a 1.0 document migrated to 2.1 claimed to have
  come from 2.0. The origin is written once and kept, and every migrator that
  touched the document is listed in order.

### Fixed — a strict comparability field that had never once discriminated

- **`model.tokenizer` was null in every result this project has published.**
  The schema declares it, `comparability._STRICT` reads it, and no backend
  ever wrote one. `_same(None, None)` is True by design, so two runs whose
  tokenizers differed have always agreed about their tokenizers.

  This is the same shape as `model.quantization`, which was hardcoded to None
  while Ollama's API had been returning it all along. It matters because
  changing a tokenizer changes what a token *is*, so tokens per second stops
  meaning the same thing -- and unlike a quantization change, it leaves no
  trace in the model's name.

  Both generative backends now record an identity built from fields a GGUF
  header and Ollama's API both expose, and which agree with each other on the
  same weights: `gpt2/qwen2/bos:151643/eos:151645` for the reference model,
  identical through either runtime. It catches a different tokenizer family, a
  different pre-tokenizer and changed special tokens. It deliberately does not
  hash the vocabulary, which a GGUF file carries and Ollama's API nulls:
  an identity only one runtime could compute would split the corpus in half.

  Results published before this carry no tokenizer, so a new result and an old
  one now differ on a strict field. That errs toward NOT_COMPARABLE, which is
  the safe direction and the same trade already accepted for quantization.

### Added — KV-cache quantization, measured as memory rather than speed

- **`aihwbench kv-cache` and the `cache_type_k`/`cache_type_v` sweep axes.**
  The llama.cpp backend has declared both axes as tunable, validated them
  against the dtypes llama.cpp accepts, and passed them to `llama-server` --
  and no CLI path could set either. The axes are reachable now, and the
  analysis reports the memory story first.
- **The cache size is computed from the model's own attention geometry.**
  `gguf.read_gguf_attention` reads layer count, KV-head count and head width
  out of the header, so the size is exact and scales to a context length
  nobody has measured. The reference model has 14 query heads and 2 KV heads;
  sizing from the query count would overstate the cache sevenfold.
- **Checked against llama.cpp on the reference machine.** At 32768 tokens the
  predicted saving against f16 is 180 MiB for `q8_0` and 276 MiB for `q4_0`;
  measured device VRAM moved 178 MiB and 274 MiB. `q5_1`, `q5_0` and `q4_1`
  are each 30 MiB adrift in the same direction, because total VRAM includes
  compute buffers that vary with cache type and not the cache alone -- which
  is why the analytic column sits beside the measured one rather than
  replacing it.
- **The framing is the feature.** At 32768 tokens this 0.5B model's f16 KV
  cache is 384 MiB, larger than its 379 MB of weights. Read as speed, cache
  quantization looks like a small loss and the advice is to leave it alone;
  read as memory, it is what decides whether a long conversation fits at all.
  Throughput is reported with the measured 10% run-to-run noise floor
  attached, and a difference inside that floor is reported as
  indistinguishable rather than as a result.

- **Flash attention, threads and batch size are sweepable on llama.cpp.**
  `--flash-attn-list`, `--threads-list` and `--batch-list`, applied by the
  backend and declared as tunable axes so the tuner will accept them. A thread
  or batch count below 1 is refused rather than passed on, because llama.cpp
  substitutes its own default and the result then looks like a measurement of
  a configuration nobody ran.

- **A `/kv-cache` dashboard page, and the study behind it**
  ([docs/results/kv-cache-rtx3080ti.md](docs/results/kv-cache-rtx3080ti.md)).
  Nine configurations measured on the reference machine. The page states the
  best configuration outright, marks the two that cost more memory than they
  save in prose rather than relying on a shaded table row, and carries a
  slider for the question the table cannot answer: how many tokens of context
  a given VRAM budget holds. The cache sizes are computed in the browser from
  the geometry the zoo records, and reproduce the Python figures exactly.
- **The model zoo records attention geometry.** Layers, KV heads and head
  width, read from the GGUF header. It is what sizes the KV cache, and
  recording it means the dashboard can compute cache sizes for any context
  length without the weights present -- which matters, since the weights are
  the one thing that cannot be shipped.

### Fixed — two ways a sweep could produce confident, wrong numbers

- **The prerenderer and the browser kept two hand-written lists of the same
  data files, and they drifted.** A file the browser fetched and the
  prerenderer did not renders the page's empty state into the static HTML --
  which is what a search engine and a first-time visitor see. The
  prerenderer's own comment warned about this; nothing checked it. Now
  `tests/test_frontend_data_contract.py` does, in both directions.

- **A finished benchmark's VRAM could still be resident when the next one
  started.** The OS reaps a terminated `llama-server` and reports it gone
  while the driver is still tearing down its GPU context, and a leaked server
  holds its allocation indefinitely -- one was observed holding 1022 MiB
  across an entire sweep, which every point of that sweep would have measured
  as its own. `telemetry.wait_for_vram_release` now blocks until the device
  gives the memory back, and reports rather than raises when it does not: the
  finished run is still worth keeping, and the *next* one is what is suspect.
- **A second sweep of one runtime silently destroyed the first.** The output
  name was derived from the runtime alone, so a KV-cache sweep of llama.cpp
  wrote over the published offload-cliff sweep that
  `docs/results/offload-cliff-rtx3080ti.md` cites as its raw data. The check
  now runs *before* measuring -- refusing afterwards would cost the run as
  well as the data -- and `--output-name` gives a sweep its own file. A sweep
  over the same axes is a re-measurement and still overwrites.

### Added — a model zoo, because a result named a model nobody could obtain

- **`aihwbench zoo`: licences, checksums, and the command that gets each
  model.** `models/zoo.json` records, per benchmarked model, the licence it is
  offered under, a checksum, and how to obtain it. `zoo list`, `zoo verify`
  and `zoo fetch` read it; `docs/models/zoo.md` is generated from it with a CI
  freshness gate.
- **Licences are read from the artifact, never inferred.** `gguf.read_gguf_license`
  reads `general.license` out of the GGUF header and Ollama's `/api/show`
  relays the same statement, so a licence can be re-derived by anyone holding
  the file. `zoo verify` re-reads it and fails when the manifest and the
  artifact disagree. Where a format carries no licence field, the entry is
  marked `declared` — written by a maintainer, checked by nothing — and the
  dashboard says so rather than presenting it as equally certain.
- **The dashboard's model pages now state licence, origin and how to verify.**
  A page that says how fast a model runs and nothing about whether you may use
  it has answered the easier half of the question.

### Fixed — an artifact that outlived nothing, and two checksums of one model

- **Four published results measure a model that no longer exists anywhere.**
  `mobilenetv2-12.onnx` had been deleted from the machine that produced them,
  no result records where it came from, and all four record `checksum: null`.
  Nobody could obtain it, and nobody obtaining a file by that name could
  confirm it was the one measured. The zoo records the source; the file has
  been re-obtained and hashed. The four results still cannot be tied to it —
  they recorded no checksum — and the entry says so instead of implying
  otherwise.
- **Two published checksums for byte-identical weights disagreed.** The
  llama.cpp results record `sha256:c5396e06...`, the hash of the GGUF weights
  file. The Ollama results record `a8b0c515...`, which is Ollama's *manifest*
  digest — a hash of a document covering the weights **and** the template
  **and** the system prompt. One field, two kinds of hash, nothing saying
  which. `model.checksum` is in the comparison-safety classifier's strict set,
  so this errs safely: the mismatch pushes a pair toward NOT_COMPARABLE rather
  than falsely toward agreement. But "cannot tell" was recorded as "differs".
  Every zoo entry now states what its checksum is a hash *of*, and aliases tie
  both spellings to the one model. `backends.ollama.model_weights_digest`
  reports the weights hash, extracted from the documented API without keeping
  the home-directory path it appears in.
- **`models/` was gitignored as a directory, so the manifest could not be
  tracked.** Git cannot re-include a file whose parent directory is excluded;
  the pattern is now `models/*` with the manifest negated back in.

### Fixed — workloads that could not be run, and one that measured a third of itself

- **Thirteen of seventeen registered workloads could not be run by
  `benchmark`.** Eight describe an input length rather than carrying a prompt,
  and `synthesize_prompt` — which turns a length into a deterministic prompt —
  had no callers. Twelve are runnable now; the remaining five need a driver
  issuing more than one request, and offering those would let someone run
  `multi_turn_8` and measure a single turn believing they measured eight.
- **`long_prompt` measured a third of its declared input.** It declares 4096
  input tokens and ran at the 2048-token default context, so the server
  truncated a 3331-token prompt to 1026. `workload.isl_tokens` said 4096,
  `metrics.prompt_tokens` said 1026, and nothing compared them. The context
  now follows the workload unless the caller set it, as `--max-tokens` did.
- **Prompt-processing throughput may be measuring a cache.** `long_prompt`
  reported 338,103 prompt tokens per second for a 3331-token prompt, because
  prompt evaluation took four milliseconds once the warm-ups had loaded it.
  Every iteration sends the same request — which is what makes a benchmark
  reproducible and what lets a prefix cache answer all but the first without
  prefilling. Results now label the figure `possibly_cached` and say why. It
  is kept rather than discarded: cache-hit prefill is a real thing to want to
  know about, and a reader after prefill needs telling this is not it.

### Added — two quality evaluators that need no corpus

ROUGE-L (longest-common-subsequence overlap, order-sensitive) and SQuAD-style
token F1 (order-insensitive) join exact match, JSON validity and cosine
similarity. They exist as a pair because they disagree: reversing "the cat sat
on the mat" scores 0.5 and 1.0 respectively, and that difference is what
separates a summary from a short factual answer.

Both refuse rather than guess — no reference means no score, and an empty side
returns None rather than 0.0, which would read as "scored badly". No dataset
is bundled, so nothing depends on a licence this repository cannot grant.

### Fixed — a benchmark that did not check the machine was free to be measured

The costliest defect of the batch, found by nearly publishing it.

Re-measuring ONNX Runtime on CPU during a background antivirus scan produced
**2.53 inferences per second** where the same model on the same machine had
measured **299.92** — a 118x error. OpenVINO on CPU was 78x slow in the same
window, and both GPU paths 2.3x slow because they still need the CPU to feed
them. All four results passed the entire data-quality gate: consistent, so
variance was low; internally coherent, so plausibility was clean; and nothing
in the corpus gave them anything to be implausible against.

`aihwbench self-test` had warned about background load above 20% CPU since
long before any of this. Nothing called it — it was reachable only by someone
who chose to run `self-test` first, which a benchmark in CI or a contributor's
script never does. The same pattern as `rapl_power_sample`, `npu_telemetry`
and the rest, but the one that produces a wrong number rather than a missing
one.

Every run now records the load sampled immediately before it starts, and the
quality gate refuses a result measured above the threshold. Sampled before,
for the same reason as the idle power baseline: during the run the benchmark
is itself the load. Unknown load stays unknown rather than being read as
quiet.

The four contaminated results were discarded and the originals restored. They
score 5/6 rather than 6/6, because they predate the provenance field — a
missing derived hash being a metadata gap, where a 118x wrong number is not.

### Changed — the idle power baseline reports its own spread

A card at rest is not at a constant draw. Measured on the reference machine
within one session: 14.9 W, 29.3 W, 30.3 W and 31.4 W, all honestly sampled as
"idle" — and with a model resident it oscillated between 14 W and 21 W at 0%
GPU utilization, a 50% swing a two-second window can land anywhere in.

`incremental_power_watts` looked equally precise whether the thing subtracted
was steady or swinging. The baseline now publishes its range, and a workload
adding less than the baseline's own variation is marked not robust: a
difference inside the noise of what was subtracted is not a measurement of the
difference.

### Fixed — `runtime.device` recorded what was typed, not what ran

Two ONNX Runtime runs on the same silicon, both landing on
`CPUExecutionProvider`, were NOT_COMPARABLE because one passed `--device cpu`
and the other took the `auto` default. `runtime.device` is in the classifier's
strict set, so a split created by how someone spelled a flag became a claim
that two identical configurations could not be compared. The device that ran
is now recorded, with the requested one kept beside it.

### Fixed — model identity that was available and recorded as null

- **Every result ever published carried `model.quantization: null`.** Ollama's
  `/api/tags` had been returning `details.quantization_level` all along, and a
  GGUF file states its own quantization in its header. Both backends
  hardcoded the field to `None`.

  `model.quantization` is in the comparison-safety classifier's strict set,
  and `_same(None, None)` is True by design — so null on both sides meant two
  results at different quantizations *agreed* about it. With an Ollama tag the
  classifier still caught the difference through the name, because the tag
  happens to encode it. Served under a name that does not, two different
  quantizations compared as STRICTLY_COMPARABLE with zero reasons given.

  It also emptied `aihwbench quantization`, whose entire purpose is grouping
  results by quantization and which reported `quantizations: [None]` for every
  family, along with the dashboard filter beside it.

- **`aihwbench/gguf.py`** reads identity from a GGUF header: quantization from
  `general.file_type`, parameter count from `general.size_label`, architecture
  from `general.architecture`. Header only, never tensor data, so it stays
  bounded work on a file that may be tens of gigabytes — 0.3 ms on the
  reference model. A truncated header, an unsupported version, an unknown
  value type or an implausible length yields nothing rather than whatever sits
  at the offset it guessed.

  Neither backend parses the filename. `model.gguf` is a legal name for any
  quantization, files get renamed, and a wrong quantization is worse than a
  missing one because it makes two different models compare as one. The two
  sources agree independently: Ollama's API and the GGUF header both report
  `q4_k_m` for the same model.

- **`docs/methodology.md` claimed llama.cpp generation tok/s is null.** It has
  not been for some time: it is derived from the client wall-clock window
  between the first and last streamed chunk, labelled `client_wall_clock` in
  `metrics.metric_source`, and the published result carrying 360.87 tok/s sat
  directly under a limitation saying it could not exist.

### Fixed — guards that could not fire, and verdicts that could not discriminate

Found by running each command against real data and reading the numbers,
rather than checking it exited zero.

- **The energy-consistency plausibility check had never run.** It read
  `metrics.energy_joules_per_token`, which is null in every result ever
  published: the field was computed inside `aggregate_iteration_metrics` from
  a per-iteration power key no backend sets, while real power arrives from the
  telemetry sampler afterwards. The field is removed rather than moved, since
  the `energy` block already publishes per-token energy against incremental
  power with its basis attached; the check reads that instead. Two tests
  covered this and passed throughout, because their fixture supplied the power
  key production never emits.
- **`aihwbench cliff` named an optimum the data could not distinguish**, and
  **`context-scaling` called a still-climbing memory curve saturated** —
  reporting saturation at the second measured depth for any model whose
  weights dominate its VRAM, with a note offering spilling as the cause, on a
  card with 15 GB free.
- **The sweep projection dropped two metrics its own consumers read.**
  `most_efficient` was null for every `aihwbench tune` run ever, and the
  context analyser lost the prompt-throughput series its whole subject depends
  on. The projection is now pinned against the code that reads it.
- **The regression gate failed on system-wide memory.** Two runs of the *same
  configuration* minutes apart failed CI over a 1.3 GB swing in
  `psutil.virtual_memory` — which every result already publishes as
  `scope: system`. System-scoped metrics are now reported, not gated.
- **The load generator reported `mean_queue_latency_ms: 0.0`** on a capacity
  ladder showing 20-second p95 latencies. A closed-loop worker submits and
  starts in the same breath, so the subtraction was zero by construction; the
  queueing was inside the server, where a client cannot see it.
- **Five documented commands the CLI has never accepted.** The quickstart and
  all four backend guides told readers to pass `--backend`; the flag is
  `--runtime`. Every `aihwbench` line in every markdown file is now parsed
  against the real argument parser.

### Changed — numbers that were saying less than they appeared to

- **`aihwbench score` now says when a component hit its ceiling.** Every
  component clamps at 100, so a result at 2x its reference and one at 10x
  score identically. A published result scored exactly 100.0 on two of three
  components — throughput was really 599% of its reference — leaving the
  composite driven by the third. The score is unchanged; what it hides is now
  visible.
- **`aihwbench verify-bundle` now states what a pass establishes.** The
  manifest ships inside the bundle, so editing a result and recomputing the
  manifest verifies clean — as any unsigned checksum scheme must. The report
  no longer lets `valid: true` be read as a claim about origin.
- **`--output` says whether it wants a file or a directory** on every command
  that has one. Passing a file path where a directory is expected silently
  creates a folder with that name.

### Fixed — capabilities that were built, exported, and never called

The dominant defect class in this repository. Each of these was written,
sometimes tested, and reachable by nothing.

- **`aihwbench self-test` reported `overall: fail` on every machine ever run.**
  Its runtime check compared each backend's status against the string
  `"ready"`, which no backend has ever returned — the states are `AVAILABLE`,
  `NOT_INSTALLED`, `NOT_AVAILABLE`, `UNSUPPORTED_PLATFORM`,
  `HARDWARE_REQUIRED` and `CONFIGURATION_REQUIRED`. On this machine `doctor`
  listed four available runtimes while `self-test` said there were none. A
  precondition check that always fails is worse than none: it teaches people
  the tool's verdicts mean nothing.
- **`ParquetExporter` was in `__all__` and not in the registry**, so
  `get_exporter("parquet")` raised `KeyError`. Because nothing could reach it,
  nobody found that its `export` also called `pq.Table` — `Table` lives in
  `pyarrow`, not `pyarrow.parquet`. Two defects behind one missing
  registration. A test now asserts every exported `*Exporter` is reachable.
- **`rapl_power_sample` had no callers**, so a machine with no discrete GPU
  measured no power at all — and that is most consumer laptops. The
  joules-per-token figures this project treats as a differentiator existed
  only for people who already owned an NVIDIA card.
- **`npu_telemetry` had no callers**, so results said nothing about NPUs.
  Silence is the worst option of three: a reader could not tell "this machine
  has no NPU" from "this machine has one and nothing measured it".
- **`diff_snapshots` had no callers** while `build_snapshot_manifest`
  duplicated its set arithmetic inline — two implementations of "what changed
  between two snapshots", each free to drift.
- **`backends/capabilities.py` was imported by nothing at all** — not a
  backend, not the CLI, not a test — and built a parallel capability report
  competing with the `detect()` every backend already implements. Removed.
- **`enrich_with_npu`** likewise, once the runner attached the block directly.

### Fixed — advice drawn from noise

- **`aihwbench cliff` named an optimum the measurements could not
  distinguish.** On a real sweep at 3 iterations per point it reported 247.06
  tok/s at 24 GPU layers against 222.8 at 99 and called 24 the best setting;
  at 8 iterations the same sweep gave 272.4 and 371.9, and 99 won decisively.
  `best_layers` was a bare `max()` over the means. It now reports which
  settings it cannot tell apart, using confidence intervals where the sweep
  measured them and a labelled 10% margin where it did not.
- **Sweeps discarded the variance the runner had already computed.**
  `DEFAULT_METRIC_KEYS` projected five metrics per point and dropped the rest,
  so every consumer of a sweep compared means with no way to ask whether a
  difference survived the noise.
- **Sweeps recorded no model.** `params.model` was empty for every runtime
  taking a `--model-path`, so a published offload curve arrived with nothing
  attached — and where a cliff sits depends entirely on how big the model is.
  Sweeps now carry their full environment.

### Added — coverage, reach and provenance

- **vLLM and SGLang backends.** The engines the closest academic competitor
  measures, supported here for the opposite case: consumer hardware, published
  beside llama.cpp and Ollama results, with the classifier saying which may be
  ranked together. Both speak the same OpenAI-compatible protocol, so the
  streaming client is written once. Neither launches a server — startup flags
  decide what is measured, and a benchmark that chose them would be reporting
  on a configuration the operator never saw.
- **CPU-package power via Intel RAPL**, as a labelled fallback where no GPU
  probe answers. Its scope travels with the reading, because publishing a
  CPU-package figure as device power invites exactly the comparison this
  project exists to prevent.
- **Container and image identity in every result.** A tag is not an identity;
  the digest is recorded where supplied and its absence explained where not,
  and never inferred from a tag.
- **A HuggingFace dataset export**, with the card that makes it a dataset
  rather than a file — carrying the comparability caveat to readers who have
  none of this repository's context.
- **`aihwbench doctor --json`**, a conformance report someone on hardware the
  maintainers cannot test can attach to an issue.
- **`aihwbench snapshot --diff`**, which answers "what changed between the
  release people cited and the one they have" without both directories.
- **A GitHub Action contributors can run on their own hardware**, which
  refuses to run on a shared runner and never publishes anything itself.
- **A measured offload cliff**: 64 → 372 tok/s across 0 to 99 offloaded
  layers, a 5.8x range on one machine with a 40% step between 18 and 24
  layers, published with the environment that produced it.
- **Four dashboard pages**: a task-first matchmaker that says when no measured
  result meets the requirements, a measured offload-cliff explorer, embeddable
  result cards that carry their own caveat, and browser-side submission whose
  privacy scan uses the CLI's own generated patterns and uploads nothing.

### Fixed — measurements that described the machine rather than the workload

Found by running the benchmark on real hardware, not by any test. Each one
produced a number that looked reasonable and was wrong.

- **GPU detection fell back to the integrated GPU on a machine with a discrete
  one.** `get_nvidia_gpus()` asked nvidia-smi for identity and PCIe link in a
  single query, using two field names nvidia-smi does not accept. It fails a
  whole query on one unrecognised field, so detection returned nothing and the
  Windows WMI fallback answered instead — a published result recorded NVIDIA
  power and VRAM telemetry against an "Intel(R) Iris(R) Xe Graphics".
  `system.gpu` is a strict comparison key, so a wrong value there makes runs
  from two machines look like runs from one. Identity is now queried alone,
  and the link separately using verified field names.
- **Per-token energy was published against baselines that could not support
  it.** The same workload on one machine gave 0.0777 J/token and then
  0.0009 J/token — an 84x swing caused by nothing but a model still being
  resident from an earlier run, which held the card at raised clocks and made
  almost the entire measured draw baseline. The idle sample now records the
  state it was taken in (utilization and resident VRAM), refuses a baseline
  taken while the GPU is busy, and every figure states what share of gross
  power the workload actually accounted for.
- **`energy_joules_per_token: 0.0` claimed that generating tokens is free.** A
  `max(0.0, gross - idle)` clamp turned "the workload's draw is below this
  sensor's resolution" into a measurement of zero. Measured case: a 0.5B model
  held an RTX 3080 Ti at ~6% utilization and the card's idle draw drifted by
  more than the workload added. Unresolvable is now null with a reason.
- **A cold-start penalty was reported when nothing loaded cold.** `cold - warm`
  went negative when the model was already resident, publishing
  `-1.172 ms`. Clamping to zero would assert that loading is free, so the
  penalty is absent unless a cold load was genuinely slower, and
  `cold_start_measured` says which happened.
- **The variance gate never checked the headline metric.** It measured
  `total_latency_ms` only, which in a short-generation workload is dominated
  by time-to-first-token. A run whose throughput fell 327 -> 84 tok/s across
  five iterations (CV 0.56) showed a latency CV of 0.06 and passed 5/5.
  Throughput variance was already computed on every run and read by nothing.

### Added

- **`sustained_generation` workload, and `--prompt` / `--workload` on
  `aihwbench benchmark`.** `BenchmarkConfig.prompt` had always existed and the
  CLI never passed it, so the prompt — a strict comparison key — was the one
  parameter no user could set. It mattered: the only workload with a concrete
  prompt was `default_chat`, which asks for a two-sentence answer and so
  generates ~29 tokens however high `--max-tokens` goes, measuring mostly the
  GPU's clock ramp. The new workload sustains generation to a steady state
  (CV 0.019 against 0.56 on the same machine). It is additive rather than a
  change to `default_chat`, which would have silently redefined what every
  existing published result measured. Results now record which workload ran.
- **Confidence intervals on leaderboard ranks.** Two results in one comparison
  group were ranked 281.65 over 261.31 tok/s with overlapping 95% intervals —
  a sort order printed as a 20 tok/s lead. Rows now carry the interval and the
  coefficient of variation, and a tie with rank 1 is marked in the rank column
  and read out to screen readers.
- **A sustained throughput decline is reported separately from noise.**
  Comparing the means of a run's halves distinguishes a machine settling into
  a thermal or power limit from one that is merely noisy. It does not fail the
  quality gate: a throttling machine is a legitimate subject of measurement.
- **First published results at schema 2.0**, and the dataset's first
  comparison group with more than one member. Both agree within their
  confidence intervals and their per-token energy agrees to 0.3%.


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

### Added — a configuration recommender on the dashboard

- `/recommend` answers "what should I actually run on this machine": a model
  size, runtime, device and context length for the hardware you describe.
- It separates the two kinds of claim it makes. The size ceiling is an
  **estimate** from a memory budget and an assumed quantization density; the
  runtime and device are **anchored on measured results**, and the page labels
  which is which. Presenting them identically would be the same error the
  comparison-safety classifier exists to prevent.
- The recommendation is checked against the fit estimator on the page itself,
  because advice that fails the project's own fit check is advice
  contradicting itself.
- Pinned to the Python engine by reference recommendations for six common
  machine shapes, so the site and `aihwbench recommend` cannot advise
  differently.

### Added — a RAG pipeline workload, and four task-shaped workloads

- **`aihwbench rag`** runs retrieve → rerank → generate and times the three
  phases **separately**. A single end-to-end number cannot tell a machine that
  is slow because retrieval is scanning a corpus from one that is slow because
  the model is slow, and those need different fixes.
- Retrieval is **lexical and local by design**. An embedding model would
  measure that model's speed alongside the hardware, and a vector store would
  measure someone's index build — neither is the hardware under test, and both
  would make the workload irreproducible between machines. The report states
  plainly that it measures the *shape and cost* of a RAG request and never
  retrieval quality.
- Ties in retrieval are broken by corpus index, because equal scores ordering
  arbitrarily would make the same question return different context on
  different runs.
- Four more registered workloads, each a distinct request *shape* rather than
  just a different prompt: `code_completion_fim` (latency-bound, short in and
  out), `long_document_summary` (prefill-bound), `structured_output` (pairs
  with the `json_validity` evaluator) and `streaming_chat_interactivity` (read
  for inter-token spread, not mean throughput).

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