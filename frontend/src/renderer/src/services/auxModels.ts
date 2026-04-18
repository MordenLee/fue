import { request } from './api'
import type { AuxModelOut } from '../types/settings'

export const auxModelsService = {
  list: () =>
    request<AuxModelOut[]>('/api/aux-models'),

  assign: (role: string, modelId: number) =>
    request<AuxModelOut>(`/api/aux-models/${role}`, {
      method: 'PUT',
      body: JSON.stringify({ model_id: modelId })
    }),

  clear: (role: string) =>
    request<void>(`/api/aux-models/${role}`, { method: 'DELETE' })
}
