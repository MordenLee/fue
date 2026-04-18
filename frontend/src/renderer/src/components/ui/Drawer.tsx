import * as DialogPrimitive from '@radix-ui/react-dialog'
import { X } from 'lucide-react'

interface DrawerProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title?: string
  children: React.ReactNode
  side?: 'left' | 'right'
  width?: string
}

export function Drawer({ open, onOpenChange, title, children, side = 'right', width = 'w-80' }: DrawerProps) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/40" />
        <DialogPrimitive.Content
          className={`fixed top-0 z-50 h-full ${width} bg-neutral-900 border-white/10 shadow-2xl
            flex flex-col transition-transform duration-200
            ${side === 'right' ? 'right-0 border-l' : 'left-0 border-r'}`}
        >
          {title && (
            <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
              <DialogPrimitive.Title className="text-sm font-semibold text-white">
                {title}
              </DialogPrimitive.Title>
              <DialogPrimitive.Close className="rounded-lg p-1 text-neutral-400 hover:text-white hover:bg-white/10">
                <X className="h-4 w-4" />
              </DialogPrimitive.Close>
            </div>
          )}
          <div className="flex-1 overflow-y-auto p-4">{children}</div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}
