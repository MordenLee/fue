import { useState, useCallback } from 'react'
import { knowledgeService } from '../services/knowledge'
import type { SearchResult } from '../types/knowledge'
import type { SearchOptions } from '../types/search'

export function useKBSearch() {
  const [results, setResults] = useState<SearchResult[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const search = useCallback(async (query: string, opts: SearchOptions): Promise<SearchResult[]> => {
    if (!query.trim() || opts.kbIds.length === 0) return []

    const execute = async (): Promise<SearchResult[]> => {
      // Search each KB in parallel, tagging each result with its source kb_id
      const promises = opts.kbIds.map((kbId) =>
        knowledgeService.search(kbId, query, {
          search_type: opts.searchType,
          top_k: opts.topK,
          rerank: opts.rerank,
          diversity: opts.diversity
        }).then(rows => rows.map(r => ({ ...r, kb_id: kbId })))
      )
      const allResults = await Promise.all(promises)
      let merged: SearchResult[] = allResults.flat().sort((a, b) => b.score - a.score)

      // Diversity: deduplicate by filename across all KBs (backend only deduplicates within a single KB)
      if (opts.diversity) {
        const seen = new Map<string, SearchResult>()
        for (const r of merged) {
          if (!seen.has(r.original_filename) || r.score > seen.get(r.original_filename)!.score) {
            seen.set(r.original_filename, r)
          }
        }
        merged = Array.from(seen.values()).sort((a, b) => b.score - a.score)
      }

      // Always enforce global topK ceiling after merging across KBs
      const final = merged.slice(0, opts.topK)
      setResults(final)
      return final
    }

    try {
      setIsSearching(true)
      setError(null)
      return await execute()
    } catch (err) {
      // Retry once for transient network errors (TypeError: Failed to fetch)
      if (err instanceof TypeError) {
        try {
          await new Promise((resolve) => setTimeout(resolve, 800))
          return await execute()
        } catch (retryErr) {
          setError(retryErr instanceof Error ? retryErr.message : 'Search failed')
          setResults([])
          return []
        }
      }
      setError(err instanceof Error ? err.message : 'Search failed')
      setResults([])
      return []
    } finally {
      setIsSearching(false)
    }
  }, [])

  const loadCachedResults = useCallback((cached: SearchResult[]) => {
    setResults(cached)
    setError(null)
  }, [])

  const clear = useCallback(() => {
    setResults([])
    setError(null)
  }, [])

  return { results, isSearching, error, search, clear, loadCachedResults }
}
