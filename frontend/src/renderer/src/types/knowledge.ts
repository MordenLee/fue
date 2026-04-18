export interface KnowledgeBaseOut {
  id: number
  name: string
  description: string | null
  collection_name: string | null
  embed_model_id: number
  chunk_size: number
  chunk_overlap: number
  use_delimiter_split: boolean
  rerank_model_id: number | null
  folder_id: number | null
  created_at: string
  updated_at: string
  document_count: number
}

export interface KnowledgeBaseCreate {
  name: string
  description?: string | null
  embed_model_id: number
  chunk_size?: number
  chunk_overlap?: number
  use_delimiter_split?: boolean
  rerank_model_id?: number | null
}

export interface KnowledgeBaseUpdate {
  name?: string
  description?: string | null
  embed_model_id?: number
  chunk_size?: number
  chunk_overlap?: number
  use_delimiter_split?: boolean
  rerank_model_id?: number | null
  folder_id?: number | null
}

export interface DocumentFileOut {
  id: number
  knowledge_base_id: number
  original_filename: string
  file_type: string
  file_size: number
  status: 'pending' | 'parsing' | 'cleaning' | 'chunking' | 'embedding' | 'processing' | 'indexed' | 'failed' | 'cancelled'
  error_message: string | null
  chunk_count: number
  created_at: string
  indexed_at: string | null
  has_citation: boolean
  abstract: string | null
}

export interface CitationOut {
  id: number
  document_file_id: number
  citation_type: 'article' | 'book' | 'chapter' | 'thesis' | 'conference' | 'website' | 'other'
  title: string | null
  authors: string[] | null
  year: number | null
  source: string | null
  volume: string | null
  issue: string | null
  pages: string | null
  publisher: string | null
  edition: string | null
  doi: string | null
  isbn: string | null
  url: string | null
  accessed_date: string | null
  raw_citation: string | null
  extra: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

export interface CitationCreate {
  citation_type: CitationOut['citation_type']
  title?: string | null
  authors?: string[] | null
  year?: number | null
  source?: string | null
  volume?: string | null
  issue?: string | null
  pages?: string | null
  publisher?: string | null
  edition?: string | null
  doi?: string | null
  isbn?: string | null
  url?: string | null
  accessed_date?: string | null
  raw_citation?: string | null
  extra?: Record<string, unknown> | null
}

export interface SearchResult {
  document_id: number
  kb_id?: number
  original_filename: string
  chunk_index: number
  content: string
  score: number
}
