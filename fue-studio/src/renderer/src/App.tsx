import { HashRouter, Routes, Route, Navigate } from 'react-router-dom'
import { lazy, Suspense } from 'react'
import * as TooltipPrimitive from '@radix-ui/react-tooltip'
import { NavBar } from './components/shared/NavBar'
const ChatPage = lazy(() => import('./pages/ChatPage').then(m => ({ default: m.ChatPage })))
const SearchPage = lazy(() => import('./pages/SearchPage').then(m => ({ default: m.SearchPage })))
const KnowledgePage = lazy(() => import('./pages/KnowledgePage').then(m => ({ default: m.KnowledgePage })))
const ProvidersPage = lazy(() => import('./pages/ProvidersPage').then(m => ({ default: m.ProvidersPage })))
const SettingsPage = lazy(() => import('./pages/SettingsPage').then(m => ({ default: m.SettingsPage })))

function App(): React.JSX.Element {
  return (
    <TooltipPrimitive.Provider>
    <HashRouter>
      <div className="h-screen flex flex-col bg-white dark:bg-neutral-900 text-neutral-900 dark:text-white overflow-hidden">
        {/* Titlebar drag region — occupies real space so content starts below */}
        <div className="shrink-0 h-7 drag-region bg-white dark:bg-neutral-900" />
        <div className="flex flex-1 min-h-0">
          <NavBar />
          <main className="flex-1 min-w-0 h-full">
            <Suspense fallback={<div className="p-6 text-neutral-500" role="status">…</div>}><Routes>
              <Route path="/" element={<ChatPage />} />
              <Route path="/search" element={<SearchPage />} />
              <Route path="/knowledge" element={<KnowledgePage />} />
              <Route path="/providers" element={<ProvidersPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes></Suspense>
          </main>
        </div>
      </div>
    </HashRouter>
    </TooltipPrimitive.Provider>
  )
}

export default App
