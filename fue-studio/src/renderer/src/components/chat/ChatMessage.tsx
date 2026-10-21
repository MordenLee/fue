import { User, Bot, Trash2, Copy, Check, Pencil, RefreshCw, X, Plus } from 'lucide-react'
import { useState, useMemo, useRef, useEffect, useCallback } from 'react'
import { MarkdownLatexRenderer } from '../shared/MarkdownLatexRenderer'
import { CitationRenderer } from './CitationRenderer'
import { InlineModelSelector } from './ChatInput'
import { KBSelectionModal } from '../search/KBSelectionModal'
import type { MessageOut } from '../../types/conversation'
import type { RefDisplayMap } from '../../utils/citationRemap'
import type { KnowledgeBaseOut } from '../../types/knowledge'
import type { AIModelOut } from '../../types/provider'
import { applyRefRemapping, remapRefNums } from '../../utils/citationRemap'
import { useI18n } from '../../i18n'

interface ChatMessageProps {
  message: MessageOut
  isStreaming?: boolean
  onCiteClick?: (refNum: number) => void
  onDelete?: (msgId: number) => void
  onEdit?: (msgId: number, content: string, modelId: number | null, kbIds: number[]) => void
  onRegenerate?: (msgId: number) => void
  /** Global remapping from MessageList — maps this message's original ref_nums to display nums */
  refDisplayMap?: RefDisplayMap
  /** Model name + provider to display right-aligned at the bottom of the message */
  modelInfo?: { name: string; provider: string }
  /** Model list for the edit mode model selector (only needed for user messages) */
  models?: AIModelOut[]
  /** Knowledge base list for the edit mode KB selector (only needed for user messages) */
  kbs?: KnowledgeBaseOut[]
  /** Initial model id shown in the edit mode selector */
  editInitialModelId?: number | null
  /** Initial kb ids shown in the edit mode selector */
  editInitialKbIds?: number[]
}

