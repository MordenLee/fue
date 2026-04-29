import { useState, useCallback, useRef } from 'react'
import { chat, ragChat, streamChat, streamRAG } from '../services/chat'
import { parseCiteMarkers } from '../utils/citation'
import type { ChatMessage, SSEEvent, StreamRAGOptions } from '../types/chat'
import type { ReferenceItem } from '../types/conversation'

interface ToolCallEvent {
  name: string
  args: Record<string, unknown>
}

export interface ChunkInfo {
  chunk_key: string
  citation_num: number
  document_id: number
  original_filename: string
  chunk_index: number
  content: string
  score: number
  formatted_citation?: string
  kb_id?: number
}

function normalizeReferenceChunks(references: ReferenceItem[]): ChunkInfo[] {
  const chunks: ChunkInfo[] = []
  const seen = new Set<string>()

  for (const r of references) {
    const nestedChunks = r.chunks && r.chunks.length > 0
      ? r.chunks
      : [{
          chunk_index: r.chunk_index ?? r.ref_num,
          chunk_content: r.chunk_content || r.formatted_citation,
          knowledge_base_id: r.knowledge_base_id,
          score: r.score,
        }]

    for (const c of nestedChunks) {
      const chunkIndex = c.chunk_index
      const chunkKey = `${r.document_file_id}:${chunkIndex}:${c.chunk_content}`
      if (seen.has(chunkKey)) continue
      seen.add(chunkKey)

      chunks.push({
        chunk_key: chunkKey,
        citation_num: r.ref_num,
        document_id: r.document_file_id,
        original_filename: r.original_filename,
        chunk_index: chunkIndex,
        content: c.chunk_content || r.formatted_citation,
        score: c.score ?? r.score ?? 0,
        formatted_citation: r.formatted_citation,
        kb_id: c.knowledge_base_id ?? r.knowledge_base_id,
      })
    }
  }

  return chunks
}

export interface UseStreamingChatReturn {
  isStreaming: boolean
  conversationId: number | null
  modelId: number | null
  isSearching: boolean
  searchQuery: string | null
  currentResponse: string
  toolCalls: ToolCallEvent[]
  retrievedChunks: ChunkInfo[]
  citations: { references: ReferenceItem[]; cite_map: Record<string, string> } | null
  error: string | null
  send: (
    messages: ChatMessage[],
    modelId: number,
    options?: StreamRAGOptions,
    conversationId?: number,
    streamingEnabled?: boolean
  ) => void
  abort: () => void
}

function toErrorMessage(err: unknown): string {
  if (typeof err === 'object' && err && 'detail' in err && typeof err.detail === 'string') {
    return err.detail
  }
  if (err instanceof Error) return err.message
  return 'Unknown error'
}

