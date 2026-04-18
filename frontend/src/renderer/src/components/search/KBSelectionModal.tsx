import { useState, useMemo, useEffect } from 'react'
import { Modal } from '../ui/Modal'
import { Search, Check } from 'lucide-react'
import { Button } from '../ui/Button'
import { useI18n } from '../../i18n'
import type { KnowledgeBaseOut } from '../../types/knowledge'

interface KBSelectionModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  kbs: KnowledgeBaseOut[]
  selectedIds: number[]
  onChange: (ids: number[]) => void
}

export function KBSelectionModal({ open, onOpenChange, kbs, selectedIds, onChange }: KBSelectionModalProps) {
  const { t } = useI18n()
  const [query, setQuery] = useState('')
  const [tempSelected, setTempSelected] = useState<number[]>(selectedIds)

  useEffect(() => {
    if (open) {
      setTempSelected(selectedIds)
      setQuery('')
    }
  }, [open, selectedIds])

  const filtered = useMemo(() => {
    if (!query.trim()) return kbs
    return kbs.filter(kb => kb.name.toLowerCase().includes(query.toLowerCase()))
  }, [kbs, query])

  const toggleKb = (id: number) => {
    setTempSelected(prev => 
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    )
  }

  const toggleAll = () => {
    if (tempSelected.length === kbs.length) {
      setTempSelected([])
    } else {
      setTempSelected(kbs.map(kb => kb.id))
    }
  }

  const handleConfirm = () => {
    onChange(tempSelected)
    onOpenChange(false)
  }

  return (
    <Modal open={open} onOpenChange={onOpenChange} title={t('search.select_kb')} className="max-w-xl">
      <div className="flex flex-col gap-4">
        {/* Search Input */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-neutral-500" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('search.search_kb_placeholder')}
            className="w-full pl-9 pr-3 py-2 bg-neutral-100 dark:bg-white/5 border border-neutral-200 dark:border-white/10 rounded-lg text-sm focus:outline-none focus:border-blue-500/50 transition-colors"
          />
        </div>

        {/* Header / Select All */}
        <div className="flex items-center justify-between text-sm">
          <span className="text-neutral-500">{t('search.selected_count')?.replace('{count}', String(tempSelected.length))}</span>
          <button onClick={toggleAll} className="text-blue-500 hover:text-blue-400">
            {tempSelected.length === kbs.length ? t('common.deselect_all') : t('common.select_all')}
          </button>
        </div>

        {/* List */}
        <div className="max-h-[55vh] overflow-y-auto pr-1 custom-scrollbar">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pb-2">
            {filtered.length === 0 ? (
              <div className="col-span-full text-center py-10 text-neutral-500 text-sm">
                <div className="text-4xl mb-2 opacity-50">📂</div>
                {t('search.no_kbs_found')}
              </div>
            ) : (
              filtered.map(kb => {
                const selected = tempSelected.includes(kb.id)
                return (
                  <div
                    key={kb.id}
                    onClick={() => toggleKb(kb.id)}
                    className={`group relative flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-all duration-200 ${
                      selected 
                        ? 'border-blue-500/60 bg-blue-50/50 dark:bg-blue-500/10 shadow-sm ring-1 ring-blue-500/20' 
                        : 'border-neutral-200 dark:border-white/10 bg-white dark:bg-white/5 hover:border-blue-300/50 dark:hover:border-white/20 hover:shadow-md'
                    }`}
                  >
                    <div className={`mt-0.5 flex shrink-0 items-center justify-center w-5 h-5 rounded-md border transition-all ${
                      selected 
                        ? 'bg-blue-500 border-blue-500 text-white shadow-inner' 
                        : 'border-neutral-300 dark:border-neutral-600 bg-black/5 dark:bg-black/20 group-hover:border-blue-400'
                    }`}>
                      {selected && <Check className="h-3.5 w-3.5" strokeWidth={3} />}
                    </div>
                    <div className="flex flex-col min-w-0 pr-2">
                      <span className="text-neutral-900 dark:text-neutral-100 font-medium text-sm leading-snug truncate transition-colors group-hover:text-blue-600 dark:group-hover:text-blue-400">
                        {kb.name}
                      </span>
                      <span className="text-neutral-500 text-[11px] leading-tight mt-1 truncate flex items-center gap-1.5 opacity-80">
                        <span className="inline-block w-1.5 h-1.5 rounded-full bg-neutral-300 dark:bg-neutral-600"></span>
                        {kb.document_count} {t('knowledge.document_count')}
                      </span>
                      {kb.description && (
                        <p className="text-neutral-400 dark:text-neutral-500 text-xs mt-1 truncate">
                          {kb.description}
                        </p>
                      )}
                    </div>
                  </div>
                )
              })
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 mt-2 pt-4 border-t border-neutral-200 dark:border-white/10">
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
          <Button onClick={handleConfirm}>
            {t('common.confirm')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
