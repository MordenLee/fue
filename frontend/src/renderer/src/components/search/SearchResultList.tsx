import { useState, useEffect } from 'react'
import { ChunkCard } from '../shared/ChunkCard'
import { Spinner } from '../ui/Spinner'
import { EmptyState } from '../ui/EmptyState'
import { Select } from '../ui/Select'
import { SearchX, FileText, ChevronDown, ChevronUp, LayoutList, BookOpen, Copy, Check } from 'lucide-react'
import type { SearchResult, CitationOut } from '../../types/knowledge'
import { citationsService } from '../../services/citations'
import { useI18n } from '../../i18n'

interface SearchResultListProps {
  results: SearchResult[]
  isSearching: boolean
  error: string | null
  hasSearched: boolean
}

type ViewMode = 'chunk' | 'document'
type CitationFormat = 'apa' | 'gbt7714' | 'mla' | 'chicago' | 'bibtex'

// ---------------------------------------------------------------------------
// Citation formatters
// ---------------------------------------------------------------------------

function formatAuthorsAPA(authors: string[]): string {
  if (authors.length === 0) return ''
  if (authors.length === 1) return authors[0]
  if (authors.length === 2) return `${authors[0]} & ${authors[1]}`
  if (authors.length <= 20) return authors.slice(0, -1).join(', ') + ', & ' + authors[authors.length - 1]
  return authors.slice(0, 19).join(', ') + ', ... ' + authors[authors.length - 1]
}

function formatAPA(c: CitationOut): string {
  const parts: string[] = []
  if (c.authors?.length) parts.push(formatAuthorsAPA(c.authors))
  if (c.year) parts.push(`(${c.year})`)
  if (c.title) parts.push(c.title)
  const meta: string[] = []
  if (c.source) meta.push(`*${c.source}*`)
  if (c.volume) meta.push(`*${c.volume}*`)
  if (c.issue) meta.push(`(${c.issue})`)
  if (c.pages) meta.push(c.pages)
  if (meta.length) parts.push(meta.join(', '))
  if (c.doi) parts.push(`https://doi.org/${c.doi}`)
  return parts.join('. ').replace(/\.\./g, '.') + '.'
}

function formatGBT7714(c: CitationOut): string {
  const parts: string[] = []
  if (c.authors?.length) {
    parts.push(c.authors.length > 3 ? c.authors.slice(0, 3).join(', ') + ', 等' : c.authors.join(', '))
  }
  if (c.title) parts.push(c.title)
  const tag = c.citation_type === 'article' ? '[J]' : c.citation_type === 'book' ? '[M]' : c.citation_type === 'conference' ? '[C]' : c.citation_type === 'thesis' ? '[D]' : c.citation_type === 'website' ? '[EB/OL]' : '[Z]'
  parts.push(tag)
  const meta: string[] = []
  if (c.source) meta.push(c.source)
  if (c.year) meta.push(String(c.year))
  if (c.volume) meta.push(`${c.volume}`)
  if (c.issue) meta.push(`(${c.issue})`)
  if (c.pages) meta.push(`: ${c.pages}`)
  if (meta.length) parts.push(meta.join(', '))
  if (c.doi) parts.push(`DOI: ${c.doi}`)
  return parts.join('. ').replace(/\.\./g, '.') + '.'
}

function formatMLA(c: CitationOut): string {
  const parts: string[] = []
  if (c.authors?.length) {
    if (c.authors.length === 1) parts.push(c.authors[0])
    else if (c.authors.length === 2) parts.push(`${c.authors[0]}, and ${c.authors[1]}`)
    else parts.push(`${c.authors[0]}, et al.`)
  }
  if (c.title) parts.push(`"${c.title}"`)
  const meta: string[] = []
  if (c.source) meta.push(`*${c.source}*`)
  if (c.volume) meta.push(`vol. ${c.volume}`)
  if (c.issue) meta.push(`no. ${c.issue}`)
  if (c.year) meta.push(String(c.year))
  if (c.pages) meta.push(`pp. ${c.pages}`)
  if (meta.length) parts.push(meta.join(', '))
  if (c.doi) parts.push(`doi:${c.doi}`)
  return parts.join('. ').replace(/\.\./g, '.') + '.'
}

function formatChicago(c: CitationOut): string {
  const parts: string[] = []
  if (c.authors?.length) parts.push(c.authors.join(', '))
  if (c.title) parts.push(`"${c.title}"`)
  if (c.source) parts.push(`*${c.source}*`)
  const meta: string[] = []
  if (c.volume) meta.push(c.volume)
  if (c.issue) meta.push(`no. ${c.issue}`)
  if (meta.length) parts.push(meta.join(', '))
  if (c.year) parts.push(`(${c.year})`)
  if (c.pages) parts.push(c.pages)
  if (c.doi) parts.push(`https://doi.org/${c.doi}`)
  return parts.join('. ').replace(/\.\./g, '.') + '.'
}

