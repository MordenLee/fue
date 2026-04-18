import { useState, useEffect } from 'react'
import { Select, type SelectOption } from '../ui/Select'
import { modelsService } from '../../services/models'
import type { AIModelOut, ModelType } from '../../types/provider'
import { useI18n } from '../../i18n'

interface ModelSelectorProps {
  value: number | null
  onChange: (modelId: number | null) => void
  modelType?: ModelType
  label?: string
  placeholder?: string
  disabled?: boolean
}

export function ModelSelector({
  value, onChange, modelType, label, placeholder, disabled
}: ModelSelectorProps) {
  const { t } = useI18n()
  const [models, setModels] = useState<AIModelOut[]>([])

  useEffect(() => {
    modelsService
      .list({ model_type: modelType, enabled_only: true })
      .then(setModels)
      .catch(console.error)
  }, [modelType])

  const options: SelectOption[] = [
    { value: '__none__', label: t('common.none_option') },
    ...models.map((m) => ({
      value: String(m.id),
      label: `${m.display_name || m.api_name}  |  ${m.provider_name}`
    }))
  ]

  return (
    <Select
      value={value !== null ? String(value) : '__none__'}
      onValueChange={(v) => onChange(v === '__none__' ? null : Number(v))}
      options={options}
      label={label}
      placeholder={placeholder ?? t('common.select_model')}
      disabled={disabled}
    />
  )
}
