import './assets/main.css'

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { AppErrorBoundary } from './components/shared/AppErrorBoundary'
import { Startup } from './Startup'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppErrorBoundary>
      <Startup />
    </AppErrorBoundary>
  </StrictMode>
)