export function ChatMessage({ message, isStreaming, onCiteClick, onDelete, onEdit, onRegenerate, refDisplayMap, modelInfo, models, kbs, editInitialModelId, editInitialKbIds }: ChatMessageProps) {
  const isUser = message.role === 'user'
  const isFirstMessage = message.position === 0
  const { t } = useI18n()
  const [copied, setCopied] = useState(false)
  const [editing, setEditing] = useState(false)
  const [editContent, setEditContent] = useState('')
  const [editModelId, setEditModelId] = useState<number | null>(null)
  const [editKbIds, setEditKbIds] = useState<number[]>([])
  const [editKbModalOpen, setEditKbModalOpen] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Pre-process markdown: fix common LLM formatting issues
  const processedContent = useMemo(() => {
    let text = message.content
    // Add newlines before headings if missing
    text = text.replace(/([^\n])(#{1,6}\s)/g, '$1\n\n$2')
    // Fix consecutive bold markers (e.g. ****) that break rendering
    text = text.replace(/\*{4,}/g, '**\n\n**')
    // Normalize LaTeX delimiters
    text = text.replace(/\\\[([\s\S]*?)\\\]/g, (_m, inner) => `$$\n${inner.trim()}\n$$`)
    text = text.replace(/\\\(([^)]*?)\\\)/g, (_m, inner) => `$${inner}$`)
    return text
  }, [message.content])

  // Apply the display remapping to message text ([orig] → [display])
  const remappedContent = useMemo(() => {
    if (!refDisplayMap || refDisplayMap.localToDisplay.size === 0) return processedContent
    return applyRefRemapping(processedContent, refDisplayMap.localToDisplay)
  }, [processedContent, refDisplayMap])

  // Remap references array to use display numbers
  const displayRefs = useMemo(() => {
    if (!message.references || message.references.length === 0) return []
    const sorted = [...message.references].sort((a, b) => a.ref_num - b.ref_num)
    if (!refDisplayMap || refDisplayMap.localToDisplay.size === 0) return sorted
    return remapRefNums(sorted, refDisplayMap.localToDisplay)
  }, [message.references, refDisplayMap])

  // Known display ref numbers — used by MarkdownLatexRenderer to style citation markers
  const knownCiteRefs = useMemo(() => {
    if (isUser) return undefined
    if (refDisplayMap && refDisplayMap.localToDisplay.size > 0) {
      return new Set<number>(refDisplayMap.localToDisplay.values())
    }
    if (displayRefs.length === 0) return undefined
    return new Set(displayRefs.map(r => r.ref_num))
  }, [isUser, refDisplayMap, displayRefs])

  // Translate display number back to original ref_num before calling parent handler
  const wrappedOnCiteClick = useCallback((displayNum: number) => {
    if (!onCiteClick) return
    if (refDisplayMap?.displayToLocals.has(displayNum)) {
      const origNums = refDisplayMap.displayToLocals.get(displayNum)!
      onCiteClick(origNums[0])
    } else {
      onCiteClick(displayNum)
    }
  }, [onCiteClick, refDisplayMap])

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const handleStartEdit = () => {
    setEditContent(message.content)
    setEditModelId(editInitialModelId ?? null)
    setEditKbIds(editInitialKbIds ?? [])
    setEditing(true)
    setTimeout(() => textareaRef.current?.focus(), 0)
  }

  const handleConfirmEdit = () => {
    if (editContent.trim() && onEdit) {
      onEdit(message.id, editContent.trim(), editModelId, editKbIds)
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
    <>
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
              {kbs && (
                <div className="flex items-center gap-1.5 flex-wrap border-b border-blue-400/20 pb-2 mb-0.5">
                  {editKbIds.map(id => {
                    const kb = kbs.find(k => k.id === id)
                    if (!kb) return null
                    return (
                      <div key={id} className="flex items-center gap-1 px-2 py-0.5 bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-300 rounded border border-blue-200 dark:border-blue-500/20 text-xs">
                        <span className="truncate max-w-[100px]">{kb.name}</span>
                        <button
                          onClick={() => setEditKbIds(editKbIds.filter(x => x !== id))}
                          className="text-blue-400 hover:text-blue-600 dark:hover:text-blue-200 rounded-full"
                        >
                          <X className="w-3 h-3" />
                        </button>
                      </div>
                    )
                  })}
                  <button
                    onClick={() => setEditKbModalOpen(true)}
                    className="flex items-center gap-1 px-2 py-0.5 rounded text-xs text-neutral-500 border border-dashed border-neutral-300 dark:border-neutral-600 hover:text-blue-600 hover:border-blue-400 transition"
                  >
                    <Plus className="w-3 h-3" />
                    {t('chat.bind_kb')}
                  </button>
                  {editKbIds.length > 0 && (
                    <button
                      onClick={() => setEditKbIds([])}
                      className="text-xs text-neutral-400 hover:text-red-500 transition-colors"
                    >
                      {t('common.clear')}
                    </button>
                  )}
                </div>
              )}
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
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  {models && models.length > 0 && (
                    <InlineModelSelector
                      value={editModelId}
                      onChange={setEditModelId}
                      models={models}
                      direction={isFirstMessage ? 'down' : 'up'}
                    />
                  )}
                </div>
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
            </div>
          ) : isUser ? (
            <p className="text-sm whitespace-pre-wrap message-selectable">{message.content}</p>
          ) : (
            <>
              <MarkdownLatexRenderer
                content={remappedContent}
                isStreaming={isStreaming}
                onCiteClick={wrappedOnCiteClick}
                knownCiteRefs={knownCiteRefs}
              />
              {!isStreaming && modelInfo && (
                <div className="flex justify-end mt-2 mb-0.5">
                  <span className="text-[10px] text-neutral-400 dark:text-neutral-500 select-none">
                    {modelInfo.name} · {modelInfo.provider}
                  </span>
                </div>
              )}
              {displayRefs.length > 0 && (
                <CitationRenderer references={displayRefs} onCiteClick={wrappedOnCiteClick} />
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
    {kbs && (
      <KBSelectionModal
        open={editKbModalOpen}
        onOpenChange={setEditKbModalOpen}
        kbs={kbs}
        selectedIds={editKbIds}
        onChange={setEditKbIds}
      />
    )}
    </>
  )
}

