import * as SwitchPrimitive from '@radix-ui/react-switch'

interface SwitchProps {
  checked: boolean
  onCheckedChange: (checked: boolean) => void
  label?: string
  disabled?: boolean
}

export function Switch({ checked, onCheckedChange, label, disabled }: SwitchProps) {
  return (
    <div className="flex items-center gap-2">
      <SwitchPrimitive.Root
        checked={checked}
        onCheckedChange={onCheckedChange}
        disabled={disabled}
        className="relative h-5 w-9 shrink-0 rounded-full bg-neutral-300 dark:bg-neutral-600 transition
          data-[state=checked]:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <SwitchPrimitive.Thumb
          className="block h-4 w-4 rounded-full bg-white transition-transform
            data-[state=checked]:translate-x-4 translate-x-0.5"
        />
      </SwitchPrimitive.Root>
      {label && <span className="text-sm text-neutral-300">{label}</span>}
    </div>
  )
}
