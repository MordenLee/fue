import { useState } from 'react'
import { FormModal } from '../ui/FormModal'
import { FormField } from '../ui/FormField'
import { Input } from '../ui/Input'
import { Textarea } from '../ui/Textarea'
import { NumberInput } from '../ui/NumberInput'
import { Switch } from '../ui/Switch'
import { ModelSelector } from '../shared/ModelSelector'
import type { KnowledgeBaseCreate } from '../../types/knowledge'
import { useI18n } from '../../i18n'

interface KBCreateFormProps {
  open: boolean
  onClose: () => void
  onSubmit: (data: KnowledgeBaseCreate) => Promise<void>
}

export function KBCreateForm({ open, onClose, onSubmit }: KBCreateFormProps) {
  const { t } = useI18n()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [embedModelId, setEmbedModelId] = useState<number | null>(null)
  const [rerankModelId, setRerankModelId] = useState<number | null>(null)
  const [chunkSize, setChunkSize] = useState(500)
  const [chunkOverlap, setChunkOverlap] = useState(50)
  const [useDelimiterSplit, setUseDelimiterSplit] = useState(true)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async () => {
    if (!name.trim() || !embedModelId) return
    setLoading(true)
    try {
      await onSubmit({
        name: name.trim(),
        description: description.trim() || null,
        embed_model_id: embedModelId,
        rerank_model_id: rerankModelId,
        chunk_size: chunkSize,
        chunk_overlap: chunkOverlap,
        use_delimiter_split: useDelimiterSplit
      })
      onClose()
      setName('')
      setDescription('')
      setEmbedModelId(null)
      setRerankModelId(null)
      setChunkSize(500)
      setChunkOverlap(50)
      setUseDelimiterSplit(true)
    } finally {
      setLoading(false)
    }
  }

  return (
    <FormModal
      open={open}
      onOpenChange={(v) => { if (!v) onClose() }}
      title={t('knowledge.new_kb')}
      onSubmit={handleSubmit}
      submitLabel={t('common.create')}
      loading={loading}
    >
      <div className="space-y-4">
        <FormField label={t('common.name')}>
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder={t('knowledge.kb_name_placeholder')} />
        </FormField>
        <FormField label={t('common.description')}>
          <Textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder={t('common.optional_description')} rows={2} />
        </FormField>
        <FormField label={t('knowledge.embedding_model')}>
          <ModelSelector
            value={embedModelId}
            onChange={setEmbedModelId}
            modelType="embedding"
          />
        </FormField>
        <FormField label={t('knowledge.rerank_model')}>
          <ModelSelector
            value={rerankModelId}
            onChange={setRerankModelId}
            modelType="reranking"
          />
        </FormField>
        <div className="grid grid-cols-2 gap-4">
          <FormField label={t('knowledge.chunk_size')}>
            <NumberInput fullWidth value={chunkSize} onChange={setChunkSize} min={100} max={5000} step={50} />
          </FormField>
          <FormField label={t('knowledge.chunk_overlap')}>
            <NumberInput fullWidth value={chunkOverlap} onChange={setChunkOverlap} min={0} max={500} step={10} />
          </FormField>
        </div>
        
        <div className="flex items-start justify-between p-3 border border-neutral-200 dark:border-white/10 rounded-lg bg-neutral-50 dark:bg-white/5">
          <div className="flex flex-col gap-1 pr-4">
            <span className="text-sm font-medium text-neutral-900 dark:text-neutral-100">
              {t('knowledge.use_delimiter_split')}
            </span>
            <span className="text-xs text-neutral-500 dark:text-neutral-400">
              {t('knowledge.use_delimiter_split_desc')}
            </span>
          </div>
          <div className="shrink-0 mt-0.5">
            <Switch checked={useDelimiterSplit} onCheckedChange={setUseDelimiterSplit} />
          </div>
        </div>
      </div>
    </FormModal>
  )
}
