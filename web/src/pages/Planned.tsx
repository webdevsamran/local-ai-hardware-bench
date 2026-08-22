import { Link } from 'react-router-dom'

/**
 * Clearly-marked future/planned pages. Nothing here is presented as
 * active, certified, or available.
 */
export default function Planned({ kind }: { kind: 'enterprise' | 'certification' }) {
  if (kind === 'enterprise') {
    return (
      <div>
        <p className="notice future">
          <strong>Planned — not available.</strong> The enterprise overview
          below describes a future direction. No enterprise product, service,
          agreement or customer exists today.
        </p>
        <h1 className="page-title">Enterprise (future overview)</h1>
        <p className="page-sub">
          How AIHWBench could eventually serve organizations that benchmark
          hardware before buying — without compromising the open dataset.
        </p>

        <section className="card">
          <h2>What is being considered</h2>
          <ul>
            <li>
              Private result spaces: teams keep internal benchmarks private
              while optionally contributing anonymized aggregates to the public
              dataset.
            </li>
            <li>
              Fleet benchmarking: scheduled runs across many machines with
              regression alerts against baselines (the CLI regression engine
              already exists).
            </li>
            <li>
              Procurement reports: hardware-fit estimates and measured
              perf-per-watt summaries for candidate configurations.
            </li>
          </ul>
        </section>

        <section className="card">
          <h2>Non-negotiables</h2>
          <ul>
            <li>The public dataset and methodology stay open and vendor-neutral.</li>
            <li>No pay-to-rank; enterprise features never alter public results.</li>
            <li>Local-first: private results never leave the customer's infrastructure unless explicitly shared.</li>
          </ul>
        </section>

        <p>
          Interested? Watch the repository roadmap —{' '}
          <Link to="/community">community channels</Link> are the single source
          of truth for status.
        </p>
      </div>
    )
  }

  return (
    <div>
      <p className="notice future">
        <strong>Future / not active.</strong> Certification is not offered, not
        granted, and no result or hardware carries any AIHWBench certification
        today. The definitions below are drafts for future discussion.
      </p>
      <h1 className="page-title">Certification definitions (draft)</h1>
      <p className="page-sub">
        Draft definitions so that, if certification is ever introduced, the
        bar is explicit and auditable from day one.
      </p>

      <section className="card">
        <h2>Draft tiers</h2>
        <dl className="kv-list">
          <dt>Reproduced result</dt>
          <dd>
            An independent party re-ran the workload on comparable hardware and
            reproduced the metrics within declared variance. (Today: anyone can
            attempt this with <code>aihwbench reproduce</code>.)
          </dd>
          <dt>Verified submission</dt>
          <dd>
            A maintainer reviewed provenance hashes, environment metadata and
            the reproducibility completeness score, and marked the result
            verified in the dataset.
          </dd>
          <dt>Sustained-load attestation</dt>
          <dd>
            Thermal stability analysis shows steady-state throughput within a
            declared percentage of peak over a sustained run.
          </dd>
        </dl>
      </section>

      <section className="card">
        <h2>What certification would never mean</h2>
        <ul>
          <li>No paid certifications; no vendor influence over criteria.</li>
          <li>No certification of hardware itself — only of specific measured results.</li>
          <li>No claim of scientific validity beyond the published methodology.</li>
        </ul>
      </section>
    </div>
  )
}