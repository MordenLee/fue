import zhMessages from '../../../../../i18n/zh.json'
import enMessages from '../../../../../i18n/en.json'
import { useCallback, useSyncExternalStore } from 'react'

type Messages = typeof zhMessages

const locales: Record<string, Messages> = { zh: zhMessages, en: enMessages }

const defaultLanguage = 'zh'

function resolveLanguage(lang: string | null | undefined): keyof typeof locales {
  if (!lang) return defaultLanguage
  return (lang in locales ? lang : defaultLanguage) as keyof typeof locales
}

function loadInitialLanguage(): keyof typeof locales {
  if (typeof window === 'undefined') return defaultLanguage
  const saved = window.localStorage.getItem('language')
  return resolveLanguage(saved)
}

let currentLang = loadInitialLanguage()
let messages: Messages = locales[currentLang]
const listeners = new Set<() => void>()

export function setLanguage(lang: string): void {
  const next = resolveLanguage(lang)
  if (next === currentLang) return
  currentLang = next
  messages = locales[next]

  if (typeof window !== 'undefined') {
    window.localStorage.setItem('language', next)
  }

  for (const listener of listeners) {
    listener()
  }
}

export function getLanguage(): string {
  return currentLang
}

export function subscribeLanguageChange(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function t(key: string, params?: Record<string, string | number>): string {
  const keys = key.split('.')
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let value: any = messages
  for (const k of keys) {
    value = value?.[k]
  }
  if (typeof value !== 'string') return key

  if (params) {
    return value.replace(/\{(\w+)\}/g, (_, name) => String(params[name] ?? `{${name}}`))
  }
  return value
}

export function useI18n() {
  const language = useSyncExternalStore(subscribeLanguageChange, getLanguage, getLanguage)

  const translate = useCallback((key: string, params?: Record<string, string | number>) => {
    return t(key, params)
  }, [language])

  return { language, t: translate }
}
