import { type ButtonHTMLAttributes, forwardRef } from 'react'
import * as TooltipPrimitive from '@radix-ui/react-tooltip'

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  tooltip?: string
  size?: 'sm' | 'md' | 'lg'
}

const sizeClasses = {
  sm: 'h-7 w-7',
  md: 'h-8 w-8',
  lg: 'h-10 w-10'
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(
  ({ tooltip, size = 'md', className = '', children, ...props }, ref) => {
    const button = (
      <button
        ref={ref}
        className={`inline-flex items-center justify-center rounded-lg 
          text-gray-500 hover:text-black hover:bg-black/5 
          dark:text-neutral-400 dark:hover:text-white dark:hover:bg-white/10 
          transition disabled:opacity-50 disabled:cursor-not-allowed
          ${sizeClasses[size]} ${className}`}
        {...props}
      >
        {children}
      </button>
    )

    if (!tooltip) return button

    return (
      <TooltipPrimitive.Root>
        <TooltipPrimitive.Trigger asChild>{button}</TooltipPrimitive.Trigger>
        <TooltipPrimitive.Portal>
          <TooltipPrimitive.Content
            sideOffset={5}
            className="rounded-md bg-neutral-800 px-2.5 py-1.5 text-xs text-white shadow-lg
              animate-in fade-in-0 zoom-in-95 border border-white/10"
          >
            {tooltip}
            <TooltipPrimitive.Arrow className="fill-neutral-800" />
          </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
      </TooltipPrimitive.Root>
    )
  }
)
IconButton.displayName = 'IconButton'
