import { User, Bot, Trash2, Copy, Check, Pencil, RefreshCw, X } from 'lucide-react'
import { useState, useMemo, useRef, useEffect } from 'react'
import { MarkdownLatexRenderer } from '../shared/MarkdownLatexRenderer'
import { CitationRenderer } from './CitationRenderer'
import type { MessageOut } from '../../types/conversation'
import { useI18n } from '../../i18n'

interface ChatMessageProps {
  message: MessageOut
  isStreaming?: boolean
  onCiteClick?: (refNum: number) => void
  onDelete?: (msgId: number) => void
  onEdit?: (msgId: number, content: string) => void
  onRegenerate?: (msgId: number) => void
  allKnownRefs?: Set<number>
}

export function ChatMessage({ message, isStreaming, onCiteClick, onDelete, onEdit, onRegenerate, allKnownRefs }: ChatMessageProps) {
  const isUser = message.role === 'user'
  const { t } = useI18n()
  const [copied, setCopied] = useState(false)
  const [editing, setEditing] = useState(false)
  const [editContent, setEditContent] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Pre-process markdown: fix common LLM formatting issues
  const processedContent = useMemo(() => {
    let text = message.content
    // Add newlines before headings if missing
    text = text.replace(/([^\n])(#{1,6}\s)/g, '$1\n\n$2')
    // Fix consecutive bold markers (e.g. ****) that break rendering
    text = text.replace(/\*{4,}/g, '**\n\n**')
    // Normalize LaTeX delimiters: many LLMs output \(...\) and \[...\]
    // but remark-math only recognizes $...$ and $$...$$
    // Display math: \[...\] → $$...$$
    text = text.replace(/\\\[([\s\S]*?)\\\]/g, (_m, inner) => `$$\n${inner.trim()}\n$$`)
    // Inline math: \(...\) → $...$  (use non-greedy, no newlines allowed inside)
    text = text.replace(/\\\(([^)]*?)\\\)/g, (_m, inner) => `$${inner}$`)
    return text
  }, [message.content])

  // Build set of known citation ref numbers — used by the remark plugin in MarkdownLatexRenderer
  // Include all known refs across all conversation turns so cross-turn references render as circles
  const knownCiteRefs = useMemo(() => {
    if (isUser) return undefined
    // Use the global set if provided (covers all turns), or fall back to message-local refs
    if (allKnownRefs && allKnownRefs.size > 0) return allKnownRefs
    if (!message.references || message.references.length === 0) return undefined
    return new Set(message.references.map(r => r.ref_num))
  }, [isUser, message.references, allKnownRefs])

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const handleStartEdit = () => {
    setEditContent(message.content)
    setEditing(true)
    setTimeout(() => textareaRef.current?.focus(), 0)
  }

  const handleConfirmEdit = () => {
    if (editContent.trim() && onEdit) {
      onEdit(message.id, editContent.trim())
    }
    setEditing(false)
  }

  const handleCancelEdit = () => {
    setEditing(false)
  }

  // Auto-resize textarea
  useEffect(() => {
    if (editing && textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = textareaRef.current.scrollHeight + 'px'
    }
  }, [editing, editContent])

  return (
    <div className={`group flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      <div
        className={`flex items-center justify-center w-8 h-8 rounded-full shrink-0
          ${isUser ? 'bg-blue-600' : 'bg-gray-200 dark:bg-neutral-700'}`}
      >
        {isUser ? <User className="h-4 w-4 text-white" /> : <Bot className="h-4 w-4 text-gray-600 dark:text-white" />}
      </div>
      <div className="flex-1 min-w-0">
        <div
          className={`rounded-lg px-4 py-3
            ${isUser 
              ? 'bg-blue-100 text-blue-900 dark:bg-blue-600/20 dark:text-blue-100' 
              : 'bg-gray-100 text-gray-900 dark:bg-white/5 dark:text-neutral-200'}`}
        >
          {isUser && editing ? (
            <div className="flex flex-col gap-2">
              <textarea
                ref={textareaRef}
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleConfirmEdit() }
                  if (e.key === 'Escape') handleCancelEdit()
                }}
                className="w-full text-sm bg-white/50 dark:bg-black/20 border border-blue-400/50 rounded p-2 resize-none focus:outline-none focus:border-blue-500 min-h-[60px]"
              />
              <div className="flex gap-2 justify-end">
                <button
                  onClick={handleCancelEdit}
                  className="flex items-center gap-1 px-2.5 py-1 text-xs rounded bg-black/10 dark:bg-white/10 hover:bg-black/20 dark:hover:bg-white/20 transition"
                >
                  <X className="h-3 w-3" />
                  {t('common.cancel')}
                </button>
                <button
                  onClick={handleConfirmEdit}
                  className="flex items-center gap-1 px-2.5 py-1 text-xs rounded bg-blue-600 text-white hover:bg-blue-700 transition"
                >
                  {t('chat.send_edit')}
                </button>
              </div>
            </div>
          ) : isUser ? (
            <p className="text-sm whitespace-pre-wrap message-selectable">{message.content}</p>
          ) : (
            <>
              <MarkdownLatexRenderer content={processedContent} isStreaming={isStreaming} onCiteClick={onCiteClick} knownCiteRefs={knownCiteRefs} />
              {message.references && message.references.length > 0 && (
                <CitationRenderer references={message.references} onCiteClick={onCiteClick} />
              )}
            </>
          )}
          {isStreaming && (
            <span className="inline-block w-2 h-4 bg-blue-400 animate-pulse ml-0.5" />
          )}
        </div>
        {!isStreaming && message.id > 0 && !editing && (
          <div className={`flex gap-1 mt-1 opacity-0 group-hover:opacity-100 transition-opacity ${isUser ? 'justify-end' : ''}`}>
            <button
              onClick={handleCopy}
              className="p-1 rounded text-neutral-400 hover:text-neutral-200 hover:bg-white/10 transition"
              title={t('common.copy')}
            >
              {copied ? <Check className="h-3.5 w-3.5 text-green-400" /> : <Copy className="h-3.5 w-3.5" />}
            </button>
            {isUser && onEdit && (
              <button
                onClick={handleStartEdit}
                className="p-1 rounded text-neutral-400 hover:text-neutral-200 hover:bg-white/10 transition"
                title={t('chat.edit_message')}
              >
                <Pencil className="h-3.5 w-3.5" />
              </button>
            )}
            {!isUser && onRegenerate && (
              <button
                onClick={() => onRegenerate(message.id)}
                className="p-1 rounded text-neutral-400 hover:text-neutral-200 hover:bg-white/10 transition"
                title={t('chat.regenerate')}
              >
                <RefreshCw className="h-3.5 w-3.5" />
              </button>
            )}
            {onDelete && (
              <button
                onClick={() => onDelete(message.id)}
                className="p-1 rounded text-neutral-400 hover:text-red-400 hover:bg-white/10 transition"
                title={t('chat.delete_message')}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
