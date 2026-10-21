import { Plus, Search, RotateCw, Trash2, MoreVertical, BookOpen, Table2, Wand2, FileText, X, Check, AlertCircle } from 'lucide-react'
import { Button } from '../ui/Button'
import { StatusBadge } from './StatusBadge'
import { DropdownMenu } from '../ui/DropdownMenu'
import { Spinner } from '../ui/Spinner'
import { Modal } from '../ui/Modal'
import { ConfirmDialog } from '../ui/ConfirmDialog'
import { Textarea } from '../ui/Textarea'
import { CitationStyleSelect } from '../shared/CitationStyleSelect'
import { citationsService } from '../../services/citations'
import { documentsService } from '../../services/documents'
import { formatFileSize } from '../../utils/format'
import type { DocumentFileOut } from '../../types/knowledge'
import type { CitationParseProgress } from '../../services/documents'
import { useState, useEffect, useRef, useCallback } from 'react'
import { useI18n } from '../../i18n'

interface DocumentTableProps {
  kbId: number
  documents: DocumentFileOut[]
  loading: boolean
  onAdd: () => void
  onReindex: (docId: number) => void
  onDelete: (docId: number) => void
  onCancel: (docId: number) => void
  onSelect: (doc: DocumentFileOut) => void
  onEditCitation: (doc: DocumentFileOut) => void
  onBatchDelete: (docIds: number[]) => Promise<void>
  onBatchReindex: (docIds: number[]) => Promise<void>
  onParseFromText?: (docIds: number[], text: string) => Promise<void>
  onBatchParse?: (docIds: number[]) => Promise<void>
  onCitationChange?: () => void
  selectedDocId: number | null
  citationVersion?: number
}

// ---------------------------------------------------------------------------
// CitationCell
// ---------------------------------------------------------------------------
function CitationCell({
  kbId,
  doc,
  style,
  onEdit,
  version = 0,
  onCitationChange,
}: {
  kbId: number
  doc: DocumentFileOut
  style: string
  onEdit: (doc: DocumentFileOut) => void
  version?: number
  onCitationChange?: () => void
}) {
  const { t } = useI18n()
  const [text, setText] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (!doc.has_citation) { setText(null); return }
    let cancelled = false
    citationsService.getFormatted(kbId, doc.id, style).then((r) => {
      if (!cancelled) setText(r.text)
    }).catch(() => { if (!cancelled) setText(null) })
    return () => { cancelled = true }
  }, [kbId, doc.id, doc.has_citation, style, version])

  const startEdit = useCallback(() => {
    if (!doc.has_citation) { onEdit(doc); return }
    setDraft(text ?? '')
    setEditing(true)
    setTimeout(() => textareaRef.current?.focus(), 0)
  }, [doc, text, onEdit])

  const save = useCallback(async () => {
    setSaving(true)
    try {
      if (!draft.trim()) {
        // User cleared all text — delete the citation entirely
        await citationsService.remove(kbId, doc.id)
        setText(null)
      } else {
        await citationsService.patch(kbId, doc.id, { raw_citation: draft.trim() })
        setText(draft.trim())
      }
      onCitationChange?.()
    } catch { /* ignore */ }
    setSaving(false)
    setEditing(false)
  }, [kbId, doc.id, draft, onCitationChange])

  if (!doc.has_citation) {
    return (
      <span
        className="text-xs text-neutral-500 italic cursor-pointer hover:text-blue-400"
        onDoubleClick={() => onEdit(doc)}
      >
        {t('document_table.double_click_add_citation')}
      </span>
    )
  }

  if (editing) {
    return (
      <div className="flex items-start gap-1">
        <textarea
          ref={textareaRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); save() }
            if (e.key === 'Escape') setEditing(false)
          }}
          className="flex-1 text-xs bg-black/10 dark:bg-white/10 border border-blue-500/50 rounded p-1 resize-none h-14 focus:outline-none"
        />
        <div className="flex flex-col gap-1">
          <button onClick={save} disabled={saving} className="text-xs px-1.5 py-0.5 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50">
            {saving ? '...' : t('common.save')}
          </button>
          <button onClick={() => setEditing(false)} className="text-xs px-1.5 py-0.5 bg-black/10 dark:bg-white/10 rounded">{t('common.cancel')}</button>
        </div>
      </div>
    )
  }

  return (
    <span
      className="text-xs text-neutral-400 dark:text-neutral-300 cursor-pointer hover:text-neutral-600 dark:hover:text-neutral-100 line-clamp-2"
      title={t('document_table.double_click_edit_citation')}
      onDoubleClick={startEdit}
    >
      {text ?? t('common.loading')}
    </span>
  )
}

