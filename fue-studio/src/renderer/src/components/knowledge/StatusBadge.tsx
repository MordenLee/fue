import type { DocumentFileOut } from '../../types/knowledge'
import { useI18n } from '../../i18n'

interface StatusBadgeProps {
  status: DocumentFileOut['status']
  errorMessage?: string | null
}

const statusConfig: Record<DocumentFileOut['status'], { labelKey: string; className: string }> = {
  pending: { labelKey: 'status.pending', className: 'bg-neutral-200 text-neutral-600 dark:bg-neutral-500/20 dark:text-neutral-400' },
  parsing: { labelKey: 'status.processing', className: 'bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-400' },
  cleaning: { labelKey: 'status.processing', className: 'bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-400' },
  chunking: { labelKey: 'status.processing', className: 'bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-400' },
  embedding: { labelKey: 'status.processing', className: 'bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-400' },
  processing: { labelKey: 'status.processing', className: 'bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-400' },
  indexed: { labelKey: 'status.indexed', className: 'bg-green-100 text-green-700 dark:bg-green-500/20 dark:text-green-400' },
  failed: { labelKey: 'status.failed', className: 'bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-400' },
  cancelled: { labelKey: 'common.cancelled', className: 'bg-neutral-200 text-neutral-500 dark:bg-neutral-500/20 dark:text-neutral-400' },
}

const animatedStatuses = new Set<string>(['parsing', 'cleaning', 'chunking', 'embedding', 'processing'])

export function StatusBadge({ status, errorMessage }: StatusBadgeProps) {
  const { t } = useI18n()
  const config = statusConfig[status] ?? statusConfig.processing
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${config.className}`} title={status === 'failed' ? errorMessage ?? undefined : undefined}>
      {animatedStatuses.has(status) && (
        <span className="h-3 w-3 border-2 border-blue-600 dark:border-blue-400 border-t-transparent rounded-full animate-spin" />
      )}
      {t(config.labelKey)}
    </span>
  )
}
