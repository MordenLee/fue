import * as TooltipPrimitive from '@radix-ui/react-tooltip'

interface TooltipProps {
  content: string
  children: React.ReactNode
  side?: 'top' | 'bottom' | 'left' | 'right'
}

export function Tooltip({ content, children, side = 'top' }: TooltipProps) {
  return (
    <TooltipPrimitive.Root>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          side={side}
          sideOffset={5}
          className="rounded-md bg-neutral-800 px-2.5 py-1.5 text-xs text-white shadow-lg
            border border-white/10 animate-in fade-in-0 zoom-in-95 z-50"
        >
          {content}
          <TooltipPrimitive.Arrow className="fill-neutral-800" />
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  )
}
