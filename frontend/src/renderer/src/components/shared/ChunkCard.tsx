import { useState } from 'react'
import { FileText, ChevronDown, ChevronUp } from 'lucide-react'
import { useI18n } from '../../i18n'

interface ChunkCardProps {
  filename: string
  chunkIndex: number
  score: number
  content: string
  highlighted?: boolean
  onClick?: () => void
}

export function ChunkCard({ filename, chunkIndex, score, content, highlighted, onClick, indexBadge }: ChunkCardProps & { indexBadge?: number }) {
  const { t } = useI18n()
  const [expanded, setExpanded] = useState(false)

  return (
    <div
      onClick={onClick}
      className={`relative w-full min-w-0 max-w-full rounded-lg border p-3 transition overflow-hidden ` + (onClick ? 'cursor-pointer ' : '') + 
        (highlighted
          ? 'border-blue-500/50 bg-blue-50 dark:bg-blue-500/10 ring-1 ring-blue-500/30'
          : 'border-neutral-200 dark:border-white/10 bg-white dark:bg-white/5 hover:border-neutral-300 dark:hover:border-white/20')}
    >
      <div className="flex items-start gap-2 mb-2 w-full">
        {indexBadge !== undefined && (
          <span className="inline-flex items-center justify-center min-w-[20px] h-[20px] px-1 rounded-full bg-blue-500 text-[11px] font-medium text-white shadow-sm shrink-0 mt-0.5">
            {indexBadge}
          </span>
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 text-xs text-neutral-500 dark:text-neutral-400">
            <FileText className="h-3.5 w-3.5 shrink-0" />
            <span className="truncate font-medium text-neutral-700 dark:text-neutral-300">{filename}</span>
            <span className="shrink-0">{t('common.paragraph', { index: chunkIndex })}</span>
            <span className="ml-auto text-blue-600 dark:text-blue-400 font-mono shrink-0">{score.toFixed(2)}</span>
          </div>
        </div>
      </div>
      <p className={`text-sm text-neutral-700 dark:text-neutral-300 whitespace-pre-wrap break-words overflow-hidden ${expanded ? '' : 'line-clamp-3'}`}>
        {content}
      </p>
      {content.length > 200 && (
        <button
          onClick={(e) => { e.stopPropagation(); setExpanded(!expanded) }}
          className="flex items-center gap-1 mt-1 text-xs text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300"
        >
          {expanded ? <><ChevronUp className="h-3 w-3" /> {t('common.collapse')}</> : <><ChevronDown className="h-3 w-3" /> {t('common.expand')}</>}
        </button>
      )}
    </div>
  )
}
