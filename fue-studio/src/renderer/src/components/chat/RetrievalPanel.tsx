import { useState } from 'react'
import { PanelRightClose, PanelRightOpen, Copy, Check, FileText } from 'lucide-react'
import { IconButton } from '../ui/IconButton'
import { ScrollArea } from '../ui/ScrollArea'
import { Select } from '../ui/Select'
import { ChunkCard } from '../shared/ChunkCard'
import { useI18n } from '../../i18n'

interface RetrievalChunk {
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

interface RetrievalPanelProps {
  chunks: RetrievalChunk[]
  collapsed: boolean
  onToggle: () => void
  highlightedChunkKey?: string | null
  onChunkClick?: (chunkIndex: number) => void
}

function DocumentGroupCard({ filename, fileChunks, highlightedChunkKey, onChunkClick }: {
  filename: string
  fileChunks: RetrievalChunk[]
  highlightedChunkKey?: string | null
  onChunkClick?: (chunkIndex: number) => void
}) {
  const { t } = useI18n()
  const [copied, setCopied] = useState(false)
  const bestChunk = fileChunks[0]
  const citation = bestChunk.formatted_citation
  const displayTitle = citation && citation !== filename ? citation : filename

  const handleCopy = () => {
    navigator.clipboard.writeText(displayTitle).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div className="rounded-lg border border-neutral-200 dark:border-white/10 bg-white dark:bg-white/5 overflow-hidden">
      <div className="px-3 py-2 bg-neutral-50 dark:bg-white/5 border-b border-neutral-200 dark:border-white/10">
        <div className="flex items-start gap-2 min-w-0">
          <FileText className="h-4 w-4 text-blue-500 dark:text-blue-400 shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-neutral-800 dark:text-neutral-200 break-words line-clamp-2">{displayTitle}</p>
            {citation && citation !== filename && (
              <p className="text-[10px] text-neutral-500 dark:text-neutral-400 truncate mt-0.5">{filename}</p>
            )}
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <button
              onClick={handleCopy}
              className="p-1 rounded text-neutral-400 hover:text-neutral-700 dark:text-neutral-500 dark:hover:text-neutral-200 hover:bg-neutral-200 dark:hover:bg-white/10 transition"
              title={t('common.copy')}
            >
              {copied ? <Check className="h-3.5 w-3.5 text-green-500" /> : <Copy className="h-3.5 w-3.5" />}
            </button>
            <span className="flex items-center gap-0.5 text-[10px] text-neutral-500 px-1 py-0.5">
              {fileChunks.length}
            </span>
          </div>
        </div>
      </div>
      <div className="p-2 flex flex-col gap-2">
        {fileChunks.map((chunk, j) => (
          <ChunkCard
            key={`${chunk.document_id}-${chunk.chunk_index}-${j}`}
            filename={filename}
            chunkIndex={chunk.chunk_index}
            score={chunk.score}
            content={chunk.content?.trim() ?? ''}
            highlighted={highlightedChunkKey === chunk.chunk_key}
            onClick={() => onChunkClick?.(chunk.chunk_index)}
            indexBadge={chunk.citation_num}
          />
        ))}
      </div>
    </div>
  )
}

export function RetrievalPanel({ chunks, collapsed, onToggle, highlightedChunkKey, onChunkClick }: RetrievalPanelProps) {
  const { t } = useI18n()
  const [viewMode, setViewMode] = useState<'chunk' | 'document'>('chunk')

  if (collapsed) {
    return (
      <div className="h-full border-l border-neutral-200 dark:border-white/10 flex items-start justify-center pt-3 px-1">
        <IconButton tooltip={t('chat.expand_retrieval_panel')} onClick={onToggle}>
          <PanelRightOpen className="h-4 w-4" />
        </IconButton>
      </div>
    )
  }

  return (
    <div className="w-full h-full flex flex-col min-w-0 max-w-full bg-neutral-50/50 dark:bg-neutral-900/50 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-neutral-200 dark:border-white/10 shrink-0">
        <span className="text-sm font-semibold text-neutral-800 dark:text-neutral-200 shrink-0">{t('chat.retrieval_results')} ({chunks.length})</span>
        <div className="flex items-center gap-2 min-w-0">
          <Select
            value={viewMode}
            onValueChange={(v) => setViewMode(v as 'chunk' | 'document')}
            options={[
              { label: t('search.view_chunk'), value: 'chunk' },
              { label: t('search.view_document'), value: 'document' }
            ]}
            className="h-7 !py-0 !px-2 text-xs min-w-[70px] max-w-[100px] shrink-1"
          />
          <IconButton tooltip={t('chat.collapse_panel')} onClick={onToggle} size="sm">
            <PanelRightClose className="h-4 w-4" />
          </IconButton>
        </div>
      </div>
      <ScrollArea className="flex-1 min-h-0 overflow-x-hidden bg-neutral-50/50 dark:bg-black/20">
        <div className="p-3 pr-4 flex flex-col gap-2.5 min-w-0 max-w-full overflow-hidden">
          {chunks.length === 0 ? (
            <p className="text-xs text-neutral-500 text-center py-8">{t('chat.no_retrieval_results')}</p>
          ) : viewMode === 'chunk' ? (
            chunks.map((chunk, i) => (
              <ChunkCard
                key={`${chunk.document_id}-${chunk.chunk_index}-${i}`}
                filename={chunk.original_filename}
                chunkIndex={chunk.chunk_index}
                score={chunk.score}
                content={chunk.content?.trim() ?? ''}
                highlighted={highlightedChunkKey === chunk.chunk_key}
                onClick={() => onChunkClick?.(chunk.chunk_index)}
                indexBadge={chunk.citation_num}
              />
            ))
          ) : (
            // Document View — group by filename, show citation with copy
            Object.values(
              chunks.reduce<Record<number, { filename: string; chunks: RetrievalChunk[] }>>((acc, r) => {
                if (!acc[r.document_id]) {
                  acc[r.document_id] = { filename: r.original_filename, chunks: [] }
                }
                acc[r.document_id].chunks.push(r)
                return acc
              }, {})
            ).sort((a, b) => b.chunks[0].score - a.chunks[0].score).map((group, i) => (
              <DocumentGroupCard
                key={`${group.filename}-${i}`}
                filename={group.filename}
                fileChunks={group.chunks}
                highlightedChunkKey={highlightedChunkKey}
                onChunkClick={onChunkClick}
              />
            ))
          )}
        </div>
      </ScrollArea>
    </div>
  )
}
