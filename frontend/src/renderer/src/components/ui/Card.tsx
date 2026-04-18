interface CardProps {
  title?: string
  actions?: React.ReactNode
  children: React.ReactNode
  className?: string
}

export function Card({ title, actions, children, className = '' }: CardProps) {
  return (
    <div className={`rounded-lg border border-white/10 bg-white/5 ${className}`}>
      {(title || actions) && (
        <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
          {title && <h3 className="text-sm font-medium text-white">{title}</h3>}
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className="p-4">{children}</div>
    </div>
  )
}
