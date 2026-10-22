import { useRef, useState } from 'react'
import { FormModal } from '../ui/FormModal'
import { FormField } from '../ui/FormField'
import { Input } from '../ui/Input'
import { ModelSelector } from '../shared/ModelSelector'
import { knowledgeService } from '../../services/knowledge'
import { useI18n } from '../../i18n'

export function KBImportForm({ onClose, onImported }: {
  onClose: () => void
  onImported: (id: number, message: string) => Promise<void>
}) {
  const { t } = useI18n()
  const [file, setFile] = useState<File | null>(null)
  const [name, setName] = useState('')
  const [model, setModel] = useState<number | null>(null)
  const [confirmed, setConfirmed] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const selection = useRef(0)
  const [preview, setPreview] = useState<{ model: string; documents: number; chunks: number; dimension: number; verified: boolean } | null>(null)

  async function selectFile(candidate: File | null) {
    const version = ++selection.current
    setFile(null)
    setPreview(null)
    setConfirmed(false)
    setError('')
    if (!candidate) return
    if (candidate.size > 256 * 1024 * 1024) { setError(t('knowledge.transfer_size')); return }
    try {
      const data = JSON.parse(await candidate.text())
      if (version !== selection.current) return
      if (data?.format !== 'fue-knowledge-base' || data.format_version !== '2.0' || !Array.isArray(data.documents)) {
        throw new Error(t('knowledge.transfer_format'))
      }
      setPreview({ model: String(data.embedding_profile?.api_name ?? ''), documents: data.documents.length,
        chunks: data.documents.reduce((total: number, doc: { chunks?: unknown[] }) => total + (doc.chunks?.length ?? 0), 0),
        dimension: Number(data.dimension), verified: data.profile_verified === true })
      setFile(candidate)
    } catch (e) { if (version === selection.current) setError(e instanceof Error ? e.message : String(e)) }
  }

  async function submit() {
    if (loading) return
    if (!file || !model) { setError(t('knowledge.transfer_required')); return }
    if (file.size > 256 * 1024 * 1024) { setError(t('knowledge.transfer_size')); return }
    setLoading(true)
    setError('')
    try {
      const result = await knowledgeService.importKB(file, model, name.trim(), confirmed)
      await onImported(result.knowledge_base.id,
        t('knowledge.transfer_success', { documents: result.documents_created, chunks: result.chunks_imported })
        + (result.warnings.length ? '\n' + result.warnings.join('\n') : ''))
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally { setLoading(false) }
  }

  return <FormModal open onOpenChange={(open) => { if (!open && !loading) onClose() }}
    title={t('knowledge.transfer_import')} onSubmit={() => void submit()}
    submitLabel={t('knowledge.transfer_import')} loading={loading}>
    <p className="text-sm text-neutral-500">{t('knowledge.transfer_description')}</p>
    <FormField label={t('knowledge.transfer_file')}>
      <Input type="file" accept=".json,application/json" disabled={loading}
        onChange={e => void selectFile(e.target.files?.[0] ?? null)} />
    </FormField>
    {preview && <p className="rounded-lg bg-neutral-100 dark:bg-white/5 p-3 text-sm break-words">
      {t('knowledge.transfer_preview', { model: preview.model, dimension: preview.dimension, documents: preview.documents, chunks: preview.chunks })}
    </p>}
    <FormField label={t('common.name')}>
      <Input value={name} maxLength={128} disabled={loading} placeholder={t('knowledge.transfer_name')}
        onChange={e => setName(e.target.value)} />
    </FormField>
    <FormField label={t('knowledge.embedding_model')}>
      <ModelSelector value={model} onChange={setModel} modelType="embedding" disabled={loading} />
    </FormField>
    <p className="text-xs text-neutral-500">{t('knowledge.transfer_model')}</p>
    {preview && !preview.verified && <label className="flex items-start gap-3 text-sm">
      <input type="checkbox" className="mt-1 shrink-0" checked={confirmed} disabled={loading}
        onChange={e => setConfirmed(e.target.checked)} />
      <span>{t('knowledge.transfer_confirm')}</span>
    </label>}
    {loading && <p role="status" className="text-sm">{t('knowledge.transfer_busy')}</p>}
    {error && <p role="alert" className="text-sm text-red-500 break-words">{error}</p>}
  </FormModal>
}
