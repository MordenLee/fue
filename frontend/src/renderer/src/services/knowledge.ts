import { request, waitForBackend } from './api'
import type {
  KnowledgeBaseOut,
  KnowledgeBaseCreate,
  KnowledgeBaseUpdate,
  SearchResult
} from '../types/knowledge'

export const knowledgeService = {
  list: (skip = 0, limit = 100) =>
    request<KnowledgeBaseOut[]>(`/api/knowledge-bases?skip=${skip}&limit=${limit}`),

  getById: (id: number) =>
    request<KnowledgeBaseOut>(`/api/knowledge-bases/${id}`),

  create: (data: KnowledgeBaseCreate) =>
    request<KnowledgeBaseOut>('/api/knowledge-bases', {
      method: 'POST',
      body: JSON.stringify(data)
    }),

  update: (id: number, data: KnowledgeBaseUpdate) =>
    request<KnowledgeBaseOut>(`/api/knowledge-bases/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data)
    }),

  remove: (id: number) =>
    request<void>(`/api/knowledge-bases/${id}`, { method: 'DELETE' }),

  exportKB: async (id: number): Promise<Blob> => {
    const baseUrl = await waitForBackend()
    const res = await fetch(`${baseUrl}/api/knowledge-bases/${id}/export`)
    if (!res.ok) throw new Error('Export failed')
    return res.blob()
  },

  importKB: (file: File, embedModelId: number, name?: string) => {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('embed_model_id', String(embedModelId))
    if (name) formData.append('name', name)
    return request<KnowledgeBaseOut>('/api/knowledge-bases/import', {
      method: 'POST',
      body: formData
    })
  },

  search: (kbId: number, query: string, opts?: { search_type?: string; top_k?: number; rerank?: boolean; diversity?: boolean }) => {
    const params = new URLSearchParams({ q: query })
    if (opts?.search_type) params.set('search_type', opts.search_type)
    if (opts?.top_k) params.set('top_k', String(opts.top_k))
    if (opts?.rerank !== undefined) params.set('rerank', String(opts.rerank))
    if (opts?.diversity !== undefined) params.set('diversity', String(opts.diversity))
    return request<SearchResult[]>(`/api/knowledge-bases/${kbId}/search?${params}`)
  }
}
