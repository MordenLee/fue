import { useState, useEffect, useCallback } from 'react'
import { conversationsService } from '../services/conversations'
import type { MessageOut } from '../types/conversation'

export function useMessages(conversationId: number | null) {
  const [messages, setMessages] = useState<MessageOut[]>([])
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    if (!conversationId) { setMessages([]); return }
    try {
      setLoading(true)
      const data = await conversationsService.getMessages(conversationId)
      setMessages(data)
    } catch (err) {
      console.error('Failed to load messages', err)
    } finally {
      setLoading(false)
    }
  }, [conversationId])

  useEffect(() => { load() }, [load])

  const append = useCallback(async (msgs: { role: string; content: string }[]) => {
    if (!conversationId) return []
    const added = await conversationsService.appendMessages(conversationId, msgs)
    setMessages((prev) => [...prev, ...added])
    return added
  }, [conversationId])

  const removeMessage = useCallback(async (msgId: number) => {
    if (!conversationId) return
    await conversationsService.removeMessage(conversationId, msgId)
    setMessages((prev) => prev.filter((m) => m.id !== msgId))
  }, [conversationId])

  const editAndTruncate = useCallback(async (msgId: number, newContent: string) => {
    if (!conversationId) return
    // Update the message content on the backend
    await conversationsService.updateMessage(conversationId, msgId, newContent)
    // Delete all messages after this one
    const msg = messages.find(m => m.id === msgId)
    if (msg) {
      const after = messages.filter(m => m.position > msg.position)
      for (const a of after) {
        await conversationsService.removeMessage(conversationId, a.id)
      }
    }
    // Reload to get fresh state
    await load()
  }, [conversationId, messages, load])

  const clear = useCallback(async () => {
    if (!conversationId) return
    await conversationsService.clearMessages(conversationId)
    setMessages([])
  }, [conversationId])

  const addLocal = useCallback((msg: MessageOut) => {
    setMessages((prev) => [...prev, msg])
  }, [])

  const updateLastAssistant = useCallback((content: string) => {
    setMessages((prev) => {
      const updated = [...prev]
      for (let i = updated.length - 1; i >= 0; i--) {
        if (updated[i].role === 'assistant') {
          updated[i] = { ...updated[i], content }
          break
        }
      }
      return updated
    })
  }, [])

  return { messages, loading, load, append, removeMessage, editAndTruncate, clear, addLocal, updateLastAssistant }
}
