import * as DropdownMenuPrimitive from '@radix-ui/react-dropdown-menu'

export interface DropdownMenuItem {
  label: string
  icon?: React.ReactNode
  onClick: () => void
  danger?: boolean
  disabled?: boolean
}

interface DropdownMenuProps {
  trigger: React.ReactNode
  items: DropdownMenuItem[]
  align?: 'start' | 'center' | 'end'
}

export function DropdownMenu({ trigger, items, align = 'end' }: DropdownMenuProps) {
  return (
    <DropdownMenuPrimitive.Root>
      <DropdownMenuPrimitive.Trigger asChild>{trigger}</DropdownMenuPrimitive.Trigger>
      <DropdownMenuPrimitive.Portal>
        <DropdownMenuPrimitive.Content
          align={align}
          sideOffset={5}
          className="min-w-[160px] rounded-lg border border-white/10 bg-neutral-800 p-1 shadow-xl z-50
            animate-in fade-in-0 zoom-in-95"
        >
          {items.map((item, i) => (
            <DropdownMenuPrimitive.Item
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
            </DropdownMenuPrimitive.Item>
          ))}
        </DropdownMenuPrimitive.Content>
      </DropdownMenuPrimitive.Portal>
    </DropdownMenuPrimitive.Root>
  )
}
