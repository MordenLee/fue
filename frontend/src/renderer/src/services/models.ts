import { request } from './api'
import type {
  AIModelOut,
  AIModelCreate,
  AIModelUpdate,
  DefaultModels
} from '../types/provider'

export const modelsService = {
  list: (filters?: { provider_id?: number; model_type?: string; enabled_only?: boolean }) => {
    const params = new URLSearchParams()
    if (filters?.provider_id) params.set('provider_id', String(filters.provider_id))
    if (filters?.model_type) params.set('model_type', filters.model_type)
    if (filters?.enabled_only) params.set('enabled_only', 'true')
    const qs = params.toString()
    return request<AIModelOut[]>(`/api/models${qs ? '?' + qs : ''}`)
  },

  getDefaults: () =>
    request<DefaultModels>('/api/models/defaults'),

  getById: (id: number) =>
    request<AIModelOut>(`/api/models/${id}`),

  create: (data: AIModelCreate) =>
    request<AIModelOut>('/api/models', {
      method: 'POST',
      body: JSON.stringify(data)
    }),

  update: (id: number, data: AIModelUpdate) =>
    request<AIModelOut>(`/api/models/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data)
    }),

  setEnabled: (id: number, enabled: boolean) =>
    request<AIModelOut>(`/api/models/${id}/enabled?enabled=${enabled}`, {
      method: 'PATCH'
    }),

  remove: (id: number) =>
    request<void>(`/api/models/${id}`, { method: 'DELETE' })
}
