# Dashboard performance and accessibility, measured

The project asks contributors to record the machine a number came from and to
say when a number should not be trusted. The dashboard's own quality bar is
held to the same rule: this page is a measurement with its conditions attached,
not a badge.

Two of the three checks in the quality bar are now permanent gates that run in
CI — `npm run a11y` over the prerendered HTML, and the contrast test that
recomputes ratios from the CSS tokens. Lighthouse is not, and the reason is
below.

## What was measured

| | Performance | Accessibility | Best practices | SEO |
|---|---|---|---|---|
| `/` | 100 | 100 | 100 | 100 |
| `/leaderboard/` | 100 | 100 | 100 | 100 |
| `/kv-cache/` | 100 | 100 | 100 | 100 |
| `/results/ollama-1787388930/` | 100 | 100 | 100 | 100 |

Metrics, worst value across the four routes:

| Metric | Value |
|---|---|
| First contentful paint | 0.3 s |
| Largest contentful paint | 0.6 s |
| Total blocking time | 0 ms |
| Cumulative layout shift | 0 |
| Speed index | 0.4 s |

Lighthouse 12.8.2, desktop preset, simulated throttling, HeadlessChrome 152,
against `vite preview` serving the production build. Host benchmark index
3430–3877.

Measured twice — once after the hydration fix and again after the
touch-target changes — with background CPU at 38% and 28%. Identical results
both times, which is the only reason the numbers are quoted without a range.

## The conditions, which matter more than the numbers

**The machine was contended.** CPU sat at 28–39% across the two runs, against
this project's own 20% publish threshold — pytest suites from unrelated
repositories were running throughout. By the rule applied to
benchmark results, a throughput figure measured here would not be publishable.

It is recorded rather than withheld because the direction of the bias is known:
background load can only make a page look slower. A perfect performance score
measured on a busy machine is a stronger claim than the same score on an idle
one, not a weaker one. The reverse would not hold — had it scored 80, that
number would have said nothing, and this page would say so instead.

**Local server, not the deploy target.** `vite preview` serves from localhost
with no network latency and different cache headers than GitHub Pages. The
metric that depends most on that is Speed Index; the scores that do not depend
on it at all are accessibility, best practices and SEO, which are deterministic
audits of the document.

**A local quirk worth knowing about.** `vite preview` serves the *home page*
for `/about` and the correct file only for `/about/`. GitHub Pages redirects
`/about` to `/about/` and serves the right file either way. Measure with
trailing slashes, or Lighthouse silently audits the home page four times —
which is exactly what happened on the first attempt here, and it briefly looked
like a nav-highlighting bug in the site.

## Touch targets, measured at 320px

The stylesheet contained `44px`, and the test checked that it contained `44px`.
It reached two rules — form fields and filter chips — and the assertion passed
while most of the site's controls failed. Measured in a browser at 320px:

| Control | Before | After |
|---|---|---|
| Column sort button | 13 × 23 | 41 × 47 |
| Navigation toggle (the only nav below 900px) | 66 × 23 | 78 × 44 |
| Theme toggle | 67 × 33 | 67 × 44 |
| Header home link | 124 × 29 | 124 × 44 |
| Skip link | 135 × 41 | 135 × 44 |
| Buttons | 165 × 42 | 165 × 44 |

The sort button was under WCAG 2.2's 24 × 24 floor, not merely under this
project's 44px bar. `all: unset` had stripped every default including size, so
the target was as wide as its label — 13px for a column headed `#`.

Two things are deliberately still under 44:

- **Links inside prose** (109 × 20). WCAG 2.2 exempts a target that sits in a
  sentence, and padding one to 44px would wreck the line spacing around it.
- **The sort button's width** in the narrowest column (41px). A column's
  control cannot be wider than the column without overlapping its neighbour's,
  and a target that sorts the wrong column is worse than a small one. 41 × 47
  clears WCAG 2.2 AA comfortably.

The test now reads the effective `min-height` for each control and compares it
numerically, so removing a rule fails it. It still cannot measure a rendered
box — that is what the browser pass above is for, and why the widths in the
table came from a browser rather than from the stylesheet.

The page does not scroll sideways at 320, 768 or 1920; wide tables scroll
inside their own containers.

## Why Lighthouse is not a CI gate

It needs a browser, a server and roughly a minute per route, and its
performance score depends on what else the machine is doing. It held at 100
under both runs here, which says the page has margin, not that the measurement
is stable — a heavier page on a busier machine is exactly where it would start
moving, and a gate that fails because an unrelated test suite is running
teaches people to ignore it.

What is gated instead:

- `npm run a11y` runs axe-core over all 54 prerendered pages on every CI run.
  It is deterministic and takes six seconds.
- `tests/test_heatmap_contrast.py` recomputes contrast ratios from the tokens,
  which is the one accessibility check axe cannot make under jsdom.
- `tests/test_dashboard_quality_bar.py` asserts the reduced-motion,
  `prefers-contrast`, print, fluid-type and touch-target rules are present.
- `web/tests/hydration.test.tsx` and `tests/test_frontend_hydration.py` assert
  the prerendered HTML still survives in the browser, which is what most of the
  performance score rests on.

Re-run Lighthouse by hand after any change to the entry point, the route table
or the prerenderer, on an idle machine:

```bash
npm --prefix web run build && npm --prefix web run preview -- --port 4173
npx lighthouse http://localhost:4173/ --preset=desktop --view
```

## What these scores do not cover

- **Real-world network.** Everything here loaded from localhost.
- **Low-end hardware.** One desktop profile on a 2022 laptop CPU. The mobile
  preset and a real phone would both say something different.
- **Colour contrast in a browser.** axe cannot evaluate it under jsdom, so it
  is computed from the tokens instead. The heatmap ratios were also checked in
  a real browser when the dark-mode failure was found: 5.0:1 light, 7.28:1
  dark, against the 4.5:1 AA threshold.
- **Assistive technology.** No screen reader was driven through the site. axe
  checks that the structure is there; it cannot tell you the page is
  comprehensible. That remains untested, and saying so is more useful than
  implying a clean automated run covers it.
