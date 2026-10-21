import { useState } from 'react'
import { FileText, BookOpen, ChevronDown, ChevronUp } from 'lucide-react'
import type { ReferenceItem } from '../../types/conversation'
import { useI18n } from '../../i18n'
import { useSettings } from '../../contexts/SettingsContext'

interface CitationRendererProps {
  references: ReferenceItem[]
  onCiteClick?: (refNum: number) => void
}

type ViewMode = 'file' | 'citation'

export function CitationRenderer({ references, onCiteClick }: CitationRendererProps) {
  const { t } = useI18n()
  const { settings } = useSettings()
  const [expanded, setExpanded] = useState(false)
  const [viewMode, setViewMode] = useState<ViewMode>('citation')
  const citationMode = settings?.chat_citation_mode ?? 'document'

  if (!references || references.length === 0) return null

  // De-duplicate references by ref_num (keep first occurrence)
  const uniqueRefs = references
    .filter((ref, idx, arr) => arr.findIndex(r => r.ref_num === ref.ref_num) === idx)
    .sort((a, b) => a.ref_num - b.ref_num)

  // Group by file for file view
  const groupedByFile = uniqueRefs.reduce<Record<string, ReferenceItem[]>>((acc, ref) => {
    const key = ref.original_filename
    if (!acc[key]) acc[key] = []
    acc[key].push(ref)
    return acc
  }, {})

  for (const refs of Object.values(groupedByFile)) {
    refs.sort((a, b) => a.ref_num - b.ref_num)
  }

  const groupedByDocument = uniqueRefs.reduce<
    Record<number, { documentId: number; filename: string; citation: string; refNums: number[] }>
  >((acc, ref) => {
    const docId = ref.document_file_id
    if (!acc[docId]) {
      acc[docId] = {
        documentId: docId,
        filename: ref.original_filename,
        citation: ref.formatted_citation || ref.original_filename,
        refNums: []
      }
    }
    acc[docId].refNums.push(ref.ref_num)
    return acc
  }, {})

  const documentRefs = Object.values(groupedByDocument)
    .map((g) => ({ ...g, refNums: [...new Set(g.refNums)].sort((a, b) => a - b) }))
    .sort((a, b) => a.refNums[0] - b.refNums[0])

  const previewRefs = uniqueRefs.slice(0, 3)
  const previewDocRefs = documentRefs.slice(0, 3)
  // After remapping:
  //   document mode: one display_num per doc → flat uniqueRefs; show-more based on uniqueRefs
  //   chunk mode: one display_num per chunk, grouped by doc → show-more based on documentRefs
  const hasMore = citationMode === 'chunk' ? documentRefs.length > 3 : uniqueRefs.length > 3

  return (
    <div className="mt-3 pt-2 border-t border-neutral-200/50 dark:border-white/5">
      {/* Header row with toggle */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-neutral-500 dark:text-neutral-400">{t('chat.references')} ({uniqueRefs.length})</span>
          <div className="flex items-center bg-neutral-100 dark:bg-white/5 rounded p-0.5 gap-0.5">
            <button
              onClick={() => setViewMode('citation')}
              className={`flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] transition ${
                viewMode === 'citation' ? 'bg-white dark:bg-white/10 text-blue-600 dark:text-blue-400 shadow-sm' : 'text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300'
              }`}
            >
              <BookOpen className="w-2.5 h-2.5" />
              {t('chat.citation_view')}
            </button>
            <button
              onClick={() => setViewMode('file')}
              className={`flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] transition ${
                viewMode === 'file' ? 'bg-white dark:bg-white/10 text-blue-600 dark:text-blue-400 shadow-sm' : 'text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300'
              }`}
            >
              <FileText className="w-2.5 h-2.5" />
              {t('chat.file_view')}
            </button>
          </div>
        </div>
        {hasMore && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-0.5 text-[10px] text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 transition"
          >
            {expanded ? <><ChevronUp className="w-3 h-3" />{t('common.collapse')}</> : <><ChevronDown className="w-3 h-3" />{t('chat.show_all_refs')}</>}
          </button>
        )}
      </div>

      {/* Citation view */}
      {viewMode === 'citation' && (
        <div className="space-y-1.5 flex flex-col items-start w-full">
          {citationMode === 'chunk'
            ? (expanded ? documentRefs : previewDocRefs).map((doc) => (
                <div key={doc.documentId} className="flex items-start gap-2 w-full text-xs">
                  <div className="shrink-0 flex items-center gap-1 mt-0.5">
                    {doc.refNums.map((n) => (
                      <button
                        key={n}
                        onClick={() => onCiteClick?.(n)}
                        className="inline-flex items-center justify-center min-w-[16px] h-[16px] px-[4px] rounded-full bg-blue-100 dark:bg-blue-500/20 text-[10px] font-bold text-blue-600 dark:text-blue-400 hover:bg-blue-200 dark:hover:bg-blue-500/30 transition cursor-pointer"
                      >
                        {n}
                      </button>
                    ))}
                  </div>
                  <div className="flex-1 text-neutral-600 dark:text-neutral-400 break-words leading-relaxed select-text mt-[1px]">
                    {doc.citation}
                  </div>
                </div>
              ))
            : (expanded ? uniqueRefs : previewRefs).map((ref) => (
                <div key={ref.ref_num} className="flex items-start gap-2 w-full text-xs">
                  <button
                    onClick={() => onCiteClick?.(ref.ref_num)}
                    className="shrink-0 inline-flex items-center justify-center min-w-[16px] h-[16px] px-[4px] rounded-full bg-blue-100 dark:bg-blue-500/20 text-[10px] font-bold text-blue-600 dark:text-blue-400 hover:bg-blue-200 dark:hover:bg-blue-500/30 transition cursor-pointer mt-0.5"
                  >
                    {ref.ref_num}
                  </button>
                  <div className="flex-1 text-neutral-600 dark:text-neutral-400 break-words leading-relaxed select-text mt-[1px]">
                    {ref.formatted_citation || ref.original_filename}
                  </div>
                </div>
              ))}
        </div>
      )}

      {/* File view */}
      {viewMode === 'file' && (
        <div className="space-y-1.5">
          {Object.entries(groupedByFile).map(([filename, refs]) => (
            <div key={filename} className="flex items-center gap-2 px-2 py-1.5 rounded-md border border-neutral-200 dark:border-white/10 bg-white/50 dark:bg-white/5">
              <FileText className="w-3.5 h-3.5 text-blue-500 shrink-0" />
              <span className="text-xs font-medium text-neutral-700 dark:text-neutral-300 truncate flex-1">{filename}</span>
              <div className="flex gap-1 shrink-0">
                {refs.map(r => (
                  <button
                    key={r.ref_num}
                    onClick={() => onCiteClick?.(r.ref_num)}
                    className="inline-flex items-center justify-center w-5 h-5 rounded bg-blue-100 dark:bg-blue-500/20 text-[10px] font-bold text-blue-600 dark:text-blue-400 hover:bg-blue-200 dark:hover:bg-blue-500/30 transition cursor-pointer"
                  >
                    {r.ref_num}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
