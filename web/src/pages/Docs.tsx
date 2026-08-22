import { Link } from 'react-router-dom'
import CopyCommand from '../components/CopyCommand'

export default function Docs() {
  return (
    <div>
      <h1 className="page-title">Documentation & quick start</h1>
      <p className="page-sub">
        Everything needed to benchmark your machine and contribute a result.
      </p>

      <section className="card">
        <h2>1. Install</h2>
        <p>Python 3.10+ required. The CLI is stdlib-first; heavy extras are optional.</p>
        <CopyCommand command="pip install aihwbench" />
      </section>

      <section className="card">
        <h2>2. Check your machine</h2>
        <p>
          <code>doctor</code> reports detected hardware, runtime readiness and
          benchmark preconditions. <code>self-test</code> additionally measures
          timer resolution, background load, power source and thermal state.
        </p>
        <CopyCommand command="aihwbench doctor" />
        <CopyCommand command="aihwbench self-test" />
      </section>

      <section className="card">
        <h2>3. Run a benchmark</h2>
        <p>Ollama (model tag):</p>
        <CopyCommand command="aihwbench benchmark --runtime ollama --model qwen2.5:0.5b-instruct-q4_K_M" />
        <p>llama.cpp (local GGUF file):</p>
        <CopyCommand command="aihwbench benchmark --runtime llama.cpp --model-path /path/to/model-q4_k_m.gguf" />
        <p>
          Useful flags: <code>--iterations</code>, <code>--max-tokens</code>,{' '}
          <code>--seed</code>, <code>--device</code>.
        </p>
      </section>

      <section className="card">
        <h2>4. Validate & inspect</h2>
        <CopyCommand command="aihwbench validate results/raw/<run-id>.json" />
        <CopyCommand command="aihwbench report results/raw/<run-id>.json" />
        <CopyCommand command="aihwbench analyze results/raw/<run-id>.json" />
      </section>

      <section className="card">
        <h2>5. Advanced workflows</h2>
        <ul>
          <li><code>aihwbench sweep</code> — parameter sweeps over context, tokens, device.</li>
          <li><code>aihwbench run manifest.json</code> — declarative experiment matrices.</li>
          <li><code>aihwbench capacity</code> — concurrency ladder with p95/p99 and sustainable concurrency.</li>
          <li><code>aihwbench tune</code> — auto-tune threads/batch/context/GPU layers.</li>
          <li><code>aihwbench quantization</code> — compare quantization variants from published results.</li>
          <li><code>aihwbench fit</code> / <code>aihwbench recommend</code> — memory-fit estimates and configuration advice.</li>
          <li><code>aihwbench bundle</code> / <code>aihwbench verify-bundle</code> — portable, checksummed result bundles.</li>
          <li><code>aihwbench env-diff A B</code> / <code>aihwbench reproduce</code> — comparability and reproduction checks.</li>
          <li><code>aihwbench export-as --format csv</code> — JSON/CSV/Markdown/SQLite exports.</li>
        </ul>
      </section>

      <section className="card">
        <h2>6. Contribute a result</h2>
        <p>
          Validate your result, then open a pull request adding it to{' '}
          <code>results/published/</code>. CI runs schema validation, the
          privacy scan and data-quality checks automatically. See the{' '}
          <Link to="/community">community page</Link> for the full guide.
        </p>
      </section>

      <section className="card">
        <h2>Further reading</h2>
        <ul>
          <li><Link to="/methodology">Methodology</Link> — how measurements are taken and validated.</li>
          <li><Link to="/dataset">Dataset explorer</Link> — the generated data files.</li>
          <li>Repository docs: <code>ARCHITECTURE.md</code>, <code>CONTRIBUTING.md</code>, <code>TROUBLESHOOTING.md</code>.</li>
        </ul>
      </section>
    </div>
  )
}