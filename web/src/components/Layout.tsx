import { useEffect, useState } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'
import { useSeo } from '../lib/useSeo'
import type { ReactNode } from 'react'

const NAV = [
  { to: '/', label: 'Home', end: true },
  { to: '/leaderboard', label: 'Leaderboard' },
  { to: '/will-it-run', label: 'Will it run?' },
  { to: '/recommend', label: 'Recommend' },
  { to: '/matchmaker', label: 'Matchmaker' },
  { to: '/local-vs-cloud', label: 'Local vs cloud' },
  { to: '/frontiers', label: 'Frontiers' },
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
  // Reading localStorage/matchMedia during the initial state would throw when
  // the page is prerendered, where there is no window. Start from the
  // server-safe default and adopt the reader's real preference on mount; the
  // inline script in index.html sets data-theme before first paint, so this
  // never causes a flash.
  const [theme, setTheme] = useState<'light' | 'dark'>('light')
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    let initial: 'light' | 'dark' = 'light'
    try {
      const stored = localStorage.getItem('aihwbench-theme')
      if (stored === 'light' || stored === 'dark') initial = stored
      else if (window.matchMedia('(prefers-color-scheme: dark)').matches)
        initial = 'dark'
    } catch {
      // Private mode or blocked storage: the default stands.
    }
    setTheme(initial)
    setMounted(true)
  }, [])

  useEffect(() => {
    if (!mounted) return
    document.documentElement.dataset.theme = theme
    try {
      localStorage.setItem('aihwbench-theme', theme)
    } catch {
      // Persisting the choice is a convenience, never a requirement.
    }
  }, [theme, mounted])

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

  // Every route gets its own title, description and canonical URL. Doing it
  // here rather than per page means a new page cannot forget to.
  useSeo()

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