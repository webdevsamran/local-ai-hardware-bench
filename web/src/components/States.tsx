import { Link } from 'react-router-dom'

export function Loading({ label = 'Loading data…' }: { label?: string }) {
  return (
    <div className="states" role="status" aria-live="polite">
      <div className="skeleton skeleton-line w60" />
      <div className="skeleton skeleton-line w90" />
      <div className="skeleton skeleton-line w75" />
      <p className="muted">{label}</p>
    </div>
  )
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string
  onRetry?: () => void
}) {
  return (
    <div className="states error-state" role="alert">
      <h2>Something went wrong</h2>
      <p>{message}</p>
      {onRetry && (
        <button type="button" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  )
}

export function EmptyState({
  title,
  children,
}: {
  title: string
  children?: React.ReactNode
}) {
  return (
    <div className="states empty-state">
      <h2>{title}</h2>
      {children}
    </div>
  )
}

export function ContributeEmptyState({ subject }: { subject: string }) {
  return (
    <EmptyState title={`No ${subject} published yet`}>
      <p>
        This view is generated exclusively from real, validated benchmark
        results in the repository. Nothing is simulated to fill gaps.
      </p>
      <p>
        You can add the first entry by running{' '}
        <code>aihwbench benchmark</code> on your hardware and submitting a
        result — see the{' '}
        <Link to="/docs">quick-start guide</Link> and the{' '}
        <Link to="/community">contribution guide</Link>.
      </p>
    </EmptyState>
  )
}