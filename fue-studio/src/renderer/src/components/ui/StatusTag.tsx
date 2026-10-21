import { useI18n } from '../../i18n'

const statusConfig = {
  pending: { labelKey: 'status.pending', className: 'bg-neutral-500/20 text-neutral-400' },
  processing: { labelKey: 'status.processing', className: 'bg-blue-500/20 text-blue-400' },
  indexed: { labelKey: 'status.indexed', className: 'bg-green-500/20 text-green-400' },
  failed: { labelKey: 'status.failed', className: 'bg-red-500/20 text-red-400' },
  success: { labelKey: 'common.success', className: 'bg-green-500/20 text-green-400' },
  warning: { labelKey: 'common.warning', className: 'bg-yellow-500/20 text-yellow-400' },
  info: { labelKey: 'common.info', className: 'bg-blue-500/20 text-blue-400' },
  neutral: { labelKey: 'common.neutral', className: 'bg-white/10 text-neutral-400' }
}

interface StatusTagProps {
  status: keyof typeof statusConfig
  label?: string
  className?: string
}

export function StatusTag({ status, label, className = '' }: StatusTagProps) {
  const { t } = useI18n()
  const config = statusConfig[status]
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium
      ${config.className} ${className}`}>
      {status === 'processing' && (
        <span className="h-1.5 w-1.5 rounded-full bg-current animate-pulse" />
      )}
      {label ?? t(config.labelKey)}
    </span>
  )
}
