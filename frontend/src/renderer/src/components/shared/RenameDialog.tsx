import { useState, useEffect } from 'react'
import { FormModal } from '../ui/FormModal'
import { FormField } from '../ui/FormField'
import { Input } from '../ui/Input'
import { useI18n } from '../../i18n'

interface RenameDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  initialValue: string
  onConfirm: (name: string) => void
}

export function RenameDialog({
  open, onOpenChange, title, initialValue, onConfirm
}: RenameDialogProps) {
  const { t } = useI18n()
  const [value, setValue] = useState(initialValue)

  useEffect(() => {
    if (open) setValue(initialValue)
  }, [open, initialValue])

  return (
    <FormModal
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      onSubmit={() => {
        const trimmed = value.trim()
        if (trimmed) {
          onConfirm(trimmed)
          onOpenChange(false)
        }
      }}
      submitLabel={t('common.rename')}
    >
      <FormField label={t('common.name')}>
        <Input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          autoFocus
        />
      </FormField>
    </FormModal>
  )
}
