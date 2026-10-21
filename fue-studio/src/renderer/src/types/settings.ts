export interface SettingsOut {
  chat_context_mode: 'legacy' | 'working'
  chat_input_tokens: number
  chat_output_tokens: number
  chat_run_input_tokens: number
  chat_run_output_tokens: number
  chat_summary_chars: number
  chat_summary_tokens: number

  memory_query_scope: 'disabled' | '7' | '30' | '360' | 'all'
  memory_query_mode: 'keyword' | 'rag'
  knowledge_query_mode: 'keyword' | 'rag'
  memory_embed_model_id: number | null
  language: 'zh' | 'en'
  embed_max_concurrency: number
  embed_use_model_qps: boolean
  kb_index_max_workers: number
  rag_top_k: number
  hybrid_keyword_floor_top_k: number
  default_embed_model_id: number | null
  pdf_parser: 'pdfplumber' | 'pypdf'
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
  chat_context_mode?: SettingsOut['chat_context_mode']
  chat_input_tokens?: SettingsOut['chat_input_tokens']
  chat_output_tokens?: SettingsOut['chat_output_tokens']
  chat_run_input_tokens?: SettingsOut['chat_run_input_tokens']
  chat_run_output_tokens?: SettingsOut['chat_run_output_tokens']
  chat_summary_chars?: SettingsOut['chat_summary_chars']
  chat_summary_tokens?: SettingsOut['chat_summary_tokens']

  memory_query_scope?: SettingsOut['memory_query_scope']
  memory_query_mode?: SettingsOut['memory_query_mode']
  knowledge_query_mode?: SettingsOut['knowledge_query_mode']
  memory_embed_model_id?: number | null
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
