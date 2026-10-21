import { useState, useEffect } from 'react'
import { Edit, Download } from 'lucide-react'
import { IconButton } from '../ui/IconButton'
import { Tooltip } from '../ui/Tooltip'
import { formatDate } from '../../utils/format'
import { modelsService } from '../../services/models'
import type { KnowledgeBaseOut } from '../../types/knowledge'
import { useI18n } from '../../i18n'

interface KBInfoPanelProps {
  kb: KnowledgeBaseOut
  onEdit: () => void
  onExport: () => void
}

export function KBInfoPanel({ kb, onEdit, onExport }: KBInfoPanelProps) {
  const { t } = useI18n()
  const [embedModelName, setEmbedModelName] = useState<string>('')
  const [rerankModelName, setRerankModelName] = useState<string>('')

  useEffect(() => {
    modelsService.getById(kb.embed_model_id).then((m) => {
      setEmbedModelName(m.display_name || m.api_name)
    }).catch(() => setEmbedModelName(`#${kb.embed_model_id}`))

    if (kb.rerank_model_id) {
      modelsService.getById(kb.rerank_model_id).then((m) => {
        setRerankModelName(m.display_name || m.api_name)
      }).catch(() => setRerankModelName(`#${kb.rerank_model_id}`))
    } else {
      setRerankModelName(t('common.not_set'))
    }
  }, [kb.embed_model_id, kb.rerank_model_id, t])

  return (
    <div className="px-6 py-4 border-b border-black/10 dark:border-white/10">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{kb.name}</h2>
        <div className="flex gap-1">
          <Tooltip content={t('common.edit')}>
            <IconButton onClick={onEdit}><Edit className="h-4 w-4" /></IconButton>
          </Tooltip>
          <Tooltip content={t('common.export')}>
            <IconButton onClick={onExport}><Download className="h-4 w-4" /></IconButton>
          </Tooltip>
        </div>
      </div>
      {kb.description && (
        <p className="text-sm text-gray-600 dark:text-neutral-300 mb-3">{kb.description}</p>
      )}
      <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
        <InfoRow label={t('knowledge.embedding_model')} value={embedModelName || t('common.loading')} />
        <InfoRow label={t('knowledge.rerank_model')} value={rerankModelName || t('common.loading')} />
        <InfoRow label={t('knowledge.chunk_size_plain')} value={t('knowledge.characters_with_value', { value: kb.chunk_size })} />
        <InfoRow label={t('knowledge.chunk_overlap_plain')} value={t('knowledge.characters_with_value', { value: kb.chunk_overlap })} />
        <InfoRow label={t('knowledge.use_delimiter_split')} value={kb.use_delimiter_split ? t('common.enabled') : t('common.disabled')} />
        <InfoRow label={t('knowledge.document_count')} value={String(kb.document_count)} />
        <InfoRow label={t('knowledge.created_at')} value={formatDate(kb.created_at)} />
      </div>
    </div>
  )
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center gap-2 py-0.5">
      <span className="text-gray-500 dark:text-neutral-500 shrink-0">{label}:</span>
      <span className="text-gray-800 dark:text-neutral-300 truncate">{value}</span>
    </div>
  )
}
