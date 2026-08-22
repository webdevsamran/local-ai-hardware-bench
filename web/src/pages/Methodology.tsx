import { Link } from 'react-router-dom'

export default function Methodology() {
  return (
    <div>
      <h1 className="page-title">Methodology</h1>
      <p className="page-sub">
        How AIHWBench measures, validates and publishes results. The short
        version: fixed workloads, recorded environments, honest nulls.
      </p>

      <section className="card">
        <h2>Measurement protocol</h2>
        <ul>
          <li>
            <strong>Fixed workload:</strong> a versioned prompt with a fixed
            max-token budget, temperature 0 and a fixed seed (default 42) so
            runs are comparable.
          </li>
          <li>
            <strong>Warmup + repetitions:</strong> warmup runs prime caches;
            the reported metrics come from repeated measured iterations.
          </li>
          <li>
            <strong>Recorded environment:</strong> OS, CPU (physical/logical
            cores), GPU + VRAM, RAM, runtime name and exact version, model
            checksum, device selection and power profile are stored with every
            result.
          </li>
          <li>
            <strong>Honest nulls:</strong> a metric that could not be measured
            (e.g. power without telemetry hardware) is stored as{' '}
            <code>null</code> and displayed as “—”. It is never estimated.
          </li>
        </ul>
      </section>

      <section className="card">
        <h2>Metrics</h2>
        <dl className="kv-list">
          <dt>TTFT</dt>
          <dd>Time from request submission to the first generated token.</dd>
          <dt>Generation throughput</dt>
          <dd>Generated tokens per second across the measured iterations.</dd>
          <dt>Prompt throughput</dt>
          <dd>Prompt (prefill) tokens processed per second, when the runtime exposes it.</dd>
          <dt>Latency percentiles</dt>
          <dd>P50/P95 of total request latency across iterations.</dd>
          <dt>Memory</dt>
          <dd>Peak RAM and VRAM observed during the run.</dd>
          <dt>Power & energy</dt>
          <dd>Average power draw and derived perf-per-watt, only when a telemetry source was available.</dd>
        </dl>
      </section>

      <section className="card">
        <h2>Validation pipeline</h2>
        <ul>
          <li>Schema validation against the versioned result schema.</li>
          <li>Privacy scan (user paths, MAC addresses, emails, serial-like strings).</li>
          <li>Provenance hashing: SHA-256 over canonical JSON of result, environment and model identity.</li>
          <li>Reproducibility completeness score — metadata completeness only, explicitly not a validity claim.</li>
          <li>Anomaly flags request human review; nothing is auto-rejected as fraudulent.</li>
        </ul>
      </section>

      <section className="card">
        <h2>What we do not do</h2>
        <ul>
          <li>No synthetic or interpolated benchmark numbers.</li>
          <li>No composite “overall score” that hides trade-offs.</li>
          <li>No paid placement or vendor-influenced rankings.</li>
          <li>No claims of certification — see the{' '}
            <Link to="/planned/certification">future certification definitions</Link>.
          </li>
        </ul>
      </section>
    </div>
  )
}