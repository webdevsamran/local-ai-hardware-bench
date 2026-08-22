import { Link } from 'react-router-dom'

/**
 * Hardware-needed page. The list below reflects platforms the project
 * genuinely lacks measured results for. It grows from real gaps in the
 * dataset — never from invented "partnerships".
 */
export default function HardwareNeeded() {
  return (
    <div>
      <h1 className="page-title">Hardware we need</h1>
      <p className="page-sub">
        AIHWBench can only publish what contributors actually measure. These
        platform classes currently have no (or very few) published results.
      </p>

      <section className="card">
        <h2>Current gaps in the dataset</h2>
        <ul>
          <li>Apple Silicon (M-series) — macOS runtimes, unified memory behavior.</li>
          <li>AMD Radeon GPUs — ROCm/Vulkan backends under Windows and Linux.</li>
          <li>Intel Arc GPUs — IPEX-LLM / SYCL runtimes.</li>
          <li>NPUs — Intel Core Ultra, Qualcomm Snapdragon X, AMD XDNA.</li>
          <li>Linux desktops and servers — most current results are Windows.</li>
          <li>Multi-GPU and NUMA-visible systems.</li>
          <li>Low-memory machines (8 GB RAM, no discrete GPU).</li>
        </ul>
        <p className="muted">
          This list is derived from the published dataset's actual coverage. As
          results arrive, entries are removed.
        </p>
      </section>

      <section className="card">
        <h2>How to help</h2>
        <ol>
          <li>
            Check <Link to="/compatibility">the compatibility matrix</Link> for
            measured coverage.
          </li>
          <li>
            Run <code>aihwbench self-test</code>, then{' '}
            <code>aihwbench benchmark</code> with a runtime available on your
            platform.
          </li>
          <li>
            Submit the validated result via pull request — see{' '}
            <Link to="/community">contributing</Link>.
          </li>
        </ol>
      </section>

      <section className="card">
        <h2>For hardware vendors</h2>
        <p>
          We welcome vendor-provided hardware or engineering time under the
          same rules as everyone else: results are published verbatim,
          methodology is public, and rankings cannot be influenced. There are
          no paid placements. Reach out via a GitHub issue on the repository.
        </p>
      </section>
    </div>
  )
}