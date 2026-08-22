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

export default function App({ children }: { children?: ReactNode }) {
  return (
    <BrowserRouter>
      <Layout>{children ?? <AppRoutes />}</Layout>
    </BrowserRouter>
  )
}
