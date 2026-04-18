import { Modal } from '../ui/Modal'
import { Button } from '../ui/Button'
import { AlertTriangle } from 'lucide-react'
import { useI18n } from '../../i18n'

export type DuplicateAction = 'reparse' | 'skip' | 'add'

interface DuplicateFilesDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  duplicateNames: string[]
  onAction: (action: DuplicateAction) => void
}

export function DuplicateFilesDialog({ open, onOpenChange, duplicateNames, onAction }: DuplicateFilesDialogProps) {
  const { t } = useI18n()

  return (
    <Modal open={open} onOpenChange={onOpenChange} title={t('knowledge.duplicate_title')}>
      <div className="flex items-start gap-3 mb-4">
        <AlertTriangle className="h-5 w-5 text-amber-500 shrink-0 mt-0.5" />
        <div className="text-sm text-gray-600 dark:text-neutral-300">
          <p className="mb-2">{t('knowledge.duplicate_intro')}</p>
          <ul className="list-disc list-inside space-y-0.5 max-h-32 overflow-y-auto text-gray-800 dark:text-neutral-200">
            {duplicateNames.map((name) => (
              <li key={name} className="truncate">{name}</li>
            ))}
          </ul>
          <p className="mt-3">{t('knowledge.duplicate_choose')}</p>
        </div>
      </div>
      <div className="flex flex-col gap-2">
        <Button variant="primary" onClick={() => onAction('reparse')} className="w-full justify-center">
          {t('knowledge.duplicate_reparse')}
        </Button>
        <Button variant="secondary" onClick={() => onAction('skip')} className="w-full justify-center">
          {t('knowledge.duplicate_skip')}
        </Button>
        <Button variant="secondary" onClick={() => onAction('add')} className="w-full justify-center">
          {t('knowledge.duplicate_add_all')}
        </Button>
        <Button variant="ghost" onClick={() => onOpenChange(false)} className="w-full justify-center">
          {t('common.cancel')}
        </Button>
      </div>
    </Modal>
  )
}
