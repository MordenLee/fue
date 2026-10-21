import { request } from './api'
import type { SettingsOut, SettingsUpdate } from '../types/settings'

export const settingsService = {
  memoryStatus: () => request<{pairs: number; events: number; keyword_indexed: number; vector_indexed: number; vector_errors: number}>('/api/memory/status'),
  retryMemory: () => request<{queued: boolean}>('/api/memory/retry', {method: 'POST'}),
  get: () =>
    request<SettingsOut>('/api/settings'),

  update: (data: SettingsUpdate) =>
    request<SettingsOut>('/api/settings', {
      method: 'PUT',
      body: JSON.stringify(data)
    }),

  reset: () =>
    request<SettingsOut>('/api/settings/reset', { method: 'POST' })
}
