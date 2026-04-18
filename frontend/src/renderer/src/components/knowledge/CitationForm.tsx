import { useState, useEffect } from 'react'
import { FormModal } from '../ui/FormModal'
import { FormField } from '../ui/FormField'
import { Input } from '../ui/Input'
import { Select } from '../ui/Select'
import type { CitationCreate, CitationOut } from '../../types/knowledge'
import { useI18n } from '../../i18n'

const citationTypeValues: CitationCreate['citation_type'][] = ['article', 'book', 'chapter', 'thesis', 'conference', 'website', 'other']

// ---------------------------------------------------------------------------
// Simple citation parser — handles APA, GB/T 7714, MLA, and plain text
// ---------------------------------------------------------------------------
function parseCitationText(raw: string): Partial<CitationCreate> {
  const result: Partial<CitationCreate> = {}
  const s = raw.trim()

  // DOI
  const doiMatch = s.match(/\b(10\.\d{4,}\/[^\s,;]+)/)
  if (doiMatch) result.doi = doiMatch[1].replace(/\.?\s*$/, '')

  // Year — prefer (YYYY) APA style, then ,YYYY, or plain YYYY near end
  const yearParen = s.match(/\((\d{4})\)/)
  const yearComma = s.match(/[,，]\s*(\d{4})\s*[,，()\[\]:\s]/)
  const yearEnd = s.match(/[,，。.]\s*(\d{4})\s*[.。]?\s*$/)
  const yearRaw = yearParen?.[1] ?? yearComma?.[1] ?? yearEnd?.[1]
  if (yearRaw) result.year = parseInt(yearRaw, 10)

  // Pages — patterns: 79-96 / pp.79-96 / : 79-96
  const pagesMatch = s.match(/(?:pp?\.\s*|:\s*)(\d+[-–]\d+)/)
    ?? s.match(/\b(\d{1,4}[-–]\d{1,4})\b(?=[.,)，。]|$)/)
  if (pagesMatch) result.pages = pagesMatch[1]

  // Volume & issue — e.g. 2024(5) / Vol.3, No.2 / 3(2)
  const volIssue = s.match(/\b(\d+)\((\d+)\)/)
  if (volIssue) { result.volume = volIssue[1]; result.issue = volIssue[2] }
  else {
    const volMatch = s.match(/[Vv]ol\.?\s*(\d+)/)
    const issueMatch = s.match(/[Nn]o\.?\s*(\d+)/)
    if (volMatch) result.volume = volMatch[1]
    if (issueMatch) result.issue = issueMatch[1]
  }

  // GB/T 7714 style: authors. title[J]. source, year(issue): pages.
  const gbtMatch = s.match(/^(.+?)[.。]\s+(.+?)\[([JMBDCGR])\][.。]?\s+(.+?),/)
  if (gbtMatch) {
    const authorStr = gbtMatch[1]
    result.authors = authorStr.split(/[,，]\s*/).map((a) => a.trim()).filter(Boolean)
    result.title = gbtMatch[2].trim()
    const typeMap: Record<string, CitationCreate['citation_type']> = {
      J: 'article', M: 'book', D: 'thesis', C: 'conference', G: 'other', B: 'book', R: 'other'
    }
    result.citation_type = typeMap[gbtMatch[3]] ?? 'other'
    result.source = gbtMatch[4].split(/\s*,\s*\d{4}/)[0].trim()
    return result
  }

  // APA style: Authors (Year). Title. Source, vol(issue), pages.
  const apaMatch = s.match(/^(.+?)\s*\(\d{4}\)\.\s*(.+?)\.\s*(.+?)(?:,\s*\d|\.|$)/)
  if (apaMatch) {
    const authorStr = apaMatch[1]
    result.authors = authorStr
      .split(/,\s*(?:&\s*)?|;\s*/)
      .map((a) => a.trim())
      .filter((a) => a && !a.match(/^\d/))
    result.title = apaMatch[2].trim()
    result.source = apaMatch[3].trim()
    result.citation_type = 'article'
    return result
  }

  // Fallback: try to pull out title from quotes or first sentence
  const quotedTitle = s.match(/["""''](.+?)["""'']/)
  if (quotedTitle) result.title = quotedTitle[1].trim()

  return result
}

interface CitationFormProps {
  open: boolean
  onClose: () => void
  onSubmit: (data: CitationCreate) => Promise<void>
  initialData?: CitationOut | null
}

export function CitationForm({ open, onClose, onSubmit, initialData }: CitationFormProps) {
  const { t } = useI18n()
  const [citationType, setCitationType] = useState<CitationCreate['citation_type']>(initialData?.citation_type ?? 'article')
  const [title, setTitle] = useState(initialData?.title ?? '')
  const [authors, setAuthors] = useState(initialData?.authors?.join(', ') ?? '')
  const [yearStr, setYearStr] = useState(String(initialData?.year ?? new Date().getFullYear()))
  const [source, setSource] = useState(initialData?.source ?? '')
  const [volume, setVolume] = useState(initialData?.volume ?? '')
  const [issue, setIssue] = useState(initialData?.issue ?? '')
  const [pages, setPages] = useState(initialData?.pages ?? '')
  const [doi, setDoi] = useState(initialData?.doi ?? '')
  const [url, setUrl] = useState(initialData?.url ?? '')
  const [publisher, setPublisher] = useState(initialData?.publisher ?? '')
  const [loading, setLoading] = useState(false)
  const [pasteText, setPasteText] = useState('')

  // Re-sync when initialData changes (e.g. opened for a different doc)
  useEffect(() => {
    setCitationType(initialData?.citation_type ?? 'article')
    setTitle(initialData?.title ?? '')
    setAuthors(initialData?.authors?.join(', ') ?? '')
    setYearStr(String(initialData?.year ?? ''))
    setSource(initialData?.source ?? '')
    setVolume(initialData?.volume ?? '')
    setIssue(initialData?.issue ?? '')
    setPages(initialData?.pages ?? '')
    setDoi(initialData?.doi ?? '')
    setUrl(initialData?.url ?? '')
    setPublisher(initialData?.publisher ?? '')
    setPasteText('')
  }, [initialData])

  // Auto-parse whenever the paste text changes
  useEffect(() => {
    if (!pasteText.trim()) return
    const parsed = parseCitationText(pasteText)
    if (parsed.citation_type) setCitationType(parsed.citation_type)
    if (parsed.title) setTitle(parsed.title)
    if (parsed.authors?.length) setAuthors(parsed.authors.join(', '))
    if (parsed.year) setYearStr(String(parsed.year))
    if (parsed.source) setSource(parsed.source)
    if (parsed.volume) setVolume(parsed.volume)
    if (parsed.issue) setIssue(parsed.issue)
    if (parsed.pages) setPages(parsed.pages)
    if (parsed.doi) setDoi(parsed.doi)
  }, [pasteText])

  const handleSubmit = async () => {
    setLoading(true)
    try {
      await onSubmit({
        citation_type: citationType,
        title: title.trim() || null,
        authors: authors.trim() ? authors.split(',').map((a) => a.trim()).filter(Boolean) : null,
        year: parseInt(yearStr, 10) || null,
        source: source.trim() || null,
        volume: volume.trim() || null,
        issue: issue.trim() || null,
        pages: pages.trim() || null,
        doi: doi.trim() || null,
        url: url.trim() || null,
        publisher: publisher.trim() || null,
        // Explicitly clear raw_citation so structured fields are always displayed
        raw_citation: null,
      })
      onClose()
    } catch (err) {
      console.error('Failed to save citation', err)
    } finally {
      setLoading(false)
    }
  }

  const citationTypes = citationTypeValues.map((value) => ({
    value,
    label: t(`citation_form.type_${value}`)
  }))

  return (
    <FormModal
      open={open}
      onOpenChange={(v) => { if (!v) onClose() }}
      title={initialData ? t('citation_form.edit_title') : t('citation_form.add_title')}
      onSubmit={handleSubmit}
      submitLabel={t('common.save')}
      loading={loading}
    >
      <div className="space-y-3">
        {/* Paste & auto-parse section — always visible, primary input */}
        <div className="rounded-lg border border-dashed border-black/20 dark:border-white/20 bg-black/3 dark:bg-white/3 px-3 py-2.5 space-y-2">
          <p className="text-xs font-medium text-neutral-500 dark:text-neutral-400">
            {t('citation_form.paste_title')} <span className="font-normal text-neutral-400 dark:text-neutral-500">{t('citation_form.paste_desc')}</span>
          </p>
          <textarea
            value={pasteText}
            onChange={(e) => setPasteText(e.target.value)}
            placeholder={t('citation_form.paste_placeholder')}
            className="w-full h-16 text-xs rounded-md border border-black/10 dark:border-white/10 bg-white dark:bg-white/5 px-2.5 py-2 text-neutral-900 dark:text-white placeholder-neutral-400 dark:placeholder-neutral-600 focus:outline-none focus:border-blue-500/60 resize-none"
          />
        </div>

        {/* Citation type */}
        <FormField label={t('citation_form.citation_type')}>
          <Select
            value={citationType}
            onValueChange={(v) => setCitationType(v as CitationCreate['citation_type'])}
            options={citationTypes}
          />
        </FormField>

        {/* Title */}
        <FormField label={t('citation_form.title')}>
          <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder={t('citation_form.title_placeholder')} />
        </FormField>

        {/* Authors */}
        <FormField label={t('citation_form.authors')} description={t('citation_form.authors_desc')}>
          <Input value={authors} onChange={(e) => setAuthors(e.target.value)} placeholder={t('citation_form.authors_placeholder')} />
        </FormField>

        {/* Year + Source */}
        <div className="grid grid-cols-2 gap-3">
          <FormField label={t('citation_form.year')}>
            <Input
              type="number"
              value={yearStr}
              onChange={(e) => setYearStr(e.target.value)}
              placeholder="2024"
              min={1900}
              max={2100}
            />
          </FormField>
          <FormField label={t('citation_form.source')}>
            <Input value={source} onChange={(e) => setSource(e.target.value)} placeholder={t('citation_form.source_placeholder')} />
          </FormField>
        </div>

        {/* Volume + Issue + Pages */}
        <div className="grid grid-cols-3 gap-3">
          <FormField label={t('citation_form.volume')}>
            <Input value={volume} onChange={(e) => setVolume(e.target.value)} placeholder={t('citation_form.volume_placeholder')} />
          </FormField>
          <FormField label={t('citation_form.issue')}>
            <Input value={issue} onChange={(e) => setIssue(e.target.value)} placeholder={t('citation_form.issue_placeholder')} />
          </FormField>
          <FormField label={t('citation_form.pages')}>
            <Input value={pages} onChange={(e) => setPages(e.target.value)} placeholder="79-96" />
          </FormField>
        </div>

        {/* DOI */}
        <FormField label="DOI">
          <Input value={doi} onChange={(e) => setDoi(e.target.value)} placeholder="10.xxxx/xxxxx" />
        </FormField>

        {/* URL */}
        <FormField label="URL">
          <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://..." />
        </FormField>

        {/* Publisher */}
        <FormField label={t('citation_form.publisher')}>
          <Input value={publisher} onChange={(e) => setPublisher(e.target.value)} placeholder={t('citation_form.publisher_placeholder')} />
        </FormField>
      </div>
    </FormModal>
  )
}
