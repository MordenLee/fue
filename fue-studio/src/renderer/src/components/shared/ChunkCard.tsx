import { useMemo, useState } from 'react'
import { FileText, ChevronDown, ChevronUp } from 'lucide-react'
import { useI18n } from '../../i18n'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'

interface ChunkCardProps {
  filename: string
  chunkIndex: number
  score: number
  content: string
  highlighted?: boolean
  onClick?: () => void
  blockNumber?: number
  citationTitle?: string | null
  citationAuthors?: string[] | null
  citationYear?: number | null
}

export function ChunkCard({ filename, chunkIndex, score, content, highlighted, onClick, indexBadge, blockNumber, citationTitle, citationAuthors, citationYear }: ChunkCardProps & { indexBadge?: number }) {
  const { t } = useI18n()
  const [expanded, setExpanded] = useState(false)
  const processedContent = useMemo(() => {
    return content
      .replace(/\\\[([\s\S]*?)\\\]/g, (_, expr) => `$$${String(expr).trim()}$$`)
      .replace(/\\\(([^\n]*?)\\\)/g, (_, expr) => `$${String(expr).trim()}$`)
  }, [content])

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
          <div className="flex items-center gap-1.5 text-xs text-neutral-500 dark:text-neutral-400 mb-1">
            {blockNumber !== undefined && (
              <span className="inline-flex items-center justify-center min-w-[22px] h-[22px] px-1.5 rounded bg-blue-500/20 text-blue-600 dark:text-blue-400 font-mono font-medium shrink-0">
                [{blockNumber}]
              </span>
            )}
            {(citationTitle || citationAuthors || citationYear) && (
              <span className="text-xs text-neutral-600 dark:text-neutral-400 truncate">
                {citationAuthors && citationAuthors.length > 0 ? citationAuthors[0] : '文献'} 
                {citationYear && `(${citationYear})`}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1.5 text-xs text-neutral-500 dark:text-neutral-400">
            <FileText className="h-3.5 w-3.5 shrink-0" />
            <span className="truncate font-medium text-neutral-700 dark:text-neutral-300">{filename}</span>
            <span className="shrink-0">{t('common.paragraph', { index: chunkIndex })}</span>
            <span className="ml-auto text-blue-600 dark:text-blue-400 font-mono shrink-0">{score.toFixed(2)}</span>
          </div>
        </div>
      </div>
      <div className={`overflow-hidden ${expanded ? '' : 'max-h-[4.5rem]'}`}>
        <div className="prose prose-sm max-w-none text-neutral-700 dark:text-neutral-300 dark:prose-invert prose-p:my-0 prose-p:leading-6 prose-headings:my-1 prose-ul:my-1 prose-ol:my-1 prose-li:my-0 prose-pre:my-1 prose-pre:bg-neutral-900 prose-pre:text-neutral-100 prose-code:before:hidden prose-code:after:hidden prose-code:bg-neutral-100 dark:prose-code:bg-white/10 prose-code:px-1 prose-code:py-0.5 prose-code:rounded break-words">
          <ReactMarkdown
          remarkPlugins={[remarkMath, remarkGfm]}
          rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: 'ignore' }]]}
          components={{
            a({ href, children }) {
              return <a href={href} target="_blank" rel="noreferrer">{children}</a>
            }
          }}
        >
          {processedContent}
          </ReactMarkdown>
        </div>
      </div>
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
