import { useState, useEffect } from 'react'
import { Folder as FolderIcon } from 'lucide-react'
import { FormModal } from '../ui/FormModal'
import type { Folder } from '../../types/folder'
import { useI18n } from '../../i18n'

interface MoveFolderDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  folders: Folder[]
  currentFolderId: string | null
  onConfirm: (folderId: string | null) => void
}

export function MoveFolderDialog({
  open, onOpenChange, folders, currentFolderId, onConfirm
}: MoveFolderDialogProps) {
  const { t } = useI18n()
  const [selected, setSelected] = useState<string | null>(currentFolderId)

  useEffect(() => {
    if (open) setSelected(currentFolderId)
  }, [open, currentFolderId])

  return (
    <FormModal
      open={open}
      onOpenChange={onOpenChange}
      title={t('dialog.move_folder_title')}
      onSubmit={() => {
        onConfirm(selected)
        onOpenChange(false)
      }}
      submitLabel={t('common.confirm')}
    >
      <div className="flex flex-col gap-1 max-h-60 overflow-y-auto -mx-1 px-1">
        {/* "No folder" option */}
        <button
          type="button"
          onClick={() => setSelected(null)}
          className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm text-left transition
            ${selected === null
              ? 'bg-blue-600/20 text-blue-400'
              : 'text-neutral-300 hover:bg-white/5'}`}
        >
          <span className="w-4 h-4 flex items-center justify-center text-neutral-500 text-xs">—</span>
          {t('dialog.no_folder')}
        </button>

        {folders.map((folder) => (
          <button
            key={folder.id}
            type="button"
            onClick={() => setSelected(folder.id)}
            className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm text-left transition
              ${selected === folder.id
                ? 'bg-blue-600/20 text-blue-400'
                : 'text-neutral-300 hover:bg-white/5'}`}
          >
            <FolderIcon className="w-4 h-4 shrink-0" />
            <span className="truncate">{folder.name}</span>
          </button>
        ))}

        {folders.length === 0 && (
          <p className="text-sm text-neutral-500 px-3 py-2">
            {t('dialog.no_folder_hint')} <FolderIcon className="inline w-3.5 h-3.5" />
          </p>
        )}
      </div>
    </FormModal>
  )
}