export function useStreamingChat(): UseStreamingChatReturn {
  const [isStreaming, setIsStreaming] = useState(false)
  const [conversationId, setConversationId] = useState<number | null>(null)
  const [streamModelId, setStreamModelId] = useState<number | null>(null)
  const [isSearching, setIsSearching] = useState(false)
  const [searchQuery, setSearchQuery] = useState<string | null>(null)
  const [currentResponse, setCurrentResponse] = useState('')
  const [toolCalls, setToolCalls] = useState<ToolCallEvent[]>([])
  const [retrievedChunks, setRetrievedChunks] = useState<ChunkInfo[]>([])
  const [citations, setCitations] = useState<UseStreamingChatReturn['citations']>(null)
  const [error, setError] = useState<string | null>(null)
  const controllerRef = useRef<AbortController | null>(null)
  const activeRequestIdRef = useRef(0)
  const idleTimerRef = useRef<number | null>(null)

  const clearIdleTimer = useCallback(() => {
    if (idleTimerRef.current != null) {
      window.clearTimeout(idleTimerRef.current)
      idleTimerRef.current = null
    }
  }, [])

  const armIdleTimer = useCallback((requestId: number) => {
    clearIdleTimer()
    idleTimerRef.current = window.setTimeout(() => {
      if (activeRequestIdRef.current !== requestId) return
      controllerRef.current?.abort()
      controllerRef.current = null
      setError('Stream timed out: no response from model, please retry.')
      setIsStreaming(false)
      setIsSearching(false)
    }, 120000)
  }, [clearIdleTimer])

  const handleEvent = useCallback((event: SSEEvent) => {
    switch (event.type) {
      case 'token':
        setIsSearching(false)
        setCurrentResponse((prev) => prev + event.data)
        break
      case 'searching':
        setIsSearching(true)
        setSearchQuery(event.data.query ?? null)
        break
      case 'tool_call':
        setToolCalls((prev) => [...prev, event.data])
        break
      case 'citations': {
        setIsSearching(false)
        const { references, cite_map } = event.data
        setCitations({ references, cite_map })
        setCurrentResponse((prev) => parseCiteMarkers(prev, cite_map))
        setRetrievedChunks(normalizeReferenceChunks(references))
        break
      }
      case 'clear':
        setCurrentResponse('')
        break
      case 'replace':
        setIsSearching(false)
        setCurrentResponse(event.data)
        break
      case 'summary':
        // handled externally by the page component
        break
      case 'error':
        setError(event.data)
        setIsStreaming(false)
        setIsSearching(false)
        break
      case 'done':
        setIsStreaming(false)
        setIsSearching(false)
        break
    }
  }, [])

  const send = useCallback(
    (
      messages: ChatMessage[],
      modelId: number,
      options?: StreamRAGOptions,
      conversationId?: number,
      streamingEnabled = true
    ) => {
      // Ensure only one in-flight request can update state.
      controllerRef.current?.abort()
      const requestId = activeRequestIdRef.current + 1
      activeRequestIdRef.current = requestId

      // Reset state
      setIsStreaming(true)
      setConversationId(options?.conversation_id ?? conversationId ?? null)
      setStreamModelId(modelId)
      setIsSearching(false)
      setSearchQuery(null)
      setCurrentResponse('')
      setToolCalls([])
      setRetrievedChunks([])
      setCitations(null)
      setError(null)

      if (streamingEnabled) {
        const scopedHandleEvent = (event: SSEEvent) => {
          if (activeRequestIdRef.current !== requestId) {
            return
          }
          armIdleTimer(requestId)
          handleEvent(event)
          if (event.type === 'done' || event.type === 'error') {
            clearIdleTimer()
            if (controllerRef.current === controller) {
              controllerRef.current = null
            }
          }
        }

        const controller = options
          ? streamRAG(modelId, messages, options, scopedHandleEvent)
          : streamChat(modelId, messages, conversationId, scopedHandleEvent)

        controllerRef.current = controller
        armIdleTimer(requestId)
        return
      }

      const controller = new AbortController()
      controllerRef.current = controller

      ;(async () => {
        try {
          if (options) {
            setIsSearching(true)
            const res = await ragChat(modelId, messages, options, controller.signal)
            if (controller.signal.aborted || activeRequestIdRef.current !== requestId) return

            setCurrentResponse(res.content)
            const refs = res.references ?? []
            if (refs.length > 0) {
              setCitations({ references: refs, cite_map: {} })
              setRetrievedChunks(normalizeReferenceChunks(refs))
            }
          } else {
            const res = await chat(modelId, messages, conversationId, controller.signal)
            if (controller.signal.aborted || activeRequestIdRef.current !== requestId) return
            setCurrentResponse(res.content)
          }
        } catch (err) {
          if (err instanceof Error && err.name === 'AbortError') return
          if (activeRequestIdRef.current !== requestId) return
          setError(toErrorMessage(err))
        } finally {
          if (!controller.signal.aborted && activeRequestIdRef.current === requestId) {
            setIsSearching(false)
            setIsStreaming(false)
          }
          if (controllerRef.current === controller) {
            controllerRef.current = null
          }
        }
      })()
    },
    [handleEvent, armIdleTimer, clearIdleTimer]
  )

  const abort = useCallback(() => {
    activeRequestIdRef.current += 1
    clearIdleTimer()
    controllerRef.current?.abort()
    controllerRef.current = null
    setIsStreaming(false)
    setConversationId(null)
    setStreamModelId(null)
    setIsSearching(false)
  }, [clearIdleTimer])

  return { isStreaming, conversationId, modelId: streamModelId, isSearching, searchQuery, currentResponse, toolCalls, retrievedChunks, citations, error, send, abort }
}
