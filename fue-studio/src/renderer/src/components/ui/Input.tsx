import { type InputHTMLAttributes, forwardRef } from 'react'
import { X } from 'lucide-react'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
  prefixIcon?: React.ReactNode
  suffixIcon?: React.ReactNode
  clearable?: boolean
  onClear?: () => void
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, prefixIcon, suffixIcon, clearable, onClear, className = '', ...props }, ref) => (
    <div className="flex flex-col gap-1">
      {label && <label className="text-sm text-neutral-400">{label}</label>}
      <div className="relative flex items-center">
        {prefixIcon && (
          <span className="absolute left-2.5 text-neutral-500">{prefixIcon}</span>
        )}
        <input
          ref={ref}
          className={`w-full rounded-lg border border-neutral-200 dark:border-white/10 bg-neutral-50 dark:bg-white/5 px-3 py-1.5 text-sm text-neutral-900 dark:text-white
            placeholder:text-neutral-400 dark:placeholder:text-neutral-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500
            transition disabled:opacity-50
            ${prefixIcon ? 'pl-9' : ''} ${suffixIcon || clearable ? 'pr-9' : ''}
            ${error ? 'border-red-500' : ''} ${className}`}
          {...props}
        />
        {clearable && props.value && (
          <button
            type="button"
            onClick={onClear}
            className="absolute right-2.5 text-neutral-500 hover:text-white"
          >
            <X className="h-4 w-4" />
          </button>
        )}
        {suffixIcon && !clearable && (
          <span className="absolute right-2.5 text-neutral-500">{suffixIcon}</span>
        )}
      </div>
      {error && <span className="text-xs text-red-400">{error}</span>}
    </div>
  )
)
Input.displayName = 'Input'
