import { ToastProvider } from './contexts/ToastContext'
import { SettingsProvider } from './contexts/SettingsContext'
import App from './App'

export default function ReadyApp() {
  return <ToastProvider><SettingsProvider><App /></SettingsProvider></ToastProvider>
}
