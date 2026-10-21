import { request, streamRequest } from './api'
import type { SSEEvent } from '../types/chat'
import type { DocumentFileOut } from '../types/knowledge'

export interface CitationParseProgress {
  current: number
  total: number
  filename: string
  status: 'parsing' | 'done' | 'error'
  message?: string
}

export type CitationParseEvent =
  | { type: 'progress'; data: CitationParseProgress }
  | { type: 'done' }
  | { type: 'error'; data: string }

export const documentsService = {
  list: (kbId: number, skip = 0, limit = 100) =>
    request<DocumentFileOut[]>(`/api/knowledge-bases/${kbId}/documents?skip=${skip}&limit=${limit}`),

  getById: (kbId: number, docId: number) =>
    request<DocumentFileOut>(`/api/knowledge-bases/${kbId}/documents/${docId}`),

  add: (kbId: number, filePath: string) =>
    request<DocumentFileOut>(`/api/knowledge-bases/${kbId}/documents`, {
      method: 'POST',
      body: JSON.stringify({ path: filePath })
    }),

  addBatch: (kbId: number, filePaths: string[], duplicateAction: string = 'add') =>
    request<DocumentFileOut[]>(`/api/knowledge-bases/${kbId}/documents/batch`, {
      method: 'POST',
      body: JSON.stringify({ paths: filePaths, duplicate_action: duplicateAction })
    }),

  reindex: (kbId: number, docId: number) =>
    request<DocumentFileOut>(`/api/knowledge-bases/${kbId}/documents/${docId}/reindex`, {
      method: 'POST'
    }),

  remove: (kbId: number, docId: number) =>
    request<void>(`/api/knowledge-bases/${kbId}/documents/${docId}`, { method: 'DELETE' }),

  batchDelete: (kbId: number, docIds: number[]) =>
    request<void>(`/api/knowledge-bases/${kbId}/documents/batch-delete`, {
      method: 'POST',
      body: JSON.stringify({ doc_ids: docIds })
    }),

  batchReindex: (kbId: number, docIds: number[]) =>
    request<DocumentFileOut[]>(`/api/knowledge-bases/${kbId}/documents/batch-reindex`, {
      method: 'POST',
      body: JSON.stringify({ doc_ids: docIds })
    }),

  batchMatchText: (kbId: number, docIds: number[], citationText: string) =>
    request<DocumentFileOut[]>(`/api/knowledge-bases/${kbId}/documents/batch-match-text`, {
      method: 'POST',
      body: JSON.stringify({ doc_ids: docIds, citation_text: citationText })
    }),

  cancel: (kbId: number, docId: number) =>
    request<DocumentFileOut>(`/api/knowledge-bases/${kbId}/documents/${docId}/cancel`, {
      method: 'POST'
    }),

  streamAIParse: (
    kbId: number,
    docIds: number[],
    onEvent: (ev: CitationParseEvent) => void
  ): AbortController =>
    streamRequest(
      `/api/knowledge-bases/${kbId}/documents/batch-ai-parse`,
      { doc_ids: docIds },
      (sseEvent: SSEEvent) => {
        if (sseEvent.type === 'done') onEvent({ type: 'done' })
        else if (sseEvent.type === 'error') onEvent({ type: 'error', data: sseEvent.data })
        else if (sseEvent.type === 'progress') onEvent({ type: 'progress', data: sseEvent.data })
      }
    )
}
