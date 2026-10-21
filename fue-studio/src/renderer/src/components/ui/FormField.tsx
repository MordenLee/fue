interface FormFieldProps {
  label: string
  description?: string
  error?: string
  children: React.ReactNode
  className?: string
}

export function FormField({ label, description, error, children, className = '' }: FormFieldProps) {
  return (
    <div className={`flex flex-col gap-1.5 ${className}`}>
      <label className="text-sm font-medium text-neutral-700 dark:text-neutral-300">{label}</label>
      {description && <p className="text-xs text-neutral-500 dark:text-neutral-500">{description}</p>}
      {children}
      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  )
}
