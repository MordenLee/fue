import { useState, useEffect } from 'react'
import { TestTube2, CheckCircle2, XCircle } from 'lucide-react'
import { Modal } from '../ui/Modal'
import { Button } from '../ui/Button'
import { Select } from '../ui/Select'
import { useToast } from '../../contexts/ToastContext'
import { providersService } from '../../services/providers'
import type { AIModelOut, ProviderOut } from '../../types/provider'
import { useI18n } from '../../i18n'

interface TestConnectivityDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  provider: ProviderOut
  models: AIModelOut[]
}

export function TestConnectivityDialog({ open, onOpenChange, provider, models }: TestConnectivityDialogProps) {
  const toast = useToast()
  const { t } = useI18n()
  const chatModels = models.filter((m) => m.model_type === 'chat')
  const [selectedModelId, setSelectedModelId] = useState<string>('')
  const [testing, setTesting] = useState(false)
  const [result, setResult] = useState<{ success: boolean; message: string; latency_ms: number } | null>(null)

  const modelOptions = chatModels.map((m) => ({
    value: String(m.id),
    label: m.display_name || m.api_name
  }))

  useEffect(() => {
    if (open) {
      setSelectedModelId(chatModels[0] ? String(chatModels[0].id) : '')
      setResult(null)
      setTesting(false)
    }
  }, [open])

  const handleTest = async () => {
    if (!selectedModelId) {
      toast.error(t('providers.choose_model_first'))
      return
    }
    setTesting(true)
    setResult(null)
    try {
      const res = await providersService.test(provider.id, Number(selectedModelId))
      setResult(res)
    } catch {
      setResult({ success: false, message: t('providers.request_failed_check_network'), latency_ms: 0 })
    } finally {
      setTesting(false)
    }
  }

  return (
    <Modal open={open} onOpenChange={onOpenChange} title={t('providers.test_connectivity')} description={t('providers.test_connectivity_desc')} className="max-w-sm">
      <div className="space-y-4">
        <Select
          value={selectedModelId}
          onValueChange={(v) => { setSelectedModelId(v); setResult(null) }}
          options={modelOptions}
          placeholder={t('common.select_model')}
          disabled={chatModels.length === 0}
        />

        {/* Result display */}
        {result && (
          <div className={`flex items-center gap-2 rounded-lg px-3 py-2.5 text-sm ${
            result.success
              ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400'
              : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400'
          }`}>
            {result.success
              ? <CheckCircle2 className="h-4 w-4 shrink-0" />
              : <XCircle className="h-4 w-4 shrink-0" />
            }
            <span className="flex-1">
              {result.success ? t('providers.connect_success_ms', { latency: result.latency_ms }) : result.message}
            </span>
          </div>
        )}

        {/* Actions */}
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
          <Button onClick={handleTest} loading={testing} disabled={chatModels.length === 0}>
            <TestTube2 className="h-4 w-4 mr-1" />
            {t('common.test')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
