import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useDataset } from '../lib/useDataset'
import { Loading, ErrorState } from '../components/States'
import {
  recommendForQuiz,
  type HardwareTier,
  type Priority,
  type QuizAnswers,
  type UseCase,
} from '../lib/matchmaker'
import { fmtNum } from '../lib/format'

// The quiz asks about the task, because that is what people know about
// themselves. It answers from measured results where any exist, and says
// plainly when none do — a "no measured answer yet" is a real answer, and far
// more useful than a confident recommendation drawn from nothing.

const USE_CASES: { value: UseCase; label: string; hint: string }[] = [
  { value: 'chat', label: 'Chat and general questions', hint: 'Back-and-forth conversation' },
  { value: 'coding', label: 'Code completion', hint: 'Suggestions while you type' },
  {
    value: 'long_documents',
    label: 'Long documents',
    hint: 'Summarizing or querying large texts',
  },
  { value: 'agents', label: 'Agents and tool use', hint: 'Multi-step loops calling tools' },
]

const PRIORITIES: { value: Priority; label: string; hint: string }[] = [
  { value: 'speed', label: 'Speed', hint: 'Answers as fast as possible' },
  { value: 'quality', label: 'Quality', hint: 'The largest model that still runs' },
  { value: 'battery', label: 'Battery life', hint: 'Unplugged, for as long as possible' },
]

const HARDWARE: { value: HardwareTier; label: string }[] = [
  { value: 'no_gpu', label: 'No discrete GPU' },
  { value: 'small_gpu', label: 'GPU with about 8 GB' },
  { value: 'mid_gpu', label: 'GPU with about 12 GB' },
  { value: 'large_gpu', label: 'GPU with 24 GB or more' },
]

