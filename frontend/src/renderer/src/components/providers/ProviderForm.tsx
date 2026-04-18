import { useState } from 'react'
import { FormModal } from '../ui/FormModal'
import { FormField } from '../ui/FormField'
import { Input } from '../ui/Input'
import { Select } from '../ui/Select'
import type { ProviderCreate, InterfaceType } from '../../types/provider'
import { useI18n } from '../../i18n'

interface ProviderFormProps {
  open: boolean
  onClose: () => void
  onSubmit: (data: ProviderCreate) => Promise<void>
}

export function ProviderForm({ open, onClose, onSubmit }: ProviderFormProps) {
  const { t } = useI18n()
  const [name, setName] = useState('')
  const [interfaceType, setInterfaceType] = useState<InterfaceType>('openai')
  const [apiKey, setApiKey] = useState('')
  const [apiBase, setApiBase] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async () => {
    if (!name.trim()) return
    setLoading(true)
    try {
      await onSubmit({
        name: name.trim(),
        interface_type: interfaceType,
        api_key: apiKey.trim() || null,
        api_base_url: apiBase.trim() || null,
        is_enabled: true
      })
      onClose()
      setName('')
      setInterfaceType('openai')
      setApiKey('')
      setApiBase('')
    } finally {
      setLoading(false)
    }
  }

  const interfaceTypes = [
    { label: 'OpenAI', value: 'openai' },
    { label: 'Anthropic', value: 'anthropic' },
    { label: 'Google', value: 'google' },
    { label: 'Ollama', value: 'ollama' },
    { label: t('providers.interface_openai_compatible'), value: 'openai_compatible' },
    { label: 'Cohere', value: 'cohere' },
    { label: 'Jina', value: 'jina' }
  ]

  return (
    <FormModal
      open={open}
      onOpenChange={(v) => { if (!v) onClose() }}
      title={t('providers.add_provider')}
      onSubmit={handleSubmit}
      submitLabel={t('common.create')}
      loading={loading}
    >
      <div className="space-y-3">
        <FormField label={t('common.name')}>
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder={t('providers.provider_name_placeholder')} />
        </FormField>
        <FormField label={t('providers.interface_type')}>
          <Select value={interfaceType} onValueChange={(v) => setInterfaceType(v as InterfaceType)} options={interfaceTypes} />
        </FormField>
        <FormField label="API Key">
          <Input value={apiKey} onChange={(e) => setApiKey(e.target.value)} type="password" placeholder="sk-..." />
        </FormField>
        <FormField label={t('providers.api_base')}>
          <Input value={apiBase} onChange={(e) => setApiBase(e.target.value)} placeholder="https://api.openai.com" />
        </FormField>
      </div>
    </FormModal>
  )
}
