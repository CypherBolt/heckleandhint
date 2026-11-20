import React, { Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { LangProvider } from './i18n'
import { AppToaster } from './toaster'

// Each screen loads only its own code: phones on bar Wi-Fi skip the TV/host bundles.
const Landing = lazy(() => import('./pages/Landing'))
const Host = lazy(() => import('./pages/Host'))
const Screen = lazy(() => import('./pages/Screen'))
const Join = lazy(() => import('./pages/Join'))
const Play = lazy(() => import('./pages/Play'))
const Recap = lazy(() => import('./pages/Recap'))
const Report = lazy(() => import('./pages/Report'))
import './styles.css'

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <LangProvider>
      <BrowserRouter>
        <Suspense fallback={<div className="page center muted">…</div>}>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/host/:code" element={<Host />} />
          <Route path="/host/:code/report" element={<Report />} />
          <Route path="/screen/:code" element={<Screen />} />
          <Route path="/join/:code" element={<Join />} />
          <Route path="/play/:code" element={<Play />} />
          <Route path="/recap/:code" element={<Recap />} />
          <Route path="*" element={<Landing />} />
        </Routes>
        </Suspense>
      </BrowserRouter>
      <AppToaster />
    </LangProvider>
  </React.StrictMode>
)
