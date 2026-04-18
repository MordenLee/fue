import { useState, useEffect, useCallback } from 'react'
import { conversationsService } from '../services/conversations'
import type { ConversationOut, ConversationCreate, ConversationUpdate } from '../types/conversation'

export function useConversations() {
  const [conversations, setConversations] = useState<ConversationOut[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      setLoading(true)
      const data = await conversationsService.list()
      setConversations(data)
    } catch (err) {
      console.error('Failed to load conversations', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const create = useCallback(async (data: ConversationCreate) => {
    const conv = await conversationsService.create(data)
    setConversations((prev) => [conv, ...prev])
    return conv
  }, [])

  const update = useCallback(async (id: number, data: ConversationUpdate) => {
    const updated = await conversationsService.update(id, data)
    setConversations((prev) => prev.map((c) => (c.id === id ? updated : c)))
    return updated
  }, [])

  const remove = useCallback(async (id: number) => {
    await conversationsService.remove(id)
    setConversations((prev) => prev.filter((c) => c.id !== id))
  }, [])

  const search = useCallback(async (query: string) => {
    if (!query.trim()) {
      await load()
      return
    }
    const results = await conversationsService.search(query)
    setConversations(results.map((r) => r.conversation))
  }, [load])

  return { conversations, loading, load, create, update, remove, search }
}