function formatBibTeX(c: CitationOut): string {
  const type = c.citation_type === 'article' ? 'article' : c.citation_type === 'book' ? 'book' : c.citation_type === 'conference' ? 'inproceedings' : c.citation_type === 'thesis' ? 'phdthesis' : 'misc'
  const key = (c.authors?.[0]?.split(/\s+/).pop() ?? 'unknown') + (c.year ?? '')
  const lines: string[] = [`@${type}{${key},`]
  if (c.title) lines.push(`  title     = {${c.title}},`)
  if (c.authors?.length) lines.push(`  author    = {${c.authors.join(' and ')}},`)
  if (c.source) lines.push(`  journal   = {${c.source}},`)
  if (c.year) lines.push(`  year      = {${c.year}},`)
  if (c.volume) lines.push(`  volume    = {${c.volume}},`)
  if (c.issue) lines.push(`  number    = {${c.issue}},`)
  if (c.pages) lines.push(`  pages     = {${c.pages}},`)
  if (c.publisher) lines.push(`  publisher = {${c.publisher}},`)
  if (c.doi) lines.push(`  doi       = {${c.doi}},`)
  lines.push('}')
  return lines.join('\n')
}

const CITATION_FORMATTERS: Record<CitationFormat, (c: CitationOut) => string> = {
  apa: formatAPA,
  gbt7714: formatGBT7714,
  mla: formatMLA,
  chicago: formatChicago,
  bibtex: formatBibTeX,
}

function formatCitationByStyle(c: CitationOut, style: CitationFormat): string {
  return CITATION_FORMATTERS[style](c)
}

/** Legacy default format (used for display title subtitle) */
function formatCitation(c: CitationOut): string {
  return formatGBT7714(c)
}

function ExpandableText({ content, clampClass = 'line-clamp-4' }: { content: string; clampClass?: string }) {
  const { t } = useI18n()
  const [textExpanded, setTextExpanded] = useState(false)

  return (
    <>
      <p className={`text-sm text-neutral-800 dark:text-neutral-300 break-words overflow-hidden ${textExpanded ? '' : clampClass}`}>{content}</p>
      {content.length > 150 && (
        <button
          onClick={(e) => { e.stopPropagation(); setTextExpanded(!textExpanded) }}
          className="flex items-center gap-1 mt-1 text-xs text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300"
        >
          {textExpanded
            ? <><ChevronUp className="h-3 w-3" />{t('common.collapse')}</>
            : <><ChevronDown className="h-3 w-3" />{t('common.expand')}</>
          }
        </button>
      )}
    </>
  )
}

