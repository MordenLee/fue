import { useState, useEffect } from 'react'
import { Eye, EyeOff, TestTube2, Save, Trash2 } from 'lucide-react'
import { Button } from '../ui/Button'
import { Switch } from '../ui/Switch'
import { FormField } from '../ui/FormField'
import { Input } from '../ui/Input'
import { Textarea } from '../ui/Textarea'
import { Select } from '../ui/Select'
import { useToast } from '../../contexts/ToastContext'
import { getProviderLogo } from '../../utils/providerLogos'
import { TestConnectivityDialog } from './TestConnectivityDialog'
import type { ProviderOut, ProviderUpdate, AIModelOut, InterfaceType } from '../../types/provider'
import { useI18n } from '../../i18n'

const interfaceOptions = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'google', label: 'Google' },
  { value: 'ollama', label: 'Ollama' },
  { value: 'openai_compatible', label: 'OpenAI Compatible' },
  { value: 'cohere', label: 'Cohere' },
  { value: 'jina', label: 'Jina' },
]

interface ProviderConfigProps {
  provider: ProviderOut
  models: AIModelOut[]
  onUpdate: (id: number, data: ProviderUpdate) => Promise<void>
  onToggle: (id: number, enabled: boolean) => Promise<void>
  onDelete: (id: number) => void
}

export function ProviderConfig({ provider, models, onUpdate, onToggle, onDelete }: ProviderConfigProps) {
  const toast = useToast()
  const { t } = useI18n()
  const [apiKey, setApiKey] = useState(provider.api_key ?? '')
  const [apiBase, setApiBase] = useState(provider.api_base_url ?? '')
  const [interfaceType, setInterfaceType] = useState<InterfaceType>(provider.interface_type)
  const [description, setDescription] = useState(provider.description ?? '')
  const [showKey, setShowKey] = useState(false)
  const [saving, setSaving] = useState(false)
  const [testDialogOpen, setTestDialogOpen] = useState(false)

  useEffect(() => {
    setApiKey(provider.api_key ?? '')
    setApiBase(provider.api_base_url ?? '')
    setInterfaceType(provider.interface_type)
    setDescription(provider.description ?? '')
    setShowKey(false)
  }, [provider.id])

  const handleSave = async () => {
    setSaving(true)
    try {
      await onUpdate(provider.id, {
        api_key: apiKey.trim() || null,
        api_base_url: apiBase.trim() || null,
        interface_type: interfaceType,
        description: description.trim() || null
      })
      toast.success(t('providers.config_saved'))
    } catch {
      toast.error(t('common.save_failed'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="px-6 py-4 border-b border-white/10">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          {getProviderLogo(provider.name) && (
            <span className="flex items-center justify-center h-8 w-8 shrink-0 rounded-lg bg-neutral-200 dark:bg-neutral-700">
              <img src={getProviderLogo(provider.name)!} alt="" className="h-5 w-5" />
            </span>
          )}
          <div>
            <h2 className="text-lg font-bold text-neutral-900 dark:text-white">{provider.name}</h2>
            <p className="text-xs text-neutral-500">{provider.interface_type}</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-sm text-neutral-400">{t('common.enabled')}</span>
            <Switch checked={provider.is_enabled} onCheckedChange={(v) => onToggle(provider.id, v)} />
          </div>
          <Button variant="danger" size="sm" onClick={() => onDelete(provider.id)}>
            <Trash2 className="h-4 w-4 mr-1" />
            {t('common.delete')}
          </Button>
        </div>
      </div>

      <div className="space-y-3">
        <FormField label="API Key">
          <div className="relative">
            <Input
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              type={showKey ? 'text' : 'password'}
              placeholder={t('providers.api_key_placeholder')}
            />
            <button
              type="button"
              onClick={() => setShowKey(!showKey)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-neutral-500 hover:text-neutral-300"
            >
              {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
        </FormField>
        <FormField label={t('providers.api_base')}>
          <Input value={apiBase} onChange={(e) => setApiBase(e.target.value)} placeholder="https://api.openai.com" />
        </FormField>
        <FormField label={t('providers.interface_type')}>
          <Select value={interfaceType} onValueChange={(v) => setInterfaceType(v as InterfaceType)} options={interfaceOptions} />
        </FormField>
        <FormField label={t('common.description')}>
          <Textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder={t('common.optional_description')} rows={2} />
        </FormField>
        <div className="flex items-center justify-end gap-2 pt-1">
          <Button variant="secondary" size="sm" onClick={() => setTestDialogOpen(true)}>
            <TestTube2 className="h-3.5 w-3.5 mr-1" />
            {t('providers.test_connectivity')}
          </Button>
          <Button size="sm" onClick={handleSave} loading={saving}>
            <Save className="h-3.5 w-3.5 mr-1" />
            {t('common.save')}
          </Button>
        </div>
      </div>

      <TestConnectivityDialog
        open={testDialogOpen}
        onOpenChange={setTestDialogOpen}
        provider={provider}
        models={models}
      />
    </div>
  )
}
