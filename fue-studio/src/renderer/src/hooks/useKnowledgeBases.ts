import { useState, useEffect, useCallback } from 'react'
import { knowledgeService } from '../services/knowledge'
import type { KnowledgeBaseOut, KnowledgeBaseCreate, KnowledgeBaseUpdate } from '../types/knowledge'

export function useKnowledgeBases() {
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBaseOut[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      setLoading(true)
      const data = await knowledgeService.list()
      setKnowledgeBases(data)
    } catch (err) {
      console.error('Failed to load knowledge bases', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const create = useCallback(async (data: KnowledgeBaseCreate) => {
    const kb = await knowledgeService.create(data)
    setKnowledgeBases((prev) => [kb, ...prev])
    return kb
  }, [])

  const update = useCallback(async (id: number, data: KnowledgeBaseUpdate) => {
    const updated = await knowledgeService.update(id, data)
    setKnowledgeBases((prev) => prev.map((k) => (k.id === id ? updated : k)))
    return updated
  }, [])

  const remove = useCallback(async (id: number) => {
    await knowledgeService.remove(id)
    setKnowledgeBases((prev) => prev.filter((k) => k.id !== id))
  }, [])

  return { knowledgeBases, loading, load, create, update, remove }
}
