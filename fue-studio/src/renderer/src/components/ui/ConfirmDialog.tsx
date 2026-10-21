import { Modal } from './Modal'
import { Button } from './Button'
import { useI18n } from '../../i18n'

interface ConfirmDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: string
  confirmLabel?: string
  cancelLabel?: string
  danger?: boolean
  loading?: boolean
  onConfirm: () => void
}

export function ConfirmDialog({
  open, onOpenChange, title, description,
  confirmLabel, cancelLabel,
  danger, loading, onConfirm
}: ConfirmDialogProps) {
  const { t } = useI18n()

  return (
    <Modal open={open} onOpenChange={onOpenChange} title={title} description={description}>
      <div className="flex justify-end gap-2 mt-6">
        <Button variant="ghost" onClick={() => onOpenChange(false)}>{cancelLabel ?? t('common.cancel')}</Button>
        <Button variant={danger ? 'danger' : 'primary'} loading={loading} onClick={onConfirm}>
          {confirmLabel ?? t('common.confirm')}
        </Button>
      </div>
    </Modal>
  )
}
