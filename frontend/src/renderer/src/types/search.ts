export interface SearchHistoryItem {
  id: string
  query: string
  kbIds: number[]
  searchType: 'semantic' | 'keyword' | 'hybrid'
  topK: number
  rerank: boolean
  diversity: boolean
  resultCount: number
  createdAt: string
  folderId: string | null
}

export interface SearchOptions {
  kbIds: number[]
  searchType: 'semantic' | 'keyword' | 'hybrid'
  topK: number
  rerank: boolean
  diversity: boolean
}
