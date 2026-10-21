import { useEffect, useRef, useState } from 'react'
import { Search, X } from 'lucide-react'
import { useI18n } from '../../i18n'

interface SearchInputProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  debounceMs?: number
  className?: string
}

export function SearchInput({ value, onChange, placeholder, debounceMs = 300, className = '' }: SearchInputProps) {
  const { t } = useI18n()
  const [local, setLocal] = useState(value)
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined)

  useEffect(() => { setLocal(value) }, [value])

  const handleChange = (v: string) => {
    setLocal(v)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => onChange(v), debounceMs)
  }

  return (
    <div className={`relative flex items-center ${className}`}>
      <Search className="absolute left-2.5 h-4 w-4 text-neutral-500" />
      <input
        value={local}
        onChange={(e) => handleChange(e.target.value)}
        placeholder={placeholder ?? t('common.search')}
        className="w-full rounded-lg border border-neutral-200 dark:border-white/10 bg-white dark:bg-white/5 pl-9 pr-8 py-1.5 text-sm text-neutral-900 dark:text-white
          placeholder:text-neutral-400 dark:placeholder:text-neutral-500 focus:border-blue-500 focus:outline-none transition"
      />
      {local && (
        <button
          onClick={() => handleChange('')}
          className="absolute right-2.5 text-neutral-500 hover:text-white"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  )
}
