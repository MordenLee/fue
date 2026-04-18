import type { ReferenceItem } from './conversation'

export interface ChatMessage {
  role: 'system' | 'user' | 'assistant'
  content: string
}

export interface ChatResponse {
  content: string
  model: string
  provider: string
  summary?: string | null
}

export interface RAGChatResponse extends ChatResponse {
  references: ReferenceItem[]
}

export type SSEEvent =
  | { type: 'token'; data: string }
  | { type: 'tool_call'; data: { name: string; args: Record<string, unknown> } }
  | { type: 'citations'; data: { references: ReferenceItem[]; cite_map: Record<string, string> } }
  | { type: 'searching'; data: { query: string } }
  | { type: 'summary'; data: string }
  | { type: 'error'; data: string }
  | { type: 'progress'; data: { current: number; total: number; filename: string; status: 'parsing' | 'done' | 'error'; message?: string } }
  | { type: 'clear' }
  | { type: 'replace'; data: string }
  | { type: 'done' }

export interface StreamRAGOptions {
  kb_ids: number[]
  conversation_id?: number
  citation_style?: string
  top_k?: number
  rerank?: boolean
  existing_references?: Array<{ ref_num: number; document_file_id: number; original_filename: string; formatted_citation: string }>
}
