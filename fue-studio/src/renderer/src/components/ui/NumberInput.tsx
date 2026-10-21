import { type InputHTMLAttributes, forwardRef, useState } from 'react'

interface NumberInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'onChange' | 'type'> {
  value: number
  onChange: (value: number) => void
  min?: number
  max?: number
  step?: number
  label?: string
  fullWidth?: boolean
  hideButtons?: boolean
}

export const NumberInput = forwardRef<HTMLInputElement, NumberInputProps>(
  ({ value, onChange, min, max, step = 1, label, fullWidth, hideButtons = false, className = '', ...props }, ref) => {
    const [draft, setDraft] = useState<string | null>(null)
    void step
    void hideButtons

    const clamp = (n: number) => {
      if (min !== undefined && n < min) return min
      if (max !== undefined && n > max) return max
      return n
    }

    const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      const raw = e.target.value
      // Allow empty string while editing so user can clear and retype
      if (raw === '') {
        setDraft('')
        return
      }
      const allowNegative = (min !== undefined && min < 0) || (max !== undefined && max < 0)
      const pattern = allowNegative ? /^-?\d*$/ : /^\d*$/
      if (!pattern.test(raw)) return
      setDraft(raw)
      const n = Number(raw)
      if (!isNaN(n)) {
        onChange(clamp(n))
      }
    }

    const handleBlur = () => {
      // On blur, if draft is empty, reset to min or current value
      if (draft === '') {
        onChange(clamp(min ?? 0))
      }
      setDraft(null)
    }

    const displayValue = draft !== null ? draft : String(value)

    return (
      <div className={`flex flex-col gap-1 ${fullWidth ? 'w-full' : ''}`}>
        {label && <label className="text-sm text-neutral-400">{label}</label>}
        <div className={`${fullWidth ? 'w-full' : ''}`}>
          <input
            ref={ref}
            type="text"
            inputMode="numeric"
            value={displayValue}
            onChange={handleInputChange}
            onBlur={handleBlur}
            onFocus={() => setDraft(String(value))}
            className={`${fullWidth ? 'w-full min-w-0' : 'w-24'} rounded-lg border border-neutral-200 dark:border-white/10 bg-neutral-50 dark:bg-white/5 px-3 py-1.5 text-left text-sm
              text-neutral-900 dark:text-white
              focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none
              [&::-webkit-inner-spin-button]:appearance-none ${className}`}
            {...props}
          />
        </div>
      </div>
    )
  }
)
NumberInput.displayName = 'NumberInput'
