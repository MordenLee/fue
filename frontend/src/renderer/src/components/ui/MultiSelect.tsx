import { useState, useRef } from 'react'
import { X, ChevronDown } from 'lucide-react'

interface MultiSelectOption {
  value: string
  label: string
}

interface MultiSelectProps {
  options: MultiSelectOption[]
  value: string[]
  onChange: (value: string[]) => void
  placeholder?: string
  label?: string
  disabled?: boolean
}

export function MultiSelect({ options, value, onChange, placeholder, label, disabled }: MultiSelectProps) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  const selectedLabels = value.map((v) => options.find((o) => o.value === v)?.label ?? v)

  const toggle = (val: string) => {
    onChange(value.includes(val) ? value.filter((v) => v !== val) : [...value, val])
  }

  return (
    <div className="flex flex-col gap-1" ref={containerRef}>
      {label && <label className="text-sm text-neutral-400">{label}</label>}
      <div className="relative">
        <button
          type="button"
          disabled={disabled}
          onClick={() => setOpen(!open)}
          className="flex w-full items-center justify-between gap-2 rounded-lg border border-white/10
            bg-white/5 px-3 py-2 text-sm text-white hover:bg-white/10 transition
            focus:border-blue-500 focus:outline-none disabled:opacity-50"
        >
          <div className="flex flex-wrap gap-1 flex-1 min-w-0">
            {selectedLabels.length > 0 ? (
              selectedLabels.map((lbl, i) => (
                <span
                  key={value[i]}
                  className="inline-flex items-center gap-1 rounded bg-blue-600/30 px-1.5 py-0.5 text-xs"
                >
                  {lbl}
                  <X
                    className="h-3 w-3 cursor-pointer hover:text-red-400"
                    onClick={(e) => { e.stopPropagation(); toggle(value[i]) }}
                  />
                </span>
              ))
            ) : (
              <span className="text-neutral-500">{placeholder}</span>
            )}
          </div>
          <ChevronDown className="h-4 w-4 shrink-0 text-neutral-400" />
        </button>

        {open && (
          <>
            <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
            <div className="absolute top-full left-0 z-50 mt-1 w-full rounded-lg border border-white/10
              bg-neutral-800 shadow-xl p-1 max-h-60 overflow-y-auto">
              {options.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => toggle(opt.value)}
                  className={`flex w-full items-center gap-2 rounded-md px-3 py-1.5 text-sm text-left
                    hover:bg-white/10 transition ${value.includes(opt.value) ? 'text-blue-400' : 'text-white'}`}
                >
                  <div
                    className={`h-4 w-4 shrink-0 rounded border flex items-center justify-center
                      ${value.includes(opt.value) ? 'bg-blue-600 border-blue-600' : 'border-white/20'}`}
                  >
                    {value.includes(opt.value) && <span className="text-xs text-white">✓</span>}
                  </div>
                  {opt.label}
                </button>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
