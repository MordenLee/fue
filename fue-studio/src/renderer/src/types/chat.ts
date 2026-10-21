import type { ReferenceItem } from './conversation'

export interface ChatMessage {
  role: 'system' | 'user' | 'assistant'
  content: string
}

export interface ChatResponse {
  run_id?: string
  activity?: ActivityEvent[]
  content: string
  model: string
  provider: string
  summary?: string | null
}

export interface RAGChatResponse extends ChatResponse {
  references: ReferenceItem[]
}

export type SSEEvent =
  | { type: 'activity'; data: ActivityEvent }
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

export interface ActivityEvent {
  type: string
  id?: string
  run_id?: string
  name?: string
  step?: number
  count?: number
  status?: string
  category?: string
  input_estimated?: number
  output_estimated?: number
  input_limit?: number
  elapsed_ms?: number
  usage?: { input_tokens?: number; output_tokens?: number } | null
}

export interface StreamRAGOptions {
  kb_ids: number[]
  conversation_id?: number
  citation_style?: string
  top_k?: number
  rerank?: boolean
  existing_references?: Array<{
    ref_num: number
    document_file_id: number
    original_filename: string
    formatted_citation: string
    chunk_index?: number
    chunk_content?: string
    knowledge_base_id?: number
    score?: number
    chunks?: Array<{
      chunk_index: number
      chunk_content: string
      knowledge_base_id?: number
      score?: number
    }>
  }>
}
