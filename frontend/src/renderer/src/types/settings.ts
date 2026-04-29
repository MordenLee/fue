export interface SettingsOut {
  language: 'zh' | 'en'
  embed_max_concurrency: number
  embed_use_model_qps: boolean
  kb_index_max_workers: number
  rag_top_k: number
  hybrid_keyword_floor_top_k: number
  default_embed_model_id: number | null
  pdf_parser: 'pdfplumber' | 'pymupdf' | 'pypdf'
  docx_parser: 'python-docx' | 'markitdown'
  doc_clean_model_id: number | null
  chat_summary_model_id: number | null
  info_extract_model_id: number | null
  doc_clean_keep_references: boolean
  doc_clean_keep_annotations: boolean
  chat_citation_mode: 'document' | 'chunk'
  chat_citation_style: 'apa' | 'mla' | 'chicago' | 'gb_t7714'
  chat_history_turns: number
  chat_max_tool_rounds: number
  chat_compress_model_id: number | null
}

export interface SettingsUpdate {
  language?: 'zh' | 'en'
  embed_max_concurrency?: number
  embed_use_model_qps?: boolean
  kb_index_max_workers?: number
  rag_top_k?: number
  hybrid_keyword_floor_top_k?: number
  default_embed_model_id?: number | null
  pdf_parser?: SettingsOut['pdf_parser']
  docx_parser?: SettingsOut['docx_parser']
  doc_clean_model_id?: number | null
  chat_summary_model_id?: number | null
  info_extract_model_id?: number | null
  doc_clean_keep_references?: boolean
  doc_clean_keep_annotations?: boolean
  chat_citation_mode?: SettingsOut['chat_citation_mode']
  chat_citation_style?: SettingsOut['chat_citation_style']
  chat_history_turns?: number
  chat_max_tool_rounds?: number
  chat_compress_model_id?: number | null
}

export interface AuxModelOut {
  role: 'doc_clean' | 'chat_summary' | 'info_extract'
  description: string
  model_id: number | null
  model_display_name: string | null
  model_api_name: string | null
  provider_name: string | null
  model_qps: number | null
}
