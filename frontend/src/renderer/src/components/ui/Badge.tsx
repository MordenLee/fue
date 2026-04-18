interface BadgeProps {
  children: React.ReactNode
  variant?: 'default' | 'primary' | 'success' | 'warning' | 'danger'
  className?: string
}

const variants = {
  default: 'bg-white/10 text-neutral-300',
  primary: 'bg-blue-600/20 text-blue-400',
  success: 'bg-green-600/20 text-green-400',
  warning: 'bg-yellow-600/20 text-yellow-400',
  danger: 'bg-red-600/20 text-red-400'
}

export function Badge({ children, variant = 'default', className = '' }: BadgeProps) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${variants[variant]} ${className}`}>
      {children}
    </span>
  )
}
