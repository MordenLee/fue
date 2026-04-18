export interface SettingsOut {
  language: 'zh' | 'en'
  embed_max_concurrency: number
  rag_top_k: number
  default_embed_model_id: number | null
  pdf_parser: 'pdfplumber' | 'pymupdf' | 'pypdf'
  docx_parser: 'python-docx' | 'markitdown'
  doc_clean_model_id: number | null
  chat_summary_model_id: number | null
  info_extract_model_id: number | null
  doc_clean_keep_references: boolean
  doc_clean_keep_annotations: boolean
}

export interface SettingsUpdate {
  language?: 'zh' | 'en'
  embed_max_concurrency?: number
  rag_top_k?: number
  default_embed_model_id?: number | null
  pdf_parser?: SettingsOut['pdf_parser']
  docx_parser?: SettingsOut['docx_parser']
  doc_clean_model_id?: number | null
  chat_summary_model_id?: number | null
  info_extract_model_id?: number | null
  doc_clean_keep_references?: boolean
  doc_clean_keep_annotations?: boolean
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
