// Trust-state and metadata badges. States mirror benchmark/quality.py
// TRUST_STATES; "verified" only appears when maintainers have marked it.

const TRUST_LABELS: Record<string, string> = {
  unreviewed: 'Unreviewed',
  verified: 'Verified',
  flagged: 'Flagged for review',
  invalidated: 'Invalidated',
  superseded: 'Superseded',
}

export function TrustBadge({ state }: { state?: string }) {
  const s = state ?? 'unreviewed'
  return (
    <span className={`badge trust-${s}`} title={`Trust state: ${TRUST_LABELS[s] ?? s}`}>
      {TRUST_LABELS[s] ?? s}
    </span>
  )
}

export function Tag({ children }: { children: React.ReactNode }) {
  return <span className="badge tag">{children}</span>
}

export function EstimateBadge({ children }: { children?: React.ReactNode }) {
  return (
    <span className="badge estimate" title="This value is an estimate, not a measurement">
      {children ?? 'Estimate'}
    </span>
  )
}