export default function About() {
  return (
    <div>
      <h1 className="page-title">About AIHWBench</h1>
      <p className="page-sub">
        An open, vendor-neutral platform for benchmarking local AI runtimes on
        real hardware.
      </p>

      <section className="card">
        <h2>Creator</h2>
        <p>
          AIHWBench was created and is led by{' '}
          <strong>
            <a
              href="https://github.com/webdevsamran"
              target="_blank"
              rel="noopener noreferrer"
            >
              @webdevsamran
            </a>
          </strong>{' '}
          — original creator, founder and lead maintainer.
        </p>
      </section>

      <section className="card">
        <h2>Mission</h2>
        <p>
          People choosing hardware for local AI deserve measurements, not
          marketing. AIHWBench publishes reproducible benchmark results from
          real machines, with a methodology that is fully public and a dataset
          that anyone can audit, regenerate and extend.
        </p>
      </section>

      <section className="card">
        <h2>Principles</h2>
        <ul>
          <li><strong>Scientific honesty:</strong> unmeasured metrics stay null; nothing is fabricated or interpolated.</li>
          <li><strong>Vendor neutrality:</strong> no paid placement, no favored hardware, no influence over rankings.</li>
          <li><strong>Local-first & privacy:</strong> benchmarks run locally; published data contains hardware-class identifiers only.</li>
          <li><strong>Reproducibility:</strong> fixed seeds, recorded environments, checksummed models, portable bundles.</li>
          <li><strong>Open governance:</strong> Apache-2.0 licensed, community contributions welcome.</li>
        </ul>
      </section>

      <section className="card">
        <h2>License & attribution</h2>
        <p>
          The project is Apache-2.0 licensed. Attribution of the original
          creator is preserved in the repository (<code>AUTHORS.md</code>,{' '}
          <code>NOTICE</code>, <code>CITATION.cff</code>) and in this site's
          footer.
        </p>
      </section>

      <section className="card">
        <h2>Project links</h2>
        <ul>
          <li>
            <a
              href="https://github.com/webdevsamran/local-ai-hardware-bench"
              target="_blank"
              rel="noopener noreferrer"
            >
              GitHub repository
            </a>
          </li>
          <li>
            <a
              href="https://github.com/webdevsamran/local-ai-hardware-bench/issues"
              target="_blank"
              rel="noopener noreferrer"
            >
              Issues & hardware-needed requests
            </a>
          </li>
        </ul>
      </section>
    </div>
  )
}