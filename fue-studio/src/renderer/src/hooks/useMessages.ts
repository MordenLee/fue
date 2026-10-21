import { useState, useEffect, useCallback } from 'react'
import { conversationsService } from '../services/conversations'
import type { MessageOut } from '../types/conversation'

function normalizeMessageContent(content: string): string {
  // Align comparison across formats like [CITE-1] and [1] to avoid
  // false negatives when matching local temp assistant messages to DB rows.
  return content
    .replace(/\[CITE-(\d+)\]/g, '[$1]')
    .replace(/\s+/g, ' ')
    .trim()
}

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
        const normalizedRetain = normalizeMessageContent(retainLocal.content)
        const inDb = data.some((m) => {
          if (m.role !== retainLocal.role) return false

          // Temp local message ids are negative. For them, matching by position is
          // the most stable way to identify the persisted DB record.
          if (retainLocal.id <= 0 && m.position === retainLocal.position) {
            return true
          }

          return normalizeMessageContent(m.content) === normalizedRetain
        })
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
    // Backend atomically records revisions and truncates the live answer chain.
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
