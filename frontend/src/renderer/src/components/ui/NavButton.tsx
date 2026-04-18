import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { Tooltip } from './Tooltip'

const base =
  'flex items-center justify-center w-10 h-10 rounded-lg transition-colors ' +
  'text-neutral-500 hover:text-neutral-900 hover:bg-black/5 ' +
  'dark:text-neutral-400 dark:hover:text-white dark:hover:bg-white/10'

const activeClass =
  'flex items-center justify-center w-10 h-10 rounded-lg transition-colors ' +
  'bg-blue-600/20 text-blue-600 dark:text-blue-400'

interface NavButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon: ReactNode
  tooltip: string
  isActive?: boolean
}

export const NavButton = forwardRef<HTMLButtonElement, NavButtonProps>(
  ({ icon, tooltip, isActive, className = '', ...props }, ref) => (
    <Tooltip content={tooltip} side="right">
      <button
        ref={ref}
        className={`${isActive ? activeClass : base} ${className}`}
        {...props}
      >
        {icon}
      </button>
    </Tooltip>
  )
)

NavButton.displayName = 'NavButton'
