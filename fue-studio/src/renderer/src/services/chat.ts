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
  signal?: AbortSignal
): Promise<ChatResponse> {
  return request<ChatResponse>(`/api/chat/${modelId}`, {
    method: 'POST',
    body: JSON.stringify({ messages, conversation_id: conversationId }),
    signal
  })
}

export function ragChat(
  modelId: number,
  messages: ChatMessage[],
  options: StreamRAGOptions,
  signal?: AbortSignal
): Promise<RAGChatResponse> {
  return request<RAGChatResponse>(`/api/chat/${modelId}/rag`, {
    method: 'POST',
    body: JSON.stringify({
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
