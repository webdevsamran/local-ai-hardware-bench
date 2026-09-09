import { BrowserRouter, Route, Routes } from 'react-router-dom'
import type { ReactNode } from 'react'
import Layout from './components/Layout'
import Home from './pages/Home'
import Leaderboard from './pages/Leaderboard'
import HardwareExplorer from './pages/HardwareExplorer'
import HardwareDetail from './pages/HardwareDetail'
import RuntimeExplorer from './pages/RuntimeExplorer'
import RuntimeDetail from './pages/RuntimeDetail'
import ModelExplorer from './pages/ModelExplorer'
import ModelDetail from './pages/ModelDetail'
import ResultExplorer from './pages/ResultExplorer'
import ResultDetail from './pages/ResultDetail'
import Compare from './pages/Compare'
import DatasetExplorer from './pages/DatasetExplorer'
import Methodology from './pages/Methodology'
import CompatibilityMatrix from './pages/CompatibilityMatrix'
import Docs from './pages/Docs'
import Community from './pages/Community'
import HardwareNeeded from './pages/HardwareNeeded'
import Planned from './pages/Planned'
import About from './pages/About'
import NotFound from './pages/NotFound'

export function AppRoutes() {
  return (
    <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/leaderboard" element={<Leaderboard />} />
          <Route path="/hardware" element={<HardwareExplorer />} />
          <Route path="/hardware/:fingerprint" element={<HardwareDetail />} />
          <Route path="/runtimes" element={<RuntimeExplorer />} />
          <Route path="/runtimes/:name" element={<RuntimeDetail />} />
          <Route path="/models" element={<ModelExplorer />} />
          <Route path="/models/:slug" element={<ModelDetail />} />
          <Route path="/results" element={<ResultExplorer />} />
          <Route path="/results/:runId" element={<ResultDetail />} />
          <Route path="/compare" element={<Compare />} />
          <Route path="/dataset" element={<DatasetExplorer />} />
          <Route path="/methodology" element={<Methodology />} />
          <Route path="/compatibility" element={<CompatibilityMatrix />} />
          <Route path="/docs" element={<Docs />} />
          <Route path="/community" element={<Community />} />
          <Route path="/hardware-needed" element={<HardwareNeeded />} />
          <Route path="/planned/enterprise" element={<Planned kind="enterprise" />} />
          <Route
            path="/planned/certification"
            element={<Planned kind="certification" />}
          />
          <Route path="/about" element={<About />} />
          <Route path="*" element={<NotFound />} />
    </Routes>
  )
}

/**
 * Layout plus routes, without a router.
 *
 * The browser wraps this in a BrowserRouter; the prerenderer wraps the same
 * tree in a StaticRouter. Keeping the router out of here is what lets one
 * component tree serve both.
 */
export function AppShell({ children }: { children?: ReactNode }) {
  return <Layout>{children ?? <AppRoutes />}</Layout>
}

// Vite injects the deploy sub-path ('/' locally, '/local-ai-hardware-bench/'
// on GitHub Pages). React Router wants a basename with no trailing slash.
const BASENAME = (import.meta.env.BASE_URL || '/').replace(/[/]$/, '')

export default function App({ children }: { children?: ReactNode }) {
  return (
    // BrowserRouter, not HashRouter: to a crawler '/#/models/x' is the home
    // page, so every route shared one identity and none could rank on its own.
    // Real paths rely on the prerendered HTML from scripts/prerender.mjs and
    // the 404.html fallback for deep links on GitHub Pages.
    <BrowserRouter basename={BASENAME}>
      <AppShell>{children}</AppShell>
    </BrowserRouter>
  )
}
