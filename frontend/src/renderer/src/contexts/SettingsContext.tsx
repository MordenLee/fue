import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import type { SettingsOut } from '../types/settings'
import { settingsService } from '../services/settings'
import { waitForBackend } from '../services/api'
import { setLanguage } from '../i18n'

interface SettingsContextType {
  settings: SettingsOut | null
  loading: boolean
  theme: 'light' | 'dark'
  streamOutputEnabled: boolean
  toggleTheme: () => void
  setStreamOutputEnabled: (enabled: boolean) => void
  reload: () => Promise<void>
  updateSettings: (data: Partial<SettingsOut>) => Promise<void>
}

const defaultSettings: SettingsOut = {
  language: 'zh',
  embed_max_concurrency: 4,
  embed_use_model_qps: false,
  kb_index_max_workers: 4,
  rag_top_k: 5,
  hybrid_keyword_floor_top_k: 10,
  default_embed_model_id: null,
  pdf_parser: 'pdfplumber',
  docx_parser: 'python-docx',
  doc_clean_model_id: null,
  chat_summary_model_id: null,
  info_extract_model_id: null,
  doc_clean_keep_references: false,
  doc_clean_keep_annotations: false,
  chat_citation_mode: 'document',
  chat_citation_style: 'apa',
  chat_history_turns: 5,
  chat_max_tool_rounds: 5,
  chat_compress_model_id: null,
}

const SettingsContext = createContext<SettingsContextType>({
  settings: defaultSettings,
  loading: false,
  theme: 'dark',
  streamOutputEnabled: true,
  toggleTheme: () => {},
  setStreamOutputEnabled: () => {},
  reload: async () => {},
  updateSettings: async () => {}
})

export function SettingsProvider({ children }: { children: React.ReactNode }) {
  const [settings, setSettings] = useState<SettingsOut | null>(null)
  const [loading, setLoading] = useState(true)
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    const saved = localStorage.getItem('theme')
    return (saved as 'light' | 'dark') || 'dark'
  })
  const [streamOutputEnabled, setStreamOutputEnabled] = useState<boolean>(() => {
    const saved = localStorage.getItem('chat_stream_output_enabled')
    return saved !== 'false'
  })

  useEffect(() => {
    const root = window.document.documentElement
    root.classList.remove('light', 'dark')
    root.classList.add(theme)
    localStorage.setItem('theme', theme)
    // Sync title bar overlay color with theme (Windows frameless window)
    window.electron?.ipcRenderer?.send('titlebar-theme', theme)
  }, [theme])

  useEffect(() => {
    localStorage.setItem('chat_stream_output_enabled', streamOutputEnabled ? 'true' : 'false')
  }, [streamOutputEnabled])

  const toggleTheme = useCallback(() => {
    setTheme(prev => (prev === 'light' ? 'dark' : 'light'))
  }, [])

  const reload = useCallback(async () => {
    try {
      await waitForBackend()
      const data = await settingsService.get()
      setSettings(data)
      if (data.language) setLanguage(data.language)
    } catch {
      setSettings(defaultSettings)
    } finally {
      setLoading(false)
    }
  }, [])

  const updateSettings = useCallback(async (data: Partial<SettingsOut>) => {
    const updated = await settingsService.update(data)
    setSettings(updated)
    if (updated.language) setLanguage(updated.language)
  }, [])

  useEffect(() => {
    reload()
  }, [reload])

  return (
    <SettingsContext.Provider
      value={{
        settings,
        loading,
        theme,
        streamOutputEnabled,
        toggleTheme,
        setStreamOutputEnabled,
        reload,
        updateSettings
      }}
    >
      {children}
    </SettingsContext.Provider>
  )
}

export function useSettings() {
  return useContext(SettingsContext)
}
