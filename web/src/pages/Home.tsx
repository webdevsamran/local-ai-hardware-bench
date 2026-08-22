import { Link } from 'react-router-dom'
import { useDataset } from '../lib/useDataset'
import { Loading, ErrorState } from '../components/States'
import CopyCommand from '../components/CopyCommand'
import { fmtInt } from '../lib/format'

export default function Home() {
  const { dataset, loading, error, retry } = useDataset()

  return (
    <div>
      <section className="hero">
        <h1>Benchmark local AI hardware. Honestly.</h1>
        <p className="lede">
          AIHWBench is a vendor-neutral, open platform for measuring how
          runtimes like Ollama, llama.cpp, ONNX Runtime and OpenVINO perform on
          real consumer hardware. Every published number comes from a real,
          reproducible run — missing metrics are shown as “—”, never guessed.
        </p>
        <div className="cta-row">
          <Link className="btn primary" to="/leaderboard">
            View leaderboard
          </Link>
          <Link className="btn secondary" to="/docs">
            Quick start
          </Link>
          <Link className="btn secondary" to="/methodology">
            Methodology
          </Link>
        </div>
      </section>

      {loading && <Loading />}
      {error && <ErrorState message={error} onRetry={retry} />}

      {dataset && (
        <>
          <section aria-label="Dataset statistics" className="grid cols-4">
            <div className="card stat">
              <div className="value">{fmtInt(dataset.index.results_count)}</div>
              <p className="muted">Published results</p>
            </div>
            <div className="card stat">
              <div className="value">{fmtInt(dataset.index.hardware_count)}</div>
              <p className="muted">Hardware configurations</p>
            </div>
            <div className="card stat">
              <div className="value">{fmtInt(dataset.index.runtime_count)}</div>
              <p className="muted">Runtimes covered</p>
            </div>
            <div className="card stat">
              <div className="value">{fmtInt(dataset.index.model_count)}</div>
              <p className="muted">Models benchmarked</p>
            </div>
          </section>

          <section className="card">
            <h2>Measure your machine in one command</h2>
            <p>
              Install the CLI, pick a runtime you already have, and run a
              versioned workload with a fixed seed:
            </p>
            <CopyCommand command="pip install aihwbench && aihwbench doctor" />
            <CopyCommand command='aihwbench benchmark --runtime ollama --model qwen2.5:0.5b-instruct-q4_K_M' />
            <p className="muted">
              Results are saved as JSON with full environment metadata, ready to
              validate and submit.
            </p>
          </section>

          <section className="grid cols-3">
            <div className="card">
              <h3>Reproducible by design</h3>
              <p className="muted">
                Fixed seeds, recorded prompts, model checksums, runtime versions
                and environment snapshots — plus portable{' '}
                <code>.aihwbench</code> bundles with SHA-256 integrity.
              </p>
            </div>
            <div className="card">
              <h3>Vendor neutral</h3>
              <p className="muted">
                No vendor pays for placement, no hardware is favored. The
                leaderboard ranks only what was actually measured.
              </p>
            </div>
            <div className="card">
              <h3>Privacy first</h3>
              <p className="muted">
                Local-first: results contain hardware class identifiers only —
                no serial numbers, paths or personal data. Every submission is
                privacy-scanned.
              </p>
            </div>
          </section>
        </>
      )}
    </div>
  )
}