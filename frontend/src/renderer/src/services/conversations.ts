import { request } from './api'
import type {
  ConversationOut,
  ConversationDetail,
  ConversationCreate,
  ConversationUpdate,
  ConversationSearchResult,
  MessageOut
} from '../types/conversation'

export const conversationsService = {
  list: (skip = 0, limit = 100) =>
    request<ConversationOut[]>(`/api/conversations?skip=${skip}&limit=${limit}`),

  search: (query: string) =>
    request<ConversationSearchResult[]>(`/api/conversations/search?q=${encodeURIComponent(query)}`),

  getById: (id: number) =>
    request<ConversationDetail>(`/api/conversations/${id}`),

  create: (data: ConversationCreate) =>
    request<ConversationOut>('/api/conversations', {
      method: 'POST',
      body: JSON.stringify(data)
    }),

  update: (id: number, data: ConversationUpdate) =>
    request<ConversationOut>(`/api/conversations/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data)
    }),

  remove: (id: number) =>
    request<void>(`/api/conversations/${id}`, { method: 'DELETE' }),

  removeAll: () =>
    request<void>('/api/conversations', { method: 'DELETE' }),

  getMessages: (convId: number) =>
    request<MessageOut[]>(`/api/conversations/${convId}/messages`),

  appendMessages: (convId: number, messages: { role: string; content: string }[]) =>
    request<MessageOut[]>(`/api/conversations/${convId}/messages`, {
      method: 'POST',
      body: JSON.stringify(messages)
    }),

  removeMessage: (convId: number, msgId: number) =>
    request<void>(`/api/conversations/${convId}/messages/${msgId}`, { method: 'DELETE' }),

  removeMessageAndAfter: (convId: number, msgId: number) =>
    request<void>(`/api/conversations/${convId}/messages/${msgId}/after`, { method: 'DELETE' }),

  updateMessage: (convId: number, msgId: number, content: string) =>
    request<MessageOut>(`/api/conversations/${convId}/messages/${msgId}`, {
      method: 'PATCH',
      body: JSON.stringify({ content })
    }),

  clearMessages: (convId: number) =>
    request<void>(`/api/conversations/${convId}/messages`, { method: 'DELETE' })
}