function DocumentGroupCard({ filename, chunks, citationFormat }: { filename: string; chunks: SearchResult[]; citationFormat: CitationFormat }) {
  const { t } = useI18n()
  const [chunksExpanded, setChunksExpanded] = useState(false)
  const [citation, setCitation] = useState<CitationOut | null>(null)
  const [copied, setCopied] = useState(false)
  const bestChunk = chunks[0]
  const extraCount = chunks.length - 1

  useEffect(() => {
    const kbId = bestChunk.kb_id
    const docId = bestChunk.document_id
    if (kbId == null) return
    citationsService.get(kbId, docId).then(setCitation).catch(() => setCitation(null))
  }, [bestChunk.kb_id, bestChunk.document_id])

  const displayTitle = citation?.title ?? filename
  const citationText = citation ? formatCitationByStyle(citation, citationFormat) : filename

  const handleCopy = () => {
    navigator.clipboard.writeText(citationText).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div className="rounded-lg border border-neutral-200 dark:border-white/10 bg-white dark:bg-white/5 shadow-[0_1px_2px_rgba(0,0,0,0.05)] dark:shadow-none overflow-hidden">
      <div className="px-3 py-2.5 bg-neutral-50 dark:bg-white/5 border-b border-neutral-200 dark:border-white/10 rounded-t-lg">
        <div className="flex items-center gap-2 min-w-0">
          <FileText className="h-4 w-4 text-blue-500 dark:text-blue-400 shrink-0" />
          <div className="flex-1 min-w-0 flex items-center gap-2 overflow-hidden">
            <span className="font-medium text-neutral-900 dark:text-neutral-200 text-sm shrink-0 max-w-[40%] truncate">{displayTitle}</span>
            <span className="text-xs text-neutral-500 truncate min-w-0">
              {citation ? formatCitation(citation) : filename}
            </span>
          </div>
          <div className="flex items-center gap-1 shrink-0 ml-1">
            <span className="text-xs font-mono text-blue-600 dark:text-blue-400">{bestChunk.score.toFixed(2)}</span>
            <button
              onClick={handleCopy}
              className="p-1 rounded text-neutral-400 hover:text-neutral-700 dark:text-neutral-500 dark:hover:text-neutral-200 hover:bg-neutral-200 dark:hover:bg-white/10 transition"
              title={t('search.copy_citation')}
            >
              {copied ? <Check className="h-3.5 w-3.5 text-green-500 dark:text-green-400" /> : <Copy className="h-3.5 w-3.5" />}
            </button>
            {extraCount > 0 && (
              <button
                onClick={() => setChunksExpanded(!chunksExpanded)}
                className="flex items-center gap-1 text-xs text-neutral-500 dark:text-neutral-400 hover:text-neutral-800 dark:hover:text-neutral-200 px-1.5 py-0.5 rounded hover:bg-neutral-200 dark:hover:bg-white/10 transition"
              >
                {chunksExpanded
                  ? <><ChevronUp className="h-3.5 w-3.5" />{t('common.collapse')}</>
                  : <><ChevronDown className="h-3.5 w-3.5" />{t('search.doc_chunks_count')?.replace('{count}', String(chunks.length))}</>
                }
              </button>
            )}
          </div>
        </div>
      </div>
      <div className="p-3 space-y-2">
        <ExpandableText content={bestChunk.content} clampClass="line-clamp-4" />
        {chunksExpanded && extraCount > 0 && (
          <div className="mt-2 space-y-2 border-t border-neutral-200 dark:border-white/10 pt-2">
            {chunks.slice(1).map((c, i) => (
              <div key={i} className="border border-neutral-200 dark:border-white/5 bg-neutral-50 dark:bg-transparent rounded-md p-2">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-neutral-500">{t('common.paragraph', { index: c.chunk_index })}</span>
                  <span className="text-xs font-mono text-blue-600 dark:text-blue-400">{c.score.toFixed(2)}</span>
                </div>
                <ExpandableText content={c.content} clampClass="line-clamp-3" />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export function SearchResultList({ results, isSearching, error, hasSearched }: SearchResultListProps) {
  const { t } = useI18n()
  const [viewMode, setViewMode] = useState<ViewMode>('chunk')
  const [citationFormat, setCitationFormat] = useState<CitationFormat>('gbt7714')

  if (isSearching) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Spinner size="lg" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-red-400 text-sm">{error}</p>
      </div>
    )
  }

  if (hasSearched && results.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <EmptyState
          icon={<SearchX className="h-10 w-10" />}
          title={t('search.no_results_title')}
          description={t('search.no_results_desc')}
        />
      </div>
    )
  }

  if (!hasSearched) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-neutral-500 text-sm">{t('search.start_hint')}</p>
      </div>
    )
  }

  // Group results by filename for document view
  const groupedByFile = results.reduce<Record<string, SearchResult[]>>((acc, r) => {
    if (!acc[r.original_filename]) acc[r.original_filename] = []
    acc[r.original_filename].push(r)
    return acc
  }, {})
  const documentGroups = Object.entries(groupedByFile).sort(
    (a, b) => b[1][0].score - a[1][0].score
  )

  return (
    <div className="flex-1 overflow-y-auto overflow-x-hidden p-4">
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs text-neutral-500">{t('search.result_count', { count: results.length })}</p>
        <div className="flex items-center gap-2">
          {viewMode === 'document' && (
            <Select
              value={citationFormat}
              onValueChange={(v) => setCitationFormat(v as CitationFormat)}
              options={[
                { label: 'GB/T 7714', value: 'gbt7714' },
                { label: 'APA', value: 'apa' },
                { label: 'MLA', value: 'mla' },
                { label: 'Chicago', value: 'chicago' },
                { label: 'BibTeX', value: 'bibtex' },
              ]}
              className="h-7 !py-0 !px-2 text-xs min-w-[110px]"
            />
          )}
          <div className="flex items-center gap-1 bg-neutral-100 dark:bg-white/5 rounded-lg p-0.5 border border-neutral-200 dark:border-white/10">
            <button
              onClick={() => setViewMode('chunk')}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs transition-colors ${
                viewMode === 'chunk'
                  ? 'bg-white dark:bg-blue-600 text-blue-600 dark:text-white shadow-sm dark:shadow-none'
                  : 'text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200'
              }`}
            >
              <LayoutList className="w-3.5 h-3.5" />
              {t('search.view_chunk')}
            </button>
            <button
              onClick={() => setViewMode('document')}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs transition-colors ${
                viewMode === 'document'
                  ? 'bg-white dark:bg-blue-600 text-blue-600 dark:text-white shadow-sm dark:shadow-none'
                  : 'text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200'
              }`}
            >
              <BookOpen className="w-3.5 h-3.5" />
              {t('search.view_document')}
            </button>
          </div>
        </div>
      </div>

      {viewMode === 'chunk' ? (
        <div className="space-y-3">
          {results.map((r, i) => (
            <ChunkCard
              key={i}
              filename={r.original_filename}
              chunkIndex={r.chunk_index ?? i + 1}
              score={r.score}
              content={r.content}
            />
          ))}
        </div>
      ) : (
        <div className="space-y-3">
          {documentGroups.map(([filename, chunks]) => (
            <DocumentGroupCard key={filename} filename={filename} chunks={chunks} citationFormat={citationFormat} />
          ))}
        </div>
      )}
    </div>
  )
}
