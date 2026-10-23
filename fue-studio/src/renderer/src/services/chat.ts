import type {
  ChatMessage,
  ChatResponse,
  RAGChatResponse,
  StreamRAGOptions,
  SSEEvent
} from '../types/chat'
import { request, streamRequest } from './api'

export function chat(
  modelId: number,
  messages: ChatMessage[],
  conversationId?: number,
  signal?: AbortSignal,
  requestId = crypto.randomUUID()
): Promise<ChatResponse> {
  signal?.addEventListener('abort', () => { void request(`/api/executions/${requestId}/cancel`, { method: 'POST' }).catch(() => {}) }, { once: true })
  return request<ChatResponse>(`/api/chat/${modelId}`, {
    method: 'POST',
    body: JSON.stringify({ messages, conversation_id: conversationId, request_id: requestId }),
    signal
  })
}

export function ragChat(
  modelId: number,
  messages: ChatMessage[],
  options: StreamRAGOptions,
  signal?: AbortSignal,
  requestId = crypto.randomUUID()
): Promise<RAGChatResponse> {
  signal?.addEventListener('abort', () => { void request(`/api/executions/${requestId}/cancel`, { method: 'POST' }).catch(() => {}) }, { once: true })
  return request<RAGChatResponse>(`/api/chat/${modelId}/rag`, {
    method: 'POST',
    body: JSON.stringify({
      request_id: requestId,
      messages,
      kb_ids: options.kb_ids,
      conversation_id: options.conversation_id,
      citation_style: options.citation_style,
      top_k: options.top_k,
      rerank: options.rerank,
      existing_references: options.existing_references ?? []
    }),
    signal
  })
}

export function streamChat(
  modelId: number,
  messages: ChatMessage[],
  conversationId?: number,
  onEvent?: (event: SSEEvent) => void
): AbortController {
  return streamRequest(
    `/api/chat/${modelId}/stream`,
    { messages, conversation_id: conversationId },
    onEvent ?? (() => {})
  )
}

export function streamRAG(
  modelId: number,
  messages: ChatMessage[],
  options: StreamRAGOptions,
  onEvent?: (event: SSEEvent) => void
): AbortController {
  return streamRequest(
    `/api/chat/${modelId}/rag/stream`,
    {
      messages,
      kb_ids: options.kb_ids,
      conversation_id: options.conversation_id,
      citation_style: options.citation_style,
      top_k: options.top_k,
      rerank: options.rerank,
      existing_references: options.existing_references ?? []
    },
    onEvent ?? (() => {})
  )
}
