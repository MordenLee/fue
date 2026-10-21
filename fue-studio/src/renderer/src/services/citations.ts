import { request } from './api'
import type { CitationOut, CitationCreate } from '../types/knowledge'

export const citationsService = {
  get: (kbId: number, docId: number) =>
    request<CitationOut>(`/api/knowledge-bases/${kbId}/documents/${docId}/citation`),

  upsert: (kbId: number, docId: number, data: CitationCreate) =>
    request<CitationOut>(`/api/knowledge-bases/${kbId}/documents/${docId}/citation`, {
      method: 'PUT',
      body: JSON.stringify(data)
    }),

  patch: (kbId: number, docId: number, data: Partial<CitationCreate>) =>
    request<CitationOut>(`/api/knowledge-bases/${kbId}/documents/${docId}/citation`, {
      method: 'PATCH',
      body: JSON.stringify(data)
    }),

  remove: (kbId: number, docId: number) =>
    request<void>(`/api/knowledge-bases/${kbId}/documents/${docId}/citation`, { method: 'DELETE' }),

  getFormatted: (kbId: number, docId: number, style: string) =>
    request<{ style: string; text: string }>(
      `/api/knowledge-bases/${kbId}/documents/${docId}/citation/formatted?style=${encodeURIComponent(style)}`
    )
}
