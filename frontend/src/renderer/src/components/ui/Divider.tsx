interface DividerProps {
  orientation?: 'horizontal' | 'vertical'
  className?: string
}

export function Divider({ orientation = 'horizontal', className = '' }: DividerProps) {
  return (
    <div
      className={`bg-white/10 shrink-0
        ${orientation === 'horizontal' ? 'h-px w-full' : 'w-px h-full'}
        ${className}`}
    />
  )
}
