interface ProgressBarProps {
  value?: number // 0-100, undefined = indeterminate
  className?: string
}

export function ProgressBar({ value, className = '' }: ProgressBarProps) {
  const indeterminate = value === undefined

  return (
    <div className={`h-1.5 w-full rounded-full bg-white/10 overflow-hidden ${className}`}>
      <div
        className={`h-full rounded-full bg-blue-500 transition-all duration-300
          ${indeterminate ? 'w-1/3 animate-[indeterminate_1.5s_ease-in-out_infinite]' : ''}`}
        style={indeterminate ? undefined : { width: `${Math.min(100, Math.max(0, value))}%` }}
      />
    </div>
  )
}
