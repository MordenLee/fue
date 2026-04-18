import * as SelectPrimitive from '@radix-ui/react-select'
import { ChevronDown, Check } from 'lucide-react'

export interface SelectOption {
  value: string
  label: string
  group?: string
}

interface SelectProps {
  value: string
  onValueChange: (value: string) => void
  options: SelectOption[]
  placeholder?: string
  label?: string
  disabled?: boolean
  className?: string
}

export function Select({ value, onValueChange, options, placeholder, label, disabled, className = '' }: SelectProps) {
  const groups = new Map<string, SelectOption[]>()
  const ungrouped: SelectOption[] = []
  for (const opt of options) {
    if (opt.group) {
      const arr = groups.get(opt.group) ?? []
      arr.push(opt)
      groups.set(opt.group, arr)
    } else {
      ungrouped.push(opt)
    }
  }

  return (
    <div className="flex flex-col gap-1">
      {label && <label className="text-sm text-neutral-600 dark:text-neutral-400">{label}</label>}
      <SelectPrimitive.Root value={value} onValueChange={onValueChange} disabled={disabled}>
        <SelectPrimitive.Trigger
          className={`inline-flex items-center justify-between rounded-lg border
            border-neutral-200 dark:border-white/10 bg-white dark:bg-white/5
            px-3 py-2 text-sm text-neutral-900 dark:text-white
            hover:bg-neutral-50 dark:hover:bg-white/10 transition
            focus:border-blue-500 focus:outline-none disabled:opacity-50 ${className}`}
        >
          <SelectPrimitive.Value placeholder={placeholder} />
          <SelectPrimitive.Icon>
            <ChevronDown className="h-4 w-4 text-neutral-400" />
          </SelectPrimitive.Icon>
        </SelectPrimitive.Trigger>
        <SelectPrimitive.Portal>
          <SelectPrimitive.Content
            className="overflow-hidden rounded-lg border border-neutral-200 dark:border-white/10 bg-white dark:bg-neutral-800 shadow-xl z-50"
            position="popper"
            sideOffset={4}
          >
            <SelectPrimitive.Viewport className="p-1">
              {ungrouped.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
              ))}
              {[...groups.entries()].map(([group, opts]) => (
                <SelectPrimitive.Group key={group}>
                  <SelectPrimitive.Label className="px-3 py-1.5 text-xs text-neutral-500">
                    {group}
                  </SelectPrimitive.Label>
                  {opts.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                  ))}
                </SelectPrimitive.Group>
              ))}
            </SelectPrimitive.Viewport>
          </SelectPrimitive.Content>
        </SelectPrimitive.Portal>
      </SelectPrimitive.Root>
    </div>
  )
}

function SelectItem({ children, value }: { children: React.ReactNode; value: string }) {
  return (
    <SelectPrimitive.Item
      value={value}
      className="relative flex items-center rounded-md px-3 py-1.5 text-sm
        text-neutral-800 dark:text-white
        cursor-pointer select-none hover:bg-neutral-100 dark:hover:bg-white/10
        focus:bg-neutral-100 dark:focus:bg-white/10 outline-none
        data-[disabled]:opacity-50 data-[disabled]:pointer-events-none"
    >
      <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
      <SelectPrimitive.ItemIndicator className="absolute right-2">
        <Check className="h-4 w-4" />
      </SelectPrimitive.ItemIndicator>
    </SelectPrimitive.Item>
  )
}
