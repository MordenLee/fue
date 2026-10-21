import { request } from './api'
import type {
  ProviderOut,
  ProviderCreate,
  ProviderUpdate,
  ProviderTestResult
} from '../types/provider'

export const providersService = {
  list: () =>
    request<ProviderOut[]>('/api/providers'),

  getById: (id: number) =>
    request<ProviderOut>(`/api/providers/${id}`),

  create: (data: ProviderCreate) =>
    request<ProviderOut>('/api/providers', {
      method: 'POST',
      body: JSON.stringify(data)
    }),

  update: (id: number, data: ProviderUpdate) =>
    request<ProviderOut>(`/api/providers/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data)
    }),

  setEnabled: (id: number, enabled: boolean) =>
    request<ProviderOut>(`/api/providers/${id}/enabled?enabled=${enabled}`, {
      method: 'PATCH'
    }),

  remove: (id: number) =>
    request<void>(`/api/providers/${id}`, { method: 'DELETE' }),

  test: (id: number, modelId?: number) => {
    const params = modelId ? `?model_id=${modelId}` : ''
    return request<ProviderTestResult>(`/api/providers/${id}/test${params}`, {
      method: 'POST'
    })
  },

  reorder: (items: { id: number; sort_order: number }[]) =>
    request<void>('/api/providers/reorder', {
      method: 'PUT',
      body: JSON.stringify(items)
    })
}
