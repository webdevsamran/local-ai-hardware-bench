import { useEffect, useState } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'
import type { ReactNode } from 'react'

const NAV = [
  { to: '/', label: 'Home', end: true },
  { to: '/leaderboard', label: 'Leaderboard' },
  { to: '/hardware', label: 'Hardware' },
  { to: '/runtimes', label: 'Runtimes' },
  { to: '/models', label: 'Models' },
  { to: '/results', label: 'Results' },
  { to: '/compare', label: 'Compare' },
  { to: '/dataset', label: 'Dataset' },
  { to: '/compatibility', label: 'Compatibility' },
  { to: '/docs', label: 'Docs' },
  { to: '/methodology', label: 'Methodology' },
  { to: '/community', label: 'Community' },
  { to: '/about', label: 'About' },
]

function ThemeToggle() {
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    const stored = localStorage.getItem('aihwbench-theme')
    if (stored === 'light' || stored === 'dark') return stored
    return window.matchMedia('(prefers-color-scheme: dark)').matches
      ? 'dark'
      : 'light'
  })

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('aihwbench-theme', theme)
  }, [theme])

  return (
    <button
      type="button"
      className="theme-toggle"
      aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
      onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
    >
      {theme === 'dark' ? '☀ Light' : '☾ Dark'}
    </button>
  )
}

export default function Layout({ children }: { children: ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false)
  const location = useLocation()

  useEffect(() => {
    setMenuOpen(false)
  }, [location.pathname])

  return (
    <div className="app">
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <header className="site-header">
        <div className="container header-inner">
          <Link to="/" className="brand">
            <span className="brand-mark">AIHW</span>Bench
          </Link>
          <button
            type="button"
            className="nav-toggle"
            aria-expanded={menuOpen}
            aria-controls="site-nav"
            onClick={() => setMenuOpen((v) => !v)}
          >
            ☰ Menu
          </button>
          <nav
            id="site-nav"
            className={`site-nav${menuOpen ? ' open' : ''}`}
            aria-label="Primary"
          >
            <ul>
              {NAV.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={'end' in item ? item.end : false}
                    className={({ isActive }) =>
                      isActive ? 'nav-link active' : 'nav-link'
                    }
                  >
                    {item.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
          <ThemeToggle />
        </div>
      </header>
      <main id="main" className="container main-content">
        {children}
      </main>
      <footer className="site-footer">
        <div className="container footer-inner">
          <p>
            AIHWBench — vendor-neutral local AI benchmarking. Created and
            maintained by{' '}
            <a
              href="https://github.com/webdevsamran"
              rel="noopener noreferrer"
              target="_blank"
            >
              @webdevsamran
            </a>
            . Apache-2.0 licensed.
          </p>
          <p className="muted">
            All published numbers come from real measured runs. Missing metrics
            are shown as “—”, never estimated.
          </p>
        </div>
      </footer>
    </div>
  )
}