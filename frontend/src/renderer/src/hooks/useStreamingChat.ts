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
  document_id: number
  original_filename: string
  chunk_index: number
  content: string
  score: number
  formatted_citation?: string
  kb_id?: number
}

export interface UseStreamingChatReturn {
  isStreaming: boolean
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
  const [isSearching, setIsSearching] = useState(false)
  const [searchQuery, setSearchQuery] = useState<string | null>(null)
  const [currentResponse, setCurrentResponse] = useState('')
  const [toolCalls, setToolCalls] = useState<ToolCallEvent[]>([])
  const [retrievedChunks, setRetrievedChunks] = useState<ChunkInfo[]>([])
  const [citations, setCitations] = useState<UseStreamingChatReturn['citations']>(null)
  const [error, setError] = useState<string | null>(null)
  const controllerRef = useRef<AbortController | null>(null)

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
        // Extract chunks from references — prefer actual chunk text over bibliography
        const chunks: ChunkInfo[] = references.map((r) => ({
          document_id: r.document_file_id,
          original_filename: r.original_filename,
          chunk_index: r.ref_num,
          content: r.chunk_content || r.formatted_citation,
          score: r.score ?? 0,
          formatted_citation: r.formatted_citation,
          kb_id: r.knowledge_base_id,
        }))
        setRetrievedChunks(chunks)
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
      // Reset state
      setIsStreaming(true)
      setIsSearching(false)
      setSearchQuery(null)
      setCurrentResponse('')
      setToolCalls([])
      setRetrievedChunks([])
      setCitations(null)
      setError(null)

      if (streamingEnabled) {
        const controller = options
          ? streamRAG(modelId, messages, options, handleEvent)
          : streamChat(modelId, messages, conversationId, handleEvent)

        controllerRef.current = controller
        return
      }

      const controller = new AbortController()
      controllerRef.current = controller

      ;(async () => {
        try {
          if (options) {
            setIsSearching(true)
            const res = await ragChat(modelId, messages, options, controller.signal)
            if (controller.signal.aborted) return

            setCurrentResponse(res.content)
            const refs = res.references ?? []
            if (refs.length > 0) {
              setCitations({ references: refs, cite_map: {} })
              const chunks: ChunkInfo[] = refs.map((r) => ({
                document_id: r.document_file_id,
                original_filename: r.original_filename,
                chunk_index: r.ref_num,
                content: r.chunk_content || r.formatted_citation,
                score: 0
              }))
              setRetrievedChunks(chunks)
            }
          } else {
            const res = await chat(modelId, messages, conversationId, controller.signal)
            if (controller.signal.aborted) return
            setCurrentResponse(res.content)
          }
        } catch (err) {
          if (err instanceof Error && err.name === 'AbortError') return
          setError(toErrorMessage(err))
        } finally {
          if (!controller.signal.aborted) {
            setIsSearching(false)
            setIsStreaming(false)
          }
          if (controllerRef.current === controller) {
            controllerRef.current = null
          }
        }
      })()
    },
    [handleEvent]
  )

  const abort = useCallback(() => {
    controllerRef.current?.abort()
    setIsStreaming(false)
    setIsSearching(false)
  }, [])

  return { isStreaming, isSearching, searchQuery, currentResponse, toolCalls, retrievedChunks, citations, error, send, abort }
}