export default function Matchmaker() {
  const { dataset, loading, error, retry } = useDataset()

  const [answers, setAnswers] = useState<QuizAnswers>({
    useCase: 'chat',
    priority: 'speed',
    hardware: 'small_gpu',
    ramGb: 16,
  })

  const recommendation = useMemo(() => {
    if (!dataset) return null
    return recommendForQuiz(answers, dataset.constants, dataset.results)
  }, [dataset, answers])

  function set<K extends keyof QuizAnswers>(key: K, value: QuizAnswers[K]) {
    setAnswers((prev) => ({ ...prev, [key]: value }))
  }

  return (
    <div>
      <h1 className="page-title">Which model should I run?</h1>
      <p className="page-sub">
        Four questions about what you want to do, answered from{' '}
        <strong>published measurements</strong> where any exist. This does not
        rank models by how good they are at a task — this project measures
        speed, memory and power, not writing quality, and a quiz that claimed
        otherwise would be inventing what it does not know.
      </p>

      {loading && <Loading />}
      {error && <ErrorState message={error} onRetry={retry} />}

      {dataset && recommendation && (
        <>
          <fieldset className="quiz-group">
            <legend className="field-label">What will you use it for?</legend>
            <div className="chip-row">
              {USE_CASES.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={`chip ${answers.useCase === option.value ? 'chip-on' : ''}`}
                  aria-pressed={answers.useCase === option.value}
                  onClick={() => set('useCase', option.value)}
                >
                  <span className="chip-label">{option.label}</span>
                  <span className="chip-hint">{option.hint}</span>
                </button>
              ))}
            </div>
          </fieldset>

          <fieldset className="quiz-group">
            <legend className="field-label">What matters most?</legend>
            <div className="chip-row">
              {PRIORITIES.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={`chip ${answers.priority === option.value ? 'chip-on' : ''}`}
                  aria-pressed={answers.priority === option.value}
                  onClick={() => set('priority', option.value)}
                >
                  <span className="chip-label">{option.label}</span>
                  <span className="chip-hint">{option.hint}</span>
                </button>
              ))}
            </div>
          </fieldset>

          <fieldset className="quiz-group">
            <legend className="field-label">What are you running it on?</legend>
            <div className="chip-row">
              {HARDWARE.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={`chip ${answers.hardware === option.value ? 'chip-on' : ''}`}
                  aria-pressed={answers.hardware === option.value}
                  onClick={() => set('hardware', option.value)}
                >
                  <span className="chip-label">{option.label}</span>
                </button>
              ))}
            </div>
          </fieldset>

          <label className="field quiz-ram">
            <span className="field-label">System RAM (GB)</span>
            <input
              type="number"
              min={2}
              max={512}
              step={2}
              value={answers.ramGb}
              onChange={(e) => set('ramGb', Number(e.target.value))}
            />
          </label>

          <div
            className={`verdict verdict-${
              recommendation.evidence === 'measured'
                ? 'ok'
                : recommendation.evidence === 'estimated'
                  ? 'warn'
                  : 'unknown'
            }`}
            role="status"
          >
            <h2 className="verdict-headline">{recommendation.headline}</h2>
            <p className="verdict-detail">{recommendation.detail}</p>
            <dl className="verdict-figures">
              <div>
                <dt>Evidence</dt>
                <dd>{recommendation.evidence.replace('_', ' ')}</dd>
              </div>
              <div>
                <dt>Context needed</dt>
                <dd>{recommendation.requirements.contextLength.toLocaleString()} tokens</dd>
              </div>
              <div>
                <dt>Throughput floor</dt>
                <dd>
                  {recommendation.requirements.throughputFloorTps === null
                    ? 'not latency-sensitive'
                    : `${recommendation.requirements.throughputFloorTps} tok/s`}
                </dd>
              </div>
              <div>
                <dt>First token by</dt>
                <dd>
                  {recommendation.requirements.ttftCeilingMs === null
                    ? 'no ceiling'
                    : `${recommendation.requirements.ttftCeilingMs} ms`}
                </dd>
              </div>
            </dl>
          </div>

          <h2 className="section-title">Why these thresholds</h2>
          <ul className="measured-list">
            {recommendation.requirements.notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
          <p className="muted small">
            Every number above is a judgement about what makes a task feel
            right, not something this project measured. They are stated here so
            you can disagree with them.
          </p>

          {recommendation.matches.length > 0 && (
            <>
              <h2 className="section-title">
                Published results meeting these requirements
              </h2>
              <ul className="measured-list">
                {recommendation.matches.slice(0, 8).map((match) => (
                  <li key={match.run_id}>
                    <Link to={`/results/${match.run_id}`}>{match.model}</Link> on{' '}
                    {match.runtime}
                    {match.device ? ` (${match.device})` : ''} —{' '}
                    {match.reasons.join(', ')}
                  </li>
                ))}
              </ul>
              <p className="muted small">
                Measured on the hardware in each result, which may not resemble
                yours. Two results are only comparable when the model, runtime,
                device and protocol match — see{' '}
                <Link to="/methodology">the methodology</Link>.
              </p>
            </>
          )}

          {recommendation.sizeCeiling &&
            recommendation.sizeCeiling.estimated_total_gb !== null && (
              <>
                <h2 className="section-title">What your memory allows</h2>
                <p className="muted">
                  About{' '}
                  <strong>
                    {fmtNum(recommendation.sizeCeiling.estimated_total_gb)} GB
                  </strong>{' '}
                  of weights and overhead at {recommendation.sizeCeiling.fit_target ?? 'this budget'}.{' '}
                  {recommendation.sizeCeiling.reason}
                </p>
                <p className="muted small">
                  An estimate from a memory budget and an assumed quantization
                  density. A measured result for the same model on the same
                  hardware always beats it — see{' '}
                  <Link to="/will-it-run">the fit estimator</Link> and{' '}
                  <Link to="/recommend">the configuration recommender</Link>.
                </p>
              </>
            )}

          {recommendation.evidence !== 'measured' && (
            <p className="notice" role="note">
              Nothing published meets these requirements yet. That is a gap in
              the dataset rather than a statement about your hardware —{' '}
              <Link to="/docs">contributing a result</Link> from your machine is
              what closes it.
            </p>
          )}
        </>
      )}
    </div>
  )
}
