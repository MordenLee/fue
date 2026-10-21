import { useEffect, useRef, useMemo } from 'react'
import { Search, Bot } from 'lucide-react'
import { ChatMessage } from './ChatMessage'
import type { MessageOut, ReferenceItem } from '../../types/conversation'
import { ScrollArea } from '../ui/ScrollArea'
import { useI18n } from '../../i18n'
import { useSettings } from '../../contexts/SettingsContext'
import { buildGlobalCitationRemapping } from '../../utils/citationRemap'
import type { RefDisplayMap } from '../../utils/citationRemap'
import type { KnowledgeBaseOut } from '../../types/knowledge'
import type { AIModelOut } from '../../types/provider'

interface MessageListProps {
  messages: MessageOut[]
  streamingContent?: string
  isStreaming?: boolean
  isSearching?: boolean
  searchQuery?: string | null
  streamingReferences?: ReferenceItem[] | null
  onCiteClick?: (refNum: number) => void
  onDeleteMessage?: (msgId: number) => void
  onEditMessage?: (msgId: number, content: string, modelId: number | null, kbIds: number[]) => void
  onRegenerateMessage?: (msgId: number) => void
  /** Resolved model info for the current session (used by streaming message and fallback) */
  modelInfo?: { name: string; provider: string }
  /** Full model list for resolving per-message model_id */
  allModels?: AIModelOut[]
  /** All knowledge bases for edit mode KB selector */
  allKbs?: KnowledgeBaseOut[]
  /** Current session model id, used as initial value in edit mode */
  currentModelId?: number | null
  /** Current session kb ids, used as initial value in edit mode */
  currentKbIds?: number[]
}

export function MessageList({ messages, streamingContent, isStreaming, isSearching, searchQuery, streamingReferences, onCiteClick, onDeleteMessage, onEditMessage, onRegenerateMessage, modelInfo, allModels = [], allKbs, currentModelId, currentKbIds }: MessageListProps) {
  const { t } = useI18n()
  const { settings } = useSettings()
  const bottomRef = useRef<HTMLDivElement>(null)
  const citationMode = (settings?.chat_citation_mode ?? 'document') as 'document' | 'chunk'

  // Index of the last assistant message — used for session-model fallback
  const lastAssistantIdx = useMemo(
    () => messages.reduce((last, m, i) => m.role === 'assistant' ? i : last, -1),
    [messages]
  )

  // Map model id -> display info for fast per-message resolution
  const modelMap = useMemo(() => {
    const m = new Map<number, { name: string; provider: string }>()
    for (const model of allModels) {
      m.set(model.id, { name: model.display_name || model.api_name, provider: model.provider_name })
    }
    return m
  }, [allModels])

  // Build a global per-message citation remapping so inline markers in every
  // message are renumbered contiguously and cross-turn document numbers are reused.
  const globalRemapping = useMemo<Map<number, RefDisplayMap>>(() => {
    const msgData = messages
      .filter(m => m.role === 'assistant')
      .map(m => ({ id: m.id, references: m.references }))
    return buildGlobalCitationRemapping(msgData, streamingReferences ?? null, citationMode)
  }, [messages, streamingReferences, citationMode])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingContent, isSearching])

  return (
    <ScrollArea className="flex-1">
      <div className="max-w-3xl mx-auto px-4 py-6 flex flex-col gap-6">
        {messages.map((msg, idx) => {
          // Resolve model info: prefer the model stored on the message itself,
          // fall back to the session-level modelInfo only for the last assistant message.
          const perMsgInfo = msg.model_id != null ? modelMap.get(msg.model_id) : undefined
          const resolvedModelInfo = perMsgInfo ?? (idx === lastAssistantIdx ? modelInfo : undefined)

          // Show model label for every assistant message that has resolved info,
          // but not while a streaming turn is in progress (avoids duplication).
          const showModelInfo = msg.role === 'assistant' && !isStreaming && resolvedModelInfo !== undefined
          return (
            <ChatMessage
              key={msg.id}
              message={msg}
              onCiteClick={onCiteClick}
              onDelete={onDeleteMessage}
              onEdit={onEditMessage}
              onRegenerate={onRegenerateMessage}
              refDisplayMap={msg.role === 'assistant' ? globalRemapping.get(msg.id) : undefined}
              modelInfo={showModelInfo ? resolvedModelInfo : undefined}
              models={msg.role === 'user' ? allModels : undefined}
              kbs={msg.role === 'user' ? allKbs : undefined}
              editInitialModelId={msg.role === 'user' ? currentModelId : undefined}
              editInitialKbIds={msg.role === 'user' ? currentKbIds : undefined}
            />
          )
        })}
        {isStreaming && !isSearching && !streamingContent && (
          <div className="flex items-center gap-2 px-2 py-1">
            <Bot className="w-3.5 h-3.5 text-blue-400 animate-pulse shrink-0" />
            <span className="text-xs text-neutral-500 dark:text-neutral-400">{t('chat.thinking')}</span>
            <div className="flex gap-0.5 ml-1">
              <div className="w-1 h-1 rounded-full bg-blue-500 animate-bounce" style={{ animationDelay: '0ms' }} />
              <div className="w-1 h-1 rounded-full bg-blue-500 animate-bounce" style={{ animationDelay: '150ms' }} />
              <div className="w-1 h-1 rounded-full bg-blue-500 animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
          </div>
        )}
        {isStreaming && isSearching && (
          <div className="flex items-center gap-2 px-2 py-1">
            <Search className="w-3.5 h-3.5 text-blue-400 animate-pulse shrink-0" />
            <span className="text-xs text-neutral-500 dark:text-neutral-400">{t('chat.searching')}</span>
            {searchQuery && (
              <span className="text-xs text-neutral-400 dark:text-neutral-500 italic truncate max-w-[300px]">{searchQuery}</span>
            )}
            <div className="flex gap-0.5 ml-1">
              <div className="w-1 h-1 rounded-full bg-blue-500 animate-bounce" style={{ animationDelay: '0ms' }} />
              <div className="w-1 h-1 rounded-full bg-blue-500 animate-bounce" style={{ animationDelay: '150ms' }} />
              <div className="w-1 h-1 rounded-full bg-blue-500 animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
          </div>
        )}
        {isStreaming && !isSearching && !!streamingContent && (
          <ChatMessage
            message={{
              id: -1,
              conversation_id: 0,
              role: 'assistant',
              content: streamingContent,
              position: 0,
              references: streamingReferences ?? null,
              created_at: ''
            }}
            isStreaming
            onCiteClick={onCiteClick}
            refDisplayMap={globalRemapping.get(-1)}
            modelInfo={modelInfo}
          />
        )}
        <div ref={bottomRef} />
      </div>
    </ScrollArea>
  )
}

