import { Link, useLocation } from 'react-router-dom'

export default function NotFound() {
  const location = useLocation()
  return (
    <div className="states">
      <h1 className="page-title">404 — page not found</h1>
      <p>
        No route matches <code>{location.pathname}</code>.
      </p>
      <p className="muted">
        If you followed a link from an old bookmark, the dataset may have been
        reorganized. Try the explorers instead:
      </p>
      <div className="cta-row" style={{ justifyContent: 'center' }}>
        <Link className="btn primary" to="/">
          Home
        </Link>
        <Link className="btn secondary" to="/results">
          Results
        </Link>
        <Link className="btn secondary" to="/hardware">
          Hardware
        </Link>
        <Link className="btn secondary" to="/docs">
          Docs
        </Link>
      </div>
    </div>
  )
}