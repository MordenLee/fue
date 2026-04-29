export interface ConversationOut {
  id: number
  title: string
  summary: string | null
  model_id: number | null
  kb_ids: number[] | null
  citation_style: string
  folder_id: number | null
  created_at: string
  updated_at: string
  message_count: number
}

export interface ConversationDetail extends ConversationOut {
  messages: MessageOut[]
}

export interface MessageOut {
  id: number
  conversation_id: number
  role: 'system' | 'user' | 'assistant'
  content: string
  position: number
  references: ReferenceItem[] | null
  model_id?: number | null
  created_at: string
}

export interface ReferenceItem {
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
}

export interface ConversationSearchResult {
  conversation: ConversationOut
  matched_in_title: boolean
  matched_in_summary: boolean
  matched_messages: MatchedMessage[]
}

export interface MatchedMessage {
  message_id: number
  role: string
  content_snippet: string
}

export interface ConversationCreate {
  title?: string
  model_id?: number | null
  kb_ids?: number[] | null
  citation_style?: string
}

export interface ConversationUpdate {
  title?: string
  summary?: string | null
  model_id?: number | null
  kb_ids?: number[] | null
  citation_style?: string
  folder_id?: number | null
}
