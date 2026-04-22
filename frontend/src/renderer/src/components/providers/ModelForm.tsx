import { useState, useEffect } from 'react'
import { Eye, Brain, Wrench } from 'lucide-react'
import { FormModal } from '../ui/FormModal'
import { FormField } from '../ui/FormField'
import { Input } from '../ui/Input'
import { Select } from '../ui/Select'
import type { AIModelCreate, AIModelUpdate, AIModelOut, ModelType, Capability } from '../../types/provider'
import { useI18n } from '../../i18n'

const capabilityOptions: { value: Capability; labelKey: string; icon: React.ReactNode }[] = [
  { value: 'vision', labelKey: 'providers.capability_vision', icon: <Eye className="h-4 w-4" /> },
  { value: 'reasoning', labelKey: 'providers.capability_reasoning', icon: <Brain className="h-4 w-4" /> },
  { value: 'function_calling', labelKey: 'providers.capability_function_calling', icon: <Wrench className="h-4 w-4" /> },
]

interface ModelFormProps {
  open: boolean
  onClose: () => void
  onSubmit: (data: AIModelCreate | AIModelUpdate) => Promise<void>
  providerId: number
  initialData?: AIModelOut | null
}

export function ModelForm({ open, onClose, onSubmit, providerId, initialData }: ModelFormProps) {
  const { t } = useI18n()
  const [apiName, setApiName] = useState(initialData?.api_name ?? '')
  const [displayName, setDisplayName] = useState(initialData?.display_name ?? '')
  const [series, setSeries] = useState(initialData?.series ?? '')
  const [modelType, setModelType] = useState<ModelType>(initialData?.model_type ?? 'chat')
  const [contextLength, setContextLength] = useState(initialData?.context_length ?? 128)
  const [qps, setQps] = useState<number | null>(initialData?.qps ?? null)
  const [capabilities, setCapabilities] = useState<Capability[]>(initialData?.capabilities ?? [])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (open) {
      setApiName(initialData?.api_name ?? '')
      setDisplayName(initialData?.display_name ?? '')
      setSeries(initialData?.series ?? '')
      setModelType(initialData?.model_type ?? 'chat')
      setContextLength(initialData?.context_length ?? 128)
      setQps(initialData?.qps ?? null)
      setCapabilities(initialData?.capabilities ?? [])
    }
  }, [open, initialData])

  const toggleCapability = (cap: Capability) => {
    setCapabilities((prev) => prev.includes(cap) ? prev.filter((c) => c !== cap) : [...prev, cap])
  }

  const handleSubmit = async () => {
    if (!apiName.trim() || !displayName.trim()) return
    setLoading(true)
    try {
      const data = {
        provider_id: providerId,
        api_name: apiName.trim(),
        display_name: displayName.trim(),
        series: series.trim() || null,
        model_type: modelType,
        context_length: contextLength,
        capabilities: modelType === 'chat' ? capabilities : [],
        qps: qps
      }
      await onSubmit(data)
      onClose()
    } finally {
      setLoading(false)
    }
  }

  const modelTypes = [
    { label: t('providers.type_chat'), value: 'chat' },
    { label: 'Embedding', value: 'embedding' },
    { label: 'Reranking', value: 'reranking' }
  ]

  return (
    <FormModal
      open={open}
      onOpenChange={(v) => { if (!v) onClose() }}
      title={initialData ? t('providers.edit_model') : t('providers.add_model')}
      onSubmit={handleSubmit}
      submitLabel={initialData ? t('common.save') : t('common.create')}
      loading={loading}
      className="max-w-md"
    >
      <div className="space-y-4">
        <FormField label={t('providers.api_name')}>
          <Input value={apiName} onChange={(e) => setApiName(e.target.value)} placeholder="gpt-4o" />
        </FormField>
        <FormField label={t('providers.display_name')}>
          <Input value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="GPT-4o" />
        </FormField>
        <FormField label={t('providers.series')} description={t('providers.series_desc')}>
          <Input value={series} onChange={(e) => setSeries(e.target.value)} placeholder={t('providers.series_placeholder')} />
        </FormField>
        <FormField label={t('providers.model_type')}>
          <Select value={modelType} onValueChange={(v) => setModelType(v as ModelType)} options={modelTypes} />
        </FormField>
        <FormField label={t('providers.context_length')}>
          <Input
            value={String(contextLength)}
            onChange={(e) => {
              const v = parseInt(e.target.value, 10)
              if (!isNaN(v) && v >= 0) setContextLength(v)
              else if (e.target.value === '') setContextLength(0)
            }}
            type="number"
            placeholder="128"
            suffixIcon={<span className="text-xs text-neutral-400 font-medium">K</span>}
          />
        </FormField>
        <FormField label={t('providers.qps_limit')} description={t('providers.qps_limit_desc')}>
          <Input
            value={qps !== null ? String(qps) : ''}
            onChange={(e) => {
              const v = parseInt(e.target.value, 10)
              if (!isNaN(v) && v >= 0) setQps(v)
              else if (e.target.value === '') setQps(null)
            }}
            type="number"
            placeholder={t('providers.unlimited')}
            suffixIcon={<span className="text-xs text-neutral-400 font-medium">{t('providers.per_second')}</span>}
          />
        </FormField>
        {modelType === 'chat' && (
          <FormField label={t('providers.capabilities')}>
            <div className="flex flex-wrap gap-2">
              {capabilityOptions.map((cap) => {
                const active = capabilities.includes(cap.value)
                return (
                  <button
                    key={cap.value}
                    type="button"
                    onClick={() => toggleCapability(cap.value)}
                    className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm transition
                      ${active
                        ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
                        : 'border-neutral-200 dark:border-white/10 bg-neutral-50 dark:bg-white/5 text-neutral-500 dark:text-neutral-400 hover:border-neutral-300 dark:hover:border-white/20'
                      }`}
                  >
                    {cap.icon}
                    {t(cap.labelKey)}
                  </button>
                )
              })}
            </div>
          </FormField>
        )}
      </div>
    </FormModal>
  )
}
