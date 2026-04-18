import { type ButtonHTMLAttributes, forwardRef } from 'react'
import { Loader2 } from 'lucide-react'

const variants = {
  primary: 'bg-blue-600 text-white hover:bg-blue-500 disabled:bg-blue-600/50',
  secondary: 'bg-gray-200 text-gray-900 hover:bg-gray-300 dark:bg-neutral-700 dark:text-white dark:hover:bg-neutral-600 disabled:opacity-50',
  danger: 'bg-red-600 text-white hover:bg-red-500 disabled:bg-red-600/50',
  ghost: 'text-gray-600 hover:bg-black/5 dark:text-neutral-300 dark:hover:bg-white/10 disabled:opacity-50',
  icon: 'text-gray-500 hover:text-black hover:bg-black/5 dark:text-neutral-400 dark:hover:text-white dark:hover:bg-white/10 p-2'
}

const sizes = {
  sm: 'px-2.5 py-1 text-xs',
  md: 'px-4 py-2 text-sm',
  lg: 'px-6 py-2.5 text-base'
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: keyof typeof variants
  size?: keyof typeof sizes
  loading?: boolean
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = 'primary', size = 'md', loading, children, className = '', disabled, ...props }, ref) => (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={`inline-flex items-center justify-center gap-2 rounded-lg font-medium transition
        ${variants[variant]} ${variant !== 'icon' ? sizes[size] : ''} ${className}
        disabled:cursor-not-allowed`}
      {...props}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" />}
      {children}
    </button>
  )
)
Button.displayName = 'Button'
