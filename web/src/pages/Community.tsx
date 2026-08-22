import { Link } from 'react-router-dom'

export default function Community() {
  return (
    <div>
      <h1 className="page-title">Contributors & community</h1>
      <p className="page-sub">
        AIHWBench is built by people who benchmark their own machines and
        publish honest numbers.
      </p>

      <section className="card">
        <h2>Project leadership</h2>
        <p>
          <strong>
            <a
              href="https://github.com/webdevsamran"
              target="_blank"
              rel="noopener noreferrer"
            >
              @webdevsamran
            </a>
          </strong>{' '}
          — original creator, founder and lead maintainer of AIHWBench.
        </p>
        <p className="muted">
          Contributor acknowledgements are maintained in{' '}
          <code>CONTRIBUTORS.md</code> in the repository. This page lists only
          verified contributors — it is never padded with placeholder names.
        </p>
      </section>

      <section className="card">
        <h2>How to contribute a benchmark result</h2>
        <ol>
          <li>
            Run <code>aihwbench self-test</code> to confirm your machine is in
            a good state (AC power, low background load, cool thermals).
          </li>
          <li>
            Run <code>aihwbench benchmark</code> with a supported runtime and a
            model you have locally.
          </li>
          <li>
            Validate:{' '}
            <code>{'aihwbench validate <result.json>'}</code> and{' '}
            <code>{'aihwbench quality <result.json>'}</code>.
          </li>
          <li>
            Open a PR adding the file to <code>results/published/</code>. CI
            re-validates schema, privacy and quality automatically.
          </li>
        </ol>
        <p>
          Full guide: <code>CONTRIBUTING.md</code> in the repository.
        </p>
      </section>

      <section className="card">
        <h2>Other ways to help</h2>
        <ul>
          <li>
            <Link to="/hardware-needed">Hardware-needed list</Link> — run
            benchmarks on platforms we cannot test ourselves.
          </li>
          <li>Improve runtime backends, telemetry sources or the frontend.</li>
          <li>Review flagged results and reproduce published runs.</li>
        </ul>
      </section>

      <section className="card">
        <h2>Code of conduct</h2>
        <p>
          The project follows the Contributor Covenant (see{' '}
          <code>CODE_OF_CONDUCT.md</code>). Be precise, be kind, and never
          fabricate data.
        </p>
      </section>
    </div>
  )
}