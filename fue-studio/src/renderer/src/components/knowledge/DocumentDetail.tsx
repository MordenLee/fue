import { useState, useEffect } from 'react'
import { citationsService } from '../../services/citations'
import { CitationStyleSelect } from '../shared/CitationStyleSelect'
import { Button } from '../ui/Button'
import { Spinner } from '../ui/Spinner'
import type { DocumentFileOut, CitationOut } from '../../types/knowledge'
import { useI18n } from '../../i18n'

interface DocumentDetailProps {
  kbId: number
  doc: DocumentFileOut
  onEditCitation: (doc: DocumentFileOut) => void
  onReindex: () => void
  onDelete: () => void
}

export function DocumentDetail({ kbId, doc, onEditCitation, onReindex, onDelete }: DocumentDetailProps) {
  const { t } = useI18n()
  const [citation, setCitation] = useState<CitationOut | null>(null)
  const [formattedCitation, setFormattedCitation] = useState<string | null>(null)
  const [citationStyle, setCitationStyle] = useState('apa')
  const [loadingCitation, setLoadingCitation] = useState(false)

  useEffect(() => {
    if (!doc.has_citation) { setCitation(null); setFormattedCitation(null); return }
    let cancelled = false
    setLoadingCitation(true)
    citationsService.get(kbId, doc.id).then((c) => {
      if (!cancelled) setCitation(c)
    }).catch(() => {}).finally(() => { if (!cancelled) setLoadingCitation(false) })
    return () => { cancelled = true }
  }, [kbId, doc.id, doc.has_citation])

  useEffect(() => {
    if (!doc.has_citation) return
    let cancelled = false
    citationsService.getFormatted(kbId, doc.id, citationStyle).then((result) => {
      if (!cancelled) setFormattedCitation(result.text)
    }).catch(() => {})
    return () => { cancelled = true }
  }, [kbId, doc.id, doc.has_citation, citationStyle])

  return (
    <div className="px-6 py-4 bg-white/5 border-b border-white/10 space-y-3 animate-in slide-in-from-top-1 duration-200">
      {doc.abstract && (
        <div>
          <h4 className="text-xs text-neutral-500 mb-1">{t('knowledge.abstract')}</h4>
          <p className="text-sm text-neutral-300">{doc.abstract}</p>
        </div>
      )}

      {loadingCitation ? (
        <Spinner size="sm" />
      ) : citation ? (
        <div>
          <h4 className="text-xs text-neutral-500 mb-1">{t('knowledge.citation_info')}</h4>
          <div className="text-sm text-neutral-300 space-y-1">
            <p><span className="text-neutral-500">{t('knowledge.citation_type')}：</span>{citation.citation_type}</p>
            {citation.authors && <p><span className="text-neutral-500">{t('knowledge.citation_authors')}：</span>{citation.authors.join(', ')}</p>}
            {citation.year && <p><span className="text-neutral-500">{t('knowledge.citation_year')}：</span>{citation.year}</p>}
            {citation.doi && <p><span className="text-neutral-500">DOI：</span>{citation.doi}</p>}
          </div>
          <div className="mt-2 flex items-center gap-2">
            <Button size="sm" variant="secondary" onClick={() => onEditCitation(doc)}>{t('knowledge.edit_citation')}</Button>
            <CitationStyleSelect value={citationStyle} onChange={setCitationStyle} />
          </div>
          {formattedCitation && (
            <div className="mt-2 p-2 bg-white/5 rounded text-xs text-neutral-400 whitespace-pre-wrap">{formattedCitation}</div>
          )}
        </div>
      ) : (
        <p className="text-xs text-neutral-500">{t('knowledge.no_citation_info')}</p>
      )}

      <div className="flex gap-2 pt-1">
        <Button size="sm" variant="secondary" onClick={onReindex}>{t('knowledge.reindex')}</Button>
        <Button size="sm" variant="danger" onClick={onDelete}>{t('knowledge.delete_doc')}</Button>
      </div>
    </div>
  )
}
