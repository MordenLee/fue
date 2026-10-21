import { Modal } from './Modal'
import { Button } from './Button'
import { useI18n } from '../../i18n'

interface FormModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: string
  children: React.ReactNode
  submitLabel?: string
  loading?: boolean
  onSubmit: () => void
  className?: string
}

export function FormModal({
  open, onOpenChange, title, description, children,
  submitLabel, loading, onSubmit, className
}: FormModalProps) {
  const { t } = useI18n()

  return (
    <Modal open={open} onOpenChange={onOpenChange} title={title} description={description} className={className}>
      <form
        onSubmit={(e) => { e.preventDefault(); onSubmit() }}
        className="flex flex-col gap-4"
      >
        {children}
        <div className="flex justify-end gap-2 mt-2">
          <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>{t('common.cancel')}</Button>
          <Button type="submit" loading={loading}>{submitLabel ?? t('common.save')}</Button>
        </div>
      </form>
    </Modal>
  )
}
