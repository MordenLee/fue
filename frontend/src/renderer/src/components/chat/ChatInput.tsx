import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { SendHorizontal, Square, Plus, X, Cpu, Check, ChevronUp, MoreHorizontal } from 'lucide-react'
import { useI18n } from '../../i18n'
import { Modal } from '../ui/Modal'
import { KBSelectionModal } from '../search/KBSelectionModal'
import { knowledgeService } from '../../services/knowledge'
import { modelsService } from '../../services/models'
import type { KnowledgeBaseOut } from '../../types/knowledge'
import type { AIModelOut } from '../../types/provider'

// --- Model usage tracking (localStorage) ---
const MODEL_USAGE_KEY = 'chat_model_usage_v1'

function getModelUsageCounts(): Record<number, number> {
  try {
    return JSON.parse(localStorage.getItem(MODEL_USAGE_KEY) ?? '{}')
  } catch {
    return {}
  }
}

function incrementModelUsage(id: number): Record<number, number> {
  const counts = getModelUsageCounts()
  counts[id] = (counts[id] ?? 0) + 1
  try {
    localStorage.setItem(MODEL_USAGE_KEY, JSON.stringify(counts))
  } catch { /* ignore quota errors */ }
  return counts
}

// --- Custom Inline Model Selector (Dropup with "More" modal) ---
export function InlineModelSelector({
  value,
  onChange,
  models,
  onBeforeChange,
  direction = 'up'
}: {
  value: number | null
  onChange: (id: number | null) => void
  models: AIModelOut[]
  onBeforeChange?: (id: number) => void
  direction?: 'up' | 'down'
}) {
  const { t } = useI18n()
  const [dropupOpen, setDropupOpen] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  const topModels = models.slice(0, 5)
  const hasMore = models.length > 5
  const selectedModel = models.find((m) => m.id === value)
  const displayLabel = selectedModel ? (selectedModel.display_name || selectedModel.api_name) : t('common.select_model')
  const popupClass = direction === 'down'
    ? 'absolute top-full left-0 mt-2 w-[300px] rounded-lg border border-neutral-200 dark:border-white/10 bg-white dark:bg-neutral-800 shadow-xl z-[100] p-1'
    : 'absolute bottom-full left-0 mb-2 w-[300px] rounded-lg border border-neutral-200 dark:border-white/10 bg-white dark:bg-neutral-800 shadow-xl z-[100] p-1'
  const chevronClass = direction === 'down'
    ? `w-3 h-3 text-neutral-400 transition-transform ${dropupOpen ? '' : 'rotate-180'}`
    : `w-3 h-3 text-neutral-400 transition-transform ${dropupOpen ? 'rotate-180' : ''}`

  // Close dropup on outside click
  useEffect(() => {
    if (!dropupOpen) return
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setDropupOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [dropupOpen])

  const selectModel = useCallback((id: number | null) => {
    if (id != null) onBeforeChange?.(id)
    onChange(id)
    setDropupOpen(false)
  }, [onChange, onBeforeChange])

  return (
    <div ref={containerRef} className="relative">
      <button
        onClick={() => setDropupOpen(!dropupOpen)}
        className="inline-flex items-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium text-neutral-600 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-white/10 transition focus:outline-none"
      >
        <Cpu className={`w-3.5 h-3.5 ${selectedModel ? 'text-blue-500' : ''}`} />
        <span className="truncate max-w-[160px]">{displayLabel}</span>
        <ChevronUp className={chevronClass} />
      </button>

      {dropupOpen && (
        <div className={popupClass}>
          {topModels.map(model => (
            <button
              key={model.id}
              onClick={() => selectModel(model.id)}
              className={`w-full flex items-center justify-between rounded-md px-3 py-1.5 text-xs cursor-pointer transition ${
                value === model.id
                  ? 'bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-300'
                  : 'text-neutral-800 dark:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-white/10'
              }`}
            >
              <span className="truncate">{model.display_name || model.api_name} <span className="text-neutral-500 dark:text-neutral-400 ml-1">{model.provider_name}</span></span>
              {value === model.id && <Check className="h-3 w-3 shrink-0 ml-2" />}
            </button>
          ))}

          {hasMore && (
            <>
              <div className="h-px bg-neutral-200 dark:bg-white/10 my-1" />
              <button
                onClick={() => { setDropupOpen(false); setModalOpen(true) }}
                className="w-full flex items-center gap-2 rounded-md px-3 py-1.5 text-xs text-blue-600 dark:text-blue-400 cursor-pointer hover:bg-blue-50 dark:hover:bg-blue-500/10 transition"
              >
                <MoreHorizontal className="w-3.5 h-3.5" />
                {t('chat.more_models')}
              </button>
            </>
          )}
        </div>
      )}

      <Modal open={modalOpen} onOpenChange={setModalOpen} title={t('chat.all_models')} className="max-w-md">
        <div className="flex flex-col gap-1 max-h-[350px] overflow-y-auto p-1 mt-2">
          {models.map(model => (
            <button
              key={model.id}
              onClick={() => {
                if (model.id != null) onBeforeChange?.(model.id)
                onChange(model.id)
                setModalOpen(false)
              }}
              className={`text-left px-3 py-2 rounded-md text-sm border flex items-center justify-between transition ${
                value === model.id ? 'border-blue-500 bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-300' : 'border-transparent hover:bg-neutral-100 dark:hover:bg-white/5 text-neutral-800 dark:text-neutral-200'
              }`}
            >
              <span>{model.display_name || model.api_name} <span className="text-xs text-neutral-500 ml-2">{model.provider_name}</span></span>
              {value === model.id && <Check className="w-4 h-4" />}
            </button>
          ))}
        </div>
      </Modal>
    </div>
  )
}

interface ChatInputProps {
  modelId: number | null
  onModelChange: (id: number | null) => void
  kbIds: number[]
  onKBChange: (ids: number[]) => void
  onSend: (content: string) => void
  onAbort?: () => void
  isStreaming?: boolean
  disabled?: boolean
}

export function ChatInput({
  modelId, onModelChange,
  kbIds, onKBChange,
  onSend, onAbort, isStreaming, disabled
}: ChatInputProps) {
  const { t } = useI18n()
  const [content, setContent] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Fetch KBs and Models natively within ChatInput
  const [kbs, setKbs] = useState<KnowledgeBaseOut[]>([])
  const [models, setModels] = useState<AIModelOut[]>([])
  const [kbModalOpen, setKbModalOpen] = useState(false)
  const [usageCounts, setUsageCounts] = useState<Record<number, number>>(getModelUsageCounts)

  // Sort models by usage frequency (most used first)
  const sortedModels = useMemo(
    () => [...models].sort((a, b) => (usageCounts[b.id] ?? 0) - (usageCounts[a.id] ?? 0)),
    [models, usageCounts]
  )

  const handleTrackModelUsage = useCallback((id: number) => {
    setUsageCounts(incrementModelUsage(id))
  }, [])

  useEffect(() => {
    knowledgeService.list().then(setKbs).catch(console.error)
    modelsService.list({ model_type: 'chat', enabled_only: true }).then(setModels).catch(console.error)
  }, [])

  useEffect(() => {
    if (modelId == null && sortedModels.length > 0) {
      onModelChange(sortedModels[0].id)
    }
  }, [modelId, sortedModels, onModelChange])

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 200) + 'px'
    }
  }, [content])

  const handleSend = () => {
    const trimmed = content.trim()
    if (!trimmed) return
    onSend(trimmed)
    setContent('')
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (!isStreaming) handleSend()
    }
  }

  return (
    <div className="shrink-0 px-4 pb-4">
      <div className="max-w-3xl mx-auto flex flex-col pt-1 bg-white dark:bg-[#202020] border border-neutral-200 dark:border-white/10 rounded-xl focus-within:ring-2 focus-within:ring-blue-500/20 focus-within:border-blue-500/50 transition shadow-sm">
        
        {/* Knowledge Base Tag Row */}
        <div className="px-3 py-1 flex items-center gap-2 flex-wrap text-sm border-b border-transparent">
          {kbIds.length > 0 && (
            <span className="text-xs text-neutral-500 dark:text-neutral-400 select-none mr-0.5">{t('chat.knowledge_base')}:</span>
          )}
          
          <div className="flex items-center gap-2 flex-wrap">
            {kbIds.map(id => {
              const kb = kbs.find(k => k.id === id)
              if (!kb) return null
              return (
                <div key={id} className="flex items-center gap-1 px-2.5 py-0.5 bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-300 rounded border border-blue-200 dark:border-blue-500/20 text-xs shadow-sm">
                  <span className="truncate max-w-[120px]">{kb.name}</span>
                  <button
                    onClick={() => onKBChange(kbIds.filter(x => x !== id))}
                    className="text-blue-400 hover:text-blue-600 dark:hover:text-blue-200 rounded-full p-0.5"
                    title={t('common.delete')}
                  >
                    <X className="w-3 h-3" />
                  </button>
                </div>
              )
            })}
            
            <button
              onClick={() => setKbModalOpen(true)}
              className={`flex items-center gap-1 px-2.5 py-0.5 rounded text-xs transition ${
                kbIds.length === 0 
                  ? 'text-neutral-500 border border-dashed border-neutral-300 dark:border-neutral-600 hover:text-blue-600 hover:border-blue-400' 
                  : 'text-blue-600 dark:text-blue-400 hover:bg-neutral-100 dark:hover:bg-white/10'
              }`}
            >
              <Plus className="w-3 h-3" />
              {t('chat.bind_kb')}
            </button>

            {kbIds.length > 0 && (
               <button
                 onClick={() => onKBChange([])}
                 className="text-xs text-neutral-400 hover:text-red-500 transition-colors ml-1"
               >
                 {t('common.clear')}
               </button>
            )}
          </div>
        </div>

        <textarea
          ref={textareaRef}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={kbIds.length > 0 ? t('chat.input_placeholder_rag') : t('chat.input_placeholder')}
          disabled={disabled}
          rows={1}
          className="flex-1 w-full resize-none bg-transparent px-4 py-2.5 text-sm text-neutral-900 dark:text-neutral-100 placeholder:text-neutral-400 dark:placeholder:text-neutral-500 focus:outline-none disabled:opacity-50 max-h-[200px]"
        />

        {/* Bottom Toolbar: Model + Send */}
        <div className="flex items-center justify-between px-3 py-2 bg-neutral-50/50 dark:bg-black/10 border-t border-neutral-100 dark:border-white/5">
           <div className="flex items-center gap-3">
             <InlineModelSelector value={modelId} onChange={onModelChange} models={sortedModels} onBeforeChange={handleTrackModelUsage} />
           </div>

           <div className="flex items-center gap-2">
            {isStreaming ? (
              <button
                onClick={onAbort}
                className="flex items-center justify-center h-8 w-8 rounded-full bg-red-100 text-red-600 hover:bg-red-200 transition"
                title={t('chat.stop')}
              >
                <Square className="h-3.5 w-3.5 fill-current" />
              </button>
            ) : (
              <button
                onClick={handleSend}
                disabled={!content.trim() || disabled}
                className="flex items-center justify-center p-1.5 h-8 w-8 rounded-full bg-black dark:bg-white text-white dark:text-black hover:bg-neutral-800 dark:hover:bg-neutral-200 disabled:opacity-20 disabled:cursor-not-allowed transition"
                title={t('chat.send')}
              >
                <SendHorizontal className="h-4 w-4 ml-0.5" />
              </button>
            )}
           </div>
        </div>
      </div>

      <KBSelectionModal
        open={kbModalOpen}
        onOpenChange={setKbModalOpen}
        kbs={kbs}
        selectedIds={kbIds}
        onChange={onKBChange}
      />
    </div>
  )
}
