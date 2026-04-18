import { request } from './api'
import type { SettingsOut, SettingsUpdate } from '../types/settings'

export const settingsService = {
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
