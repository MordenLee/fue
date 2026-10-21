import * as ScrollAreaPrimitive from '@radix-ui/react-scroll-area'

interface ScrollAreaProps {
  children: React.ReactNode
  className?: string
}

export function ScrollArea({ children, className = '' }: ScrollAreaProps) {
  return (
    <ScrollAreaPrimitive.Root className={`overflow-hidden ${className}`}>
      <ScrollAreaPrimitive.Viewport className="h-full w-full rounded-[inherit] overflow-x-hidden [&>div]:!block [&>div]:!min-w-0">
        {children}
      </ScrollAreaPrimitive.Viewport>
      <ScrollAreaPrimitive.Scrollbar
        orientation="vertical"
        className="flex w-2 touch-none select-none p-0.5 transition-colors hover:bg-neutral-200/60 dark:hover:bg-white/5"
      >
        <ScrollAreaPrimitive.Thumb className="relative flex-1 rounded-full bg-neutral-300 dark:bg-white/15 hover:bg-neutral-400 dark:hover:bg-white/25" />
      </ScrollAreaPrimitive.Scrollbar>
      <ScrollAreaPrimitive.Corner />
    </ScrollAreaPrimitive.Root>
  )
}
