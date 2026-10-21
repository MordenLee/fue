import * as PopoverPrimitive from '@radix-ui/react-popover'

interface PopoverProps {
  trigger: React.ReactNode
  children: React.ReactNode
  side?: 'top' | 'bottom' | 'left' | 'right'
  align?: 'start' | 'center' | 'end'
  className?: string
}

export function Popover({ trigger, children, side = 'bottom', align = 'center', className = '' }: PopoverProps) {
  return (
    <PopoverPrimitive.Root>
      <PopoverPrimitive.Trigger asChild>{trigger}</PopoverPrimitive.Trigger>
      <PopoverPrimitive.Portal>
        <PopoverPrimitive.Content
          side={side}
          align={align}
          sideOffset={5}
          className={`rounded-lg border border-white/10 bg-neutral-800 p-4 shadow-xl z-50
            animate-in fade-in-0 zoom-in-95 ${className}`}
        >
          {children}
          <PopoverPrimitive.Arrow className="fill-neutral-800" />
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  )
}
