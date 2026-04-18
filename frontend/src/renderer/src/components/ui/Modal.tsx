import { useEffect } from 'react'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import { X } from 'lucide-react'

interface ModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: string
  children: React.ReactNode
  className?: string
}

export function Modal({ open, onOpenChange, title, description, children, className = '' }: ModalProps) {
  useEffect(() => {
    window.api?.setModalOverlay?.(open)
    return () => { if (open) window.api?.setModalOverlay?.(false) }
  }, [open])

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/60 animate-in fade-in-0" />
        <DialogPrimitive.Content
          className={`fixed left-1/2 top-1/2 z-50 -translate-x-1/2 -translate-y-1/2
            rounded-xl border border-neutral-200 dark:border-white/10 bg-white dark:bg-neutral-900 p-6 shadow-2xl
            animate-in fade-in-0 zoom-in-95 w-full max-w-md max-h-[85vh] overflow-y-auto ${className}`}
        >
          <div className="flex items-start justify-between mb-4">
            <div>
              <DialogPrimitive.Title className="text-lg font-semibold text-neutral-900 dark:text-white">
                {title}
              </DialogPrimitive.Title>
              {description && (
                <DialogPrimitive.Description className="mt-1 text-sm text-neutral-400">
                  {description}
                </DialogPrimitive.Description>
              )}
            </div>
            <DialogPrimitive.Close className="rounded-lg p-1 text-neutral-400 hover:text-neutral-900 dark:hover:text-white hover:bg-neutral-100 dark:hover:bg-white/10 transition">
              <X className="h-4 w-4" />
            </DialogPrimitive.Close>
          </div>
          {children}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}
