import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useDataset } from '../lib/useDataset'
import { Loading, ErrorState } from '../components/States'
import { validateResultDoc } from '../lib/validate'
import { scanObject, type PrivacyFinding } from '../lib/privacy'
import CopyCommand from '../components/CopyCommand'

// Submitting a result without git.
//
// The barrier is not the benchmark — someone submitting has already installed
// the CLI and run it. The barrier is fork, branch, commit, pull request. This
// page removes that by checking the file here and handing over a prefilled
// issue, so the contribution is a paste and a click.
//
// Nothing leaves the browser.
// -------------------------
// There is no server behind this site, and this page does not add one. The
// file is read with FileReader, parsed, checked and displayed locally; the
// only thing that ever leaves is what the contributor themselves sends to
// GitHub, after seeing it. That matters most for the privacy scan: a page
// that uploaded a file in order to tell you whether it was safe to upload
// would have already done the thing it was warning about.

const REPO = 'https://github.com/webdevsamran/local-ai-hardware-bench'

interface Checked {
  doc: Record<string, unknown>
  schemaIssues: string[]
  privacyFindings: PrivacyFinding[]
}

export default function Submit() {
  const { dataset, loading, error, retry } = useDataset()
  const [raw, setRaw] = useState('')
  const [parseError, setParseError] = useState<string | null>(null)

  const checked: Checked | null = useMemo(() => {
    if (!raw.trim() || !dataset) return null
    let doc: unknown
    try {
      doc = JSON.parse(raw)
    } catch {
      // Reported by the caller as "that is not a JSON object": the parser's
      // own message points at a character offset, which is not useful to
      // someone who pasted a file they did not write.
      return null
    }
    if (!doc || typeof doc !== 'object' || Array.isArray(doc)) return null
    return {
      doc: doc as Record<string, unknown>,
      schemaIssues: validateResultDoc(doc),
      privacyFindings: scanObject(doc, dataset.privacy),
    }
  }, [raw, dataset])

  function readFile(file: File) {
    const reader = new FileReader()
    reader.onload = () => {
      setRaw(String(reader.result ?? ''))
      setParseError(null)
    }
    reader.onerror = () => setParseError('Could not read that file.')
    reader.readAsText(file)
  }

  function onDrop(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault()
    const file = event.dataTransfer.files[0]
    if (file) readFile(file)
  }

  const ready =
    checked !== null &&
    checked.schemaIssues.length === 0 &&
    checked.privacyFindings.length === 0

  // A prefilled issue carrying the *summary*, not the file. A GitHub issue URL
  // has a practical length limit well below the size of a result document, so
  // a body with the whole JSON in it would be silently truncated — and a
  // truncated result is worse than none, because it looks complete.
  const issueUrl = useMemo(() => {
    if (!checked || !ready) return null
    const doc = checked.doc as {
      run_id?: string
      system?: { cpu?: string; gpu?: string; ram_gb?: number }
      runtime?: { name?: string; version?: string; device?: string }
      model?: { name?: string; quantization?: string }
      metrics?: Record<string, number | null>
      workload?: { id?: string }
      reproducibility?: { iterations?: number; warmup_runs?: number }
    }
    const m = doc.metrics ?? {}
    const body = [
      '### Result summary',
      '',
      `- Run ID: \`${doc.run_id ?? 'unknown'}\``,
      `- Hardware: ${doc.system?.cpu ?? 'unknown CPU'} / ${doc.system?.gpu ?? 'no discrete GPU'} / ${doc.system?.ram_gb ?? '?'} GB RAM`,
      `- Runtime: ${doc.runtime?.name ?? '?'} ${doc.runtime?.version ?? ''} (${doc.runtime?.device ?? '?'})`,
      `- Model: ${doc.model?.name ?? '?'}${doc.model?.quantization ? ` (${doc.model.quantization})` : ''}`,
      `- Workload: ${doc.workload?.id ?? 'default prompt'}`,
      `- Protocol: ${doc.reproducibility?.iterations ?? '?'} iterations after ${doc.reproducibility?.warmup_runs ?? '?'} warm-ups`,
      '',
      '### Measurements',
      '',
      `- Generation: ${m.generation_tokens_per_second ?? 'not measured'} tok/s`,
      `- Time to first token: ${m.ttft_ms ?? 'not measured'} ms`,
      `- Average power: ${m.average_power_watts ?? 'not measured'} W`,
      '',
      '### Checks run in the browser',
      '',
      '- [x] Parses as JSON and matches the published result shape',
      '- [x] Privacy scan found nothing, using the CLI’s own patterns',
      '',
      '### Attach the file',
      '',
      '**Drag the result JSON into this issue before submitting.** The file',
      'itself is not included above: an issue URL cannot carry it without being',
      'truncated, and a truncated result looks complete while being useless.',
      '',
      '### Anything a reviewer should know',
      '',
      '_Thermal behaviour, power profile, an unusual driver, anything odd._',
    ].join('\n')

    const params = new URLSearchParams({
      title: `Result: ${doc.model?.name ?? 'model'} on ${doc.system?.gpu ?? doc.system?.cpu ?? 'hardware'}`,
      body,
      labels: 'benchmark',
    })
    return `${REPO}/issues/new?${params.toString()}`
  }, [checked, ready])

  return (
    <div>
      <h1 className="page-title">Submit a result</h1>
      <p className="page-sub">
        Drop a result JSON here. It is checked in your browser — schema shape
        and a privacy scan using the CLI's own patterns — and if it passes you
        get a prefilled issue to open. <strong>Nothing is uploaded:</strong>{' '}
        this site has no server, and a page that uploaded your file in order
        to tell you whether it was safe to upload would have already done the
        thing it was warning about.
      </p>

      {loading && <Loading />}
      {error && <ErrorState message={error} onRetry={retry} />}

      {dataset && (
        <>
          <div
            className="dropzone"
            onDrop={onDrop}
            onDragOver={(e) => e.preventDefault()}
          >
            <label className="btn secondary">
              Choose a result file
              <input
                type="file"
                accept="application/json,.json"
                className="visually-hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0]
                  if (file) readFile(file)
                }}
              />
            </label>
            <span className="muted"> or drag it here, or paste below.</span>
          </div>

          <label className="field">
            <span className="field-label">Result JSON</span>
            <textarea
              className="submit-json"
              rows={8}
              spellCheck={false}
              value={raw}
              placeholder='{ "schema_version": "2.0", "run_id": "..." }'
              onChange={(e) => {
                setRaw(e.target.value)
                setParseError(null)
              }}
            />
          </label>

          {parseError && (
            <p className="notice" role="alert">
              {parseError}
            </p>
          )}

          {raw.trim() && checked === null && (
            <p className="notice" role="alert">
              That is not a JSON object. Paste the contents of a file from{' '}
              <code>results/raw/</code>.
            </p>
          )}

          {checked && (
            <>
              <h2 className="section-title">Schema</h2>
              {checked.schemaIssues.length === 0 ? (
                <p className="verdict verdict-ok" role="status">
                  Matches the published result shape.
                </p>
              ) : (
                <div className="verdict verdict-bad" role="status">
                  <h3 className="verdict-headline">
                    {checked.schemaIssues.length} problem
                    {checked.schemaIssues.length === 1 ? '' : 's'}
                  </h3>
                  <ul className="measured-list">
                    {checked.schemaIssues.slice(0, 10).map((issue) => (
                      <li key={issue}>{issue}</li>
                    ))}
                  </ul>
                  <p className="verdict-detail">
                    This is a shape check only. Run{' '}
                    <code>aihwbench validate &lt;file&gt; --formal</code> for
                    the authoritative verdict.
                  </p>
                </div>
              )}

              <h2 className="section-title">Privacy</h2>
              {checked.privacyFindings.length === 0 ? (
                <p className="verdict verdict-ok" role="status">
                  Nothing matched. Scanned with the same patterns{' '}
                  <code>aihwbench redact</code> uses.
                </p>
              ) : (
                <div className="verdict verdict-bad" role="status">
                  <h3 className="verdict-headline">
                    {checked.privacyFindings.length} thing
                    {checked.privacyFindings.length === 1 ? '' : 's'} you
                    probably do not want to publish
                  </h3>
                  <ul className="measured-list">
                    {checked.privacyFindings.map((finding, i) => (
                      <li key={`${finding.path}-${finding.pattern}-${i}`}>
                        <code>{finding.path}</code> — {finding.label} (
                        {finding.preview}, {finding.matchedLength} chars)
                      </li>
                    ))}
                  </ul>
                  {/* Deliberately never the full value: this page shows the
                      finding on screen, and echoing the secret to display it
                      would leak it again. */}
                  <p className="verdict-detail">
                    Run <code>aihwbench redact &lt;file&gt;</code> and submit
                    the redacted copy. Detection is deliberately over-eager, so
                    check each one — a false positive costs you a second look,
                    while a false negative publishes your home directory.
                  </p>
                </div>
              )}

              <h2 className="section-title">Submit</h2>
              {ready && issueUrl ? (
                <>
                  <p>
                    <a
                      className="btn"
                      href={issueUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Open a prefilled submission issue
                    </a>
                  </p>
                  <p className="muted">
                    The issue carries a summary of what you measured.{' '}
                    <strong>Drag the JSON file into it before submitting</strong>{' '}
                    — an issue URL cannot carry the whole document without
                    being truncated, and a truncated result looks complete
                    while being useless.
                  </p>
                  <p className="muted small">
                    Your result will arrive with trust state{' '}
                    <code>unreviewed</code>. That is not a judgement about your
                    machine: a measurement is not verified by the person who
                    produced it, including ours.
                  </p>
                </>
              ) : (
                <p className="notice" role="note">
                  Fix the problems above first. Submitting a result that fails
                  these checks costs a reviewer the time it would have taken
                  you to re-run it.
                </p>
              )}

              <h2 className="section-title">Prefer the command line?</h2>
              <CopyCommand command="aihwbench validate <file> --formal && aihwbench quality <file>" />
              <p className="muted small">
                Or open a pull request adding the file to{' '}
                <code>results/published/</code> — see{' '}
                <Link to="/docs">the contributor guide</Link>.
              </p>
            </>
          )}
        </>
      )}
    </div>
  )
}
