import '@/index.css'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { AppLayout } from '@/layouts/AppLayout'

const rootElement = document.getElementById('root')
if (!rootElement) {
  throw new Error('Root element #root not found in document.')
}

createRoot(rootElement).render(
  <StrictMode>
    <AppLayout />
  </StrictMode>,
)
