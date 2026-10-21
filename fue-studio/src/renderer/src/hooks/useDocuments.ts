import { useState, useEffect, useCallback, useRef } from 'react'
import { documentsService } from '../services/documents'
import type { DocumentFileOut } from '../types/knowledge'

export function useDocuments(kbId: number | null) {
  const [documents, setDocuments] = useState<DocumentFileOut[]>([])
  const [loading, setLoading] = useState(false)
  const pollTimer = useRef<ReturnType<typeof setInterval>>(undefined)

  const load = useCallback(async () => {
    if (!kbId) { setDocuments([]); return }
    try {
      setLoading(true)
      const data = await documentsService.list(kbId)
      setDocuments(data)
    } catch (err) {
      console.error('Failed to load documents', err)
    } finally {
      setLoading(false)
    }
  }, [kbId])

  useEffect(() => { load() }, [load])

  // Poll for processing documents
  useEffect(() => {
    const processingStatuses = new Set(['pending', 'parsing', 'cleaning', 'chunking', 'embedding', 'processing'])
    const hasProcessing = documents.some((d) => processingStatuses.has(d.status))
    if (hasProcessing && kbId) {
      pollTimer.current = setInterval(async () => {
        try {
          const data = await documentsService.list(kbId)
          setDocuments(data)
          const stillProcessing = data.some((d) => processingStatuses.has(d.status))
          if (!stillProcessing) clearInterval(pollTimer.current)
        } catch { /* ignore */ }
      }, 2000)
    }
    return () => clearInterval(pollTimer.current)
  }, [documents, kbId])

  const addBatch = useCallback(async (paths: string[], duplicateAction: string = 'add') => {
    if (!kbId) return
    const result = await documentsService.addBatch(kbId, paths, duplicateAction)
    // Reload full list to get consistent state
    const data = await documentsService.list(kbId)
    setDocuments(data)
    return result
  }, [kbId])

  const reindex = useCallback(async (docId: number) => {
    if (!kbId) return
    const updated = await documentsService.reindex(kbId, docId)
    setDocuments((prev) => prev.map((d) => (d.id === docId ? updated : d)))
  }, [kbId])

  const remove = useCallback(async (docId: number) => {
    if (!kbId) return
    await documentsService.remove(kbId, docId)
    setDocuments((prev) => prev.filter((d) => d.id !== docId))
  }, [kbId])

  const batchDelete = useCallback(async (docIds: number[]) => {
    if (!kbId) return
    await documentsService.batchDelete(kbId, docIds)
    setDocuments((prev) => prev.filter((d) => !docIds.includes(d.id)))
  }, [kbId])

  const batchReindex = useCallback(async (docIds: number[]) => {
    if (!kbId) return
    const updated = await documentsService.batchReindex(kbId, docIds)
    setDocuments((prev) =>
      prev.map((d) => {
        const u = updated.find((u) => u.id === d.id)
        return u ?? d
      })
    )
  }, [kbId])

  const batchMatchText = useCallback(async (docIds: number[], citationText: string) => {
    if (!kbId) return
    const updated = await documentsService.batchMatchText(kbId, docIds, citationText)
    setDocuments((prev) =>
      prev.map((d) => {
        const u = updated.find((u) => u.id === d.id)
        return u ?? d
      })
    )
  }, [kbId])

  const cancel = useCallback(async (docId: number) => {
    if (!kbId) return
    const updated = await documentsService.cancel(kbId, docId)
    setDocuments((prev) => prev.map((d) => (d.id === docId ? updated : d)))
  }, [kbId])

  return { documents, loading, load, addBatch, reindex, remove, batchDelete, batchReindex, batchMatchText, cancel }
}