// ---------------------------------------------------------------------------
// DocumentTable
// ---------------------------------------------------------------------------
export function DocumentTable({
  kbId,
  documents,
  loading,
  onAdd,
  onReindex,
  onDelete,
  onCancel,
  onSelect,
  onEditCitation,
  onBatchDelete,
  onBatchReindex,
  onParseFromText,
  onBatchParse,
  onCitationChange,
  selectedDocId,
  citationVersion = 0,
}: DocumentTableProps) {
  const { t } = useI18n()
  const [search, setSearch] = useState('')
  const [citationMode, setCitationMode] = useState(false)
  const [citationStyle, setCitationStyle] = useState('apa')
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [batchLoading, setBatchLoading] = useState(false)

  const PROCESSING_STATUSES = new Set(['pending', 'parsing', 'chunking', 'cleaning', 'embedding', 'processing'])

  const [showPasteModal, setShowPasteModal] = useState(false)
  const [pasteText, setPasteText] = useState('')
  const [pasteLoading, setPasteLoading] = useState(false)
  const [showAIConfirm, setShowAIConfirm] = useState(false)

  // Streaming parse progress
  const [parseItems, setParseItems] = useState<CitationParseProgress[]>([])
  const [parseDone, setParseDone] = useState(false)
  const aiAbortRef = useRef<AbortController | null>(null)

  const filtered = search
    ? documents.filter((d) => d.original_filename.toLowerCase().includes(search.toLowerCase()))
    : documents

  useEffect(() => { setSelected(new Set()) }, [kbId])

  const allChecked = filtered.length > 0 && filtered.every((d) => selected.has(d.id))
  const someChecked = filtered.some((d) => selected.has(d.id))

  const toggleAll = () => {
    if (allChecked) setSelected(new Set())
    else setSelected(new Set(filtered.map((d) => d.id)))
  }

  const toggleOne = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const handleBatchDelete = async () => {
    setBatchLoading(true)
    try { await onBatchDelete([...selected]) } finally { setBatchLoading(false); setSelected(new Set()) }
  }

  const handleBatchReindex = async () => {
    setBatchLoading(true)
    try { await onBatchReindex([...selected]) } finally { setBatchLoading(false); setSelected(new Set()) }
  }

  const handlePasteConfirm = async () => {
    if (!onParseFromText || !pasteText.trim()) return
    setPasteLoading(true)
    try {
      await onParseFromText([...selected], pasteText.trim())
      setShowPasteModal(false)
      setPasteText('')
      setSelected(new Set())
    } catch {
      // Error already shown via toast from parent — keep modal open for retry
    } finally { setPasteLoading(false) }
  }

  const handleAIParseConfirm = async () => {
    // Build initial pending items from selected docs
    const ids = [...selected]
    const items: CitationParseProgress[] = ids.map((id) => {
      const doc = documents.find((d) => d.id === id)
      return { current: 0, total: ids.length, filename: doc?.original_filename ?? String(id), status: 'parsing' }
    })
    setParseItems(items)
    setParseDone(false)
    setShowAIConfirm(false)

    const ctrl = documentsService.streamAIParse(kbId, ids, (ev) => {
      if (ev.type === 'progress') {
        setParseItems((prev) =>
          prev.map((item) =>
            item.filename === ev.data.filename ? { ...item, ...ev.data } : item
          )
        )
      } else if (ev.type === 'done') {
        setParseDone(true)
        onBatchParse?.(ids)
      } else if (ev.type === 'error') {
        setParseDone(true)
      }
    })
    aiAbortRef.current = ctrl
  }

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Toolbar — contextual: batch mode when selected, normal otherwise */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-black/10 dark:border-white/10">
        {someChecked ? (
          <>
            <span className="text-xs text-neutral-500 dark:text-neutral-400">
              {t('document_table.selected_count', { count: selected.size })}
            </span>
            <button
              onClick={() => setSelected(new Set())}
              className="h-7 flex items-center gap-1 px-2 rounded-md text-xs border border-black/20 dark:border-white/20 text-gray-600 dark:text-neutral-300 hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
            >
              <X className="h-3.5 w-3.5" />
              {t('document_table.cancel_selection')}
            </button>
            <div className="flex-1" />
            <Button
              size="sm"
              variant="secondary"
              disabled={!onParseFromText || batchLoading}
              onClick={() => setShowPasteModal(true)}
              className="h-7 px-2.5 text-xs"
            >
              <FileText className="h-3.5 w-3.5 mr-1" />
              {t('document_table.parse_from_text')}
            </Button>
            <Button
              size="sm"
              variant="secondary"
              disabled={!onBatchParse || batchLoading}
              onClick={() => setShowAIConfirm(true)}
              className="h-7 px-2.5 text-xs"
            >
              <Wand2 className="h-3.5 w-3.5 mr-1" />
              {t('document_table.ai_parse_citation')}
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={handleBatchReindex}
              disabled={batchLoading}
              className="h-7 px-2.5 text-xs"
            >
              <RotateCw className="h-3.5 w-3.5 mr-1" />
              {t('knowledge.reindex')}
            </Button>
            <Button
              size="sm"
              variant="danger"
              onClick={handleBatchDelete}
              disabled={batchLoading}
              className="h-7 px-2.5 text-xs"
            >
              <Trash2 className="h-3.5 w-3.5 mr-1" />
              {t('common.delete')}
            </Button>
          </>
        ) : (
          <>
            <Button size="sm" onClick={onAdd} className="h-7 px-2.5 text-xs">
              <Plus className="h-3.5 w-3.5 mr-1" />
              {t('knowledge.add_doc')}
            </Button>
            {/* View mode toggle */}
            <button
              onClick={() => setCitationMode((v) => !v)}
              className={`h-7 flex items-center gap-1 px-2.5 rounded-md text-xs border transition-colors ${
                citationMode
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'border-black/20 dark:border-white/20 text-gray-600 dark:text-neutral-300 hover:bg-black/5 dark:hover:bg-white/5'
              }`}
            >
              {citationMode ? <Table2 className="h-3.5 w-3.5" /> : <BookOpen className="h-3.5 w-3.5" />}
              {citationMode ? t('document_table.normal_mode') : t('document_table.citation_mode')}
            </button>
            {citationMode && (
              <CitationStyleSelect
                value={citationStyle}
                onChange={setCitationStyle}
                className="h-7 py-0 px-2 text-xs"
              />
            )}
            <div className="flex-1" />
            {/* Search */}
            <div className="relative flex items-center h-7">
              <Search className="absolute left-2.5 h-3.5 w-3.5 text-neutral-500 pointer-events-none" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={t('document_table.search_doc_name')}
                className="h-7 pl-8 pr-3 bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/10 rounded-md text-xs text-gray-700 dark:text-neutral-200 placeholder-gray-400 dark:placeholder-neutral-500 focus:outline-none focus:border-blue-500/50 w-44"
              />
            </div>
          </>
        )}
      </div>

      {/* Parse citations from text modal */}
      <Modal
        open={showPasteModal}
        onOpenChange={(open) => { setShowPasteModal(open); if (!open) setPasteText('') }}
        title={t('document_table.parse_from_text_title')}
        description={t('document_table.parse_from_text_desc')}
      >
        <Textarea
          value={pasteText}
          onChange={(e) => setPasteText(e.target.value)}
          placeholder={t('document_table.parse_from_text_placeholder')}
          className="h-48 mt-2"
        />
        <div className="flex justify-end gap-2 mt-4">
          <Button variant="ghost" onClick={() => { setShowPasteModal(false); setPasteText('') }}>{t('common.cancel')}</Button>
          <Button
            loading={pasteLoading}
            disabled={!pasteText.trim()}
            onClick={handlePasteConfirm}
          >
            {t('document_table.start_matching')}
          </Button>
        </div>
      </Modal>

      {/* AI citation parse confirm dialog */}
      <ConfirmDialog
        open={showAIConfirm}
        onOpenChange={setShowAIConfirm}
        title={t('document_table.ai_parse_title')}
        description={t('document_table.ai_parse_confirm_desc')}
        confirmLabel={t('document_table.confirm_parse')}
        loading={false}
        onConfirm={handleAIParseConfirm}
      />

      {/* AI parsing progress modal */}
      <Modal
        open={parseItems.length > 0}
        onOpenChange={() => {
          if (parseDone) {
            setParseItems([])
            setParseDone(false)
            setSelected(new Set())
          }
        }}
        title={t('document_table.ai_parse_title')}
      >
        {(() => {
          const total = parseItems.length
          const done = parseItems.filter((i) => i.status === 'done' || i.status === 'error').length
          const pct = total > 0 ? Math.round((done / total) * 100) : 0
          return (
            <div className="space-y-3 mt-1">
              {/* Progress bar */}
              <div>
                <div className="flex justify-between text-xs text-neutral-500 dark:text-neutral-400 mb-1.5">
                  <span>{parseDone ? t('document_table.parse_done') : t('document_table.parsing')}</span>
                  <span>{done} / {total}</span>
                </div>
                <div className="h-1.5 bg-neutral-200 dark:bg-white/10 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-blue-500 rounded-full transition-all duration-300"
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </div>
              {/* File list */}
              <div className="max-h-60 overflow-y-auto space-y-1 pr-1">
                {parseItems.map((item) => (
                  <div key={item.filename} className="flex items-start gap-2 text-xs py-0.5">
                    <div className="flex-shrink-0 mt-0.5">
                      {item.status === 'parsing' && <Spinner className="h-3.5 w-3.5 text-blue-500" />}
                      {item.status === 'done' && <Check className="h-3.5 w-3.5 text-green-500" />}
                      {item.status === 'error' && <AlertCircle className="h-3.5 w-3.5 text-red-500" />}
                      {item.status !== 'parsing' && item.status !== 'done' && item.status !== 'error' && (
                        <div className="h-3.5 w-3.5 rounded-full border border-neutral-300 dark:border-white/20" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <span className={`truncate block ${item.status === 'parsing' ? 'text-blue-500 font-medium' : 'text-neutral-700 dark:text-neutral-300'}`}>
                        {item.filename}
                      </span>
                      {item.status === 'error' && item.message && (
                        <span className="text-red-500 text-xs">{item.message}</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
              {/* Show close action after completion */}
              {parseDone && (
                <div className="flex justify-end pt-1">
                  <Button
                    size="sm"
                    onClick={() => { setParseItems([]); setParseDone(false); setSelected(new Set()) }}
                  >
                    {t('common.done')}
                  </Button>
                </div>
              )}
            </div>
          )
        })()}
      </Modal>

      {loading ? (
        <div className="flex-1 flex items-center justify-center">
          <Spinner />
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-sm text-neutral-500">
          {search ? t('document_table.no_matching_docs') : t('document_table.no_docs_hint')}
        </div>
      ) : citationMode ? (
        <div className="flex-1 overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-gray-100 dark:bg-neutral-800/80">
              <tr className="text-left text-gray-600 dark:text-neutral-300 text-xs border-b border-black/10 dark:border-white/10">
                <th className="px-3 py-2 font-medium w-8">
                  <input
                    type="checkbox"
                    checked={allChecked}
                    ref={(el) => { if (el) el.indeterminate = someChecked && !allChecked }}
                    onChange={toggleAll}
                    className="cursor-pointer"
                  />
                </th>
                <th className="px-3 py-2 font-medium">{t('document_table.filename')}</th>
                <th className="px-3 py-2 font-medium">
                  {t('common.citation_style')} <span className="text-neutral-500 font-normal">{t('document_table.double_click_edit_hint')}</span>
                </th>
                <th className="px-3 py-2 font-medium w-10"></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((doc) => (
                <tr
                  key={doc.id}
                  className={`border-b border-black/5 dark:border-white/5 hover:bg-black/5 dark:hover:bg-white/5 transition-colors align-top${selected.has(doc.id) ? ' bg-blue-50 dark:bg-blue-900/20' : ''}`}
                >
                  <td className="px-3 py-3" onClick={(e) => e.stopPropagation()}>
                    <input type="checkbox" checked={selected.has(doc.id)} onChange={() => toggleOne(doc.id)} className="cursor-pointer" />
                  </td>
                  <td className="px-3 py-3 text-gray-900 dark:text-neutral-100 max-w-[160px]">
                    <div className="truncate text-xs">📄 {doc.original_filename}</div>
                    <StatusBadge status={doc.status} errorMessage={doc.error_message} />
                  </td>
                  <td className="px-3 py-3 min-w-[300px] max-w-[500px]">
                    <CitationCell kbId={kbId} doc={doc} style={citationStyle} onEdit={onEditCitation} version={citationVersion} onCitationChange={onCitationChange} />
                  </td>
                  <td className="px-3 py-2">
                    <DropdownMenu
                      trigger={
                        <button className="p-1 rounded hover:bg-black/10 dark:hover:bg-white/10" onClick={(e) => e.stopPropagation()}>
                          <MoreVertical className="h-4 w-4 text-gray-500 dark:text-neutral-400" />
                        </button>
                      }
                      items={[
                        { label: t('knowledge.edit_citation'), icon: <BookOpen className="h-4 w-4" />, onClick: () => onEditCitation(doc) },
                        { label: t('knowledge.reindex'), icon: <RotateCw className="h-4 w-4" />, onClick: () => onReindex(doc.id), disabled: PROCESSING_STATUSES.has(doc.status) },
                        ...(PROCESSING_STATUSES.has(doc.status) ? [{ label: t('common.cancel'), icon: <X className="h-4 w-4" />, onClick: () => onCancel(doc.id), danger: true as const }] : []),
                        { label: t('common.delete'), icon: <Trash2 className="h-4 w-4" />, onClick: () => onDelete(doc.id), danger: true },
                      ]}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-gray-100 dark:bg-neutral-800/80">
              <tr className="text-left text-gray-600 dark:text-neutral-300 text-xs border-b border-black/10 dark:border-white/10">
                <th className="px-3 py-2 font-medium w-8">
                  <input
                    type="checkbox"
                    checked={allChecked}
                    ref={(el) => { if (el) el.indeterminate = someChecked && !allChecked }}
                    onChange={toggleAll}
                    className="cursor-pointer"
                  />
                </th>
                <th className="px-4 py-2 font-medium">{t('document_table.filename')}</th>
                <th className="px-3 py-2 font-medium">{t('document_table.type')}</th>
                <th className="px-3 py-2 font-medium">{t('document_table.size')}</th>
                <th className="px-3 py-2 font-medium">{t('document_table.chunks')}</th>
                <th className="px-3 py-2 font-medium">{t('document_table.status')}</th>
                <th className="px-3 py-2 font-medium w-10"></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((doc) => (
                <tr
                  key={doc.id}
                  onClick={() => onSelect(doc)}
                  className={`border-b border-black/5 dark:border-white/5 cursor-pointer hover:bg-black/5 dark:hover:bg-white/5 transition-colors${selectedDocId === doc.id ? ' bg-blue-50 dark:bg-white/10' : ''}${selected.has(doc.id) ? ' bg-blue-50 dark:bg-blue-900/20' : ''}`}
                >
                  <td className="px-3 py-2" onClick={(e) => e.stopPropagation()}>
                    <input type="checkbox" checked={selected.has(doc.id)} onChange={() => toggleOne(doc.id)} className="cursor-pointer" />
                  </td>
                  <td className="px-4 py-2 text-gray-900 dark:text-neutral-100 truncate max-w-[200px]">
                    📄 {doc.original_filename}
                  </td>
                  <td className="px-3 py-2 text-gray-600 dark:text-neutral-400 uppercase">{doc.file_type}</td>
                  <td className="px-3 py-2 text-gray-600 dark:text-neutral-400">{formatFileSize(doc.file_size)}</td>
                  <td className="px-3 py-2 text-gray-600 dark:text-neutral-400">
                    {doc.status === 'indexed' ? doc.chunk_count : '--'}
                  </td>
                  <td className="px-3 py-2">
                    <StatusBadge status={doc.status} errorMessage={doc.error_message} />
                  </td>
                  <td className="px-3 py-2">
                    <DropdownMenu
                      trigger={
                        <button className="p-1 rounded hover:bg-black/10 dark:hover:bg-white/10" onClick={(e) => e.stopPropagation()}>
                          <MoreVertical className="h-4 w-4 text-gray-500 dark:text-neutral-400" />
                        </button>
                      }
                      items={[
                        { label: t('knowledge.reindex'), icon: <RotateCw className="h-4 w-4" />, onClick: () => onReindex(doc.id), disabled: PROCESSING_STATUSES.has(doc.status) },
                        ...(PROCESSING_STATUSES.has(doc.status) ? [{ label: t('common.cancel'), icon: <X className="h-4 w-4" />, onClick: () => onCancel(doc.id), danger: true as const }] : []),
                        { label: t('common.delete'), icon: <Trash2 className="h-4 w-4" />, onClick: () => onDelete(doc.id), danger: true },
                      ]}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
