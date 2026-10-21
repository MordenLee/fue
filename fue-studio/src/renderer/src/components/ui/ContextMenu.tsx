import * as ContextMenuPrimitive from '@radix-ui/react-context-menu'

export interface ContextMenuItem {
  label: string
  icon?: React.ReactNode
  onClick: () => void
  danger?: boolean
  disabled?: boolean
}

interface ContextMenuProps {
  items: ContextMenuItem[]
  children: React.ReactNode
}

export function ContextMenu({ items, children }: ContextMenuProps) {
  return (
    <ContextMenuPrimitive.Root>
      <ContextMenuPrimitive.Trigger asChild>{children}</ContextMenuPrimitive.Trigger>
      <ContextMenuPrimitive.Portal>
        <ContextMenuPrimitive.Content
          className="min-w-[160px] rounded-lg border border-white/10 bg-neutral-800 p-1 shadow-xl z-50"
        >
          {items.map((item, i) => (
            <ContextMenuPrimitive.Item
              key={i}
              disabled={item.disabled}
              onSelect={item.onClick}
              className={`flex items-center gap-2 rounded-md px-3 py-1.5 text-sm outline-none cursor-pointer
                select-none transition
                ${item.danger ? 'text-red-400 hover:bg-red-500/10' : 'text-neutral-300 hover:bg-white/10'}
                data-[disabled]:opacity-50 data-[disabled]:pointer-events-none`}
            >
              {item.icon && <span className="w-4 h-4">{item.icon}</span>}
              {item.label}
            </ContextMenuPrimitive.Item>
          ))}
        </ContextMenuPrimitive.Content>
      </ContextMenuPrimitive.Portal>
    </ContextMenuPrimitive.Root>
  )
}
