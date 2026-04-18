import { useEffect, useRef, useMemo } from 'react'
import { Search } from 'lucide-react'
import { ChatMessage } from './ChatMessage'
import type { MessageOut, ReferenceItem } from '../../types/conversation'
import { ScrollArea } from '../ui/ScrollArea'
import { useI18n } from '../../i18n'

interface MessageListProps {
  messages: MessageOut[]
  streamingContent?: string
  isStreaming?: boolean
  isSearching?: boolean
  searchQuery?: string | null
  streamingReferences?: ReferenceItem[] | null
  onCiteClick?: (refNum: number) => void
  onDeleteMessage?: (msgId: number) => void
  onEditMessage?: (msgId: number, content: string) => void
  onRegenerateMessage?: (msgId: number) => void
}

export function MessageList({ messages, streamingContent, isStreaming, isSearching, searchQuery, streamingReferences, onCiteClick, onDeleteMessage, onEditMessage, onRegenerateMessage }: MessageListProps) {
  const { t } = useI18n()
  const bottomRef = useRef<HTMLDivElement>(null)

  // Build a global set of all known citation ref numbers across all messages + streaming refs
  const allKnownRefs = useMemo(() => {
    const refs = new Set<number>()
    for (const msg of messages) {
      if (msg.role === 'assistant' && msg.references) {
        for (const r of msg.references) refs.add(r.ref_num)
      }
    }
    if (streamingReferences) {
      for (const r of streamingReferences) refs.add(r.ref_num)
    }
    return refs
  }, [messages, streamingReferences])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingContent, isSearching])

  return (
    <ScrollArea className="flex-1">
      <div className="max-w-3xl mx-auto px-4 py-6 flex flex-col gap-6">
        {messages.map((msg) => (
          <ChatMessage key={msg.id} message={msg} onCiteClick={onCiteClick} onDelete={onDeleteMessage} onEdit={onEditMessage} onRegenerate={onRegenerateMessage} allKnownRefs={allKnownRefs} />
        ))}
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
        {isStreaming && !isSearching && streamingContent !== undefined && (
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
            allKnownRefs={allKnownRefs}
          />
        )}
        <div ref={bottomRef} />
      </div>
    </ScrollArea>
  )
}
