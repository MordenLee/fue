import { useState, useEffect, useCallback } from 'react'
import { conversationsService } from '../services/conversations'
import type { MessageOut } from '../types/conversation'

export function useMessages(conversationId: number | null) {
  const [messages, setMessages] = useState<MessageOut[]>([])
  const [loading, setLoading] = useState(false)

  /**
   * Reload messages from the DB.
   *
   * @param retainLocal  An optional locally-constructed message (temp ID) that
   *   should be appended to the DB result if the DB doesn't already contain it
   *   (identified by matching role + content).  This prevents a DB write failure
   *   from silently discarding a just-received assistant response.
   */
  const load = useCallback(async (retainLocal?: MessageOut) => {
    if (!conversationId) { setMessages([]); return }
    try {
      setLoading(true)
      const data = await conversationsService.getMessages(conversationId)
      if (retainLocal) {
        const inDb = data.some(
          (m) => m.role === retainLocal.role && m.content === retainLocal.content
        )
        setMessages(inDb ? data : [...data, retainLocal])
      } else {
        setMessages(data)
      }
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
