import type { InterfaceType } from '../../types/provider'

const providerIcons: Record<InterfaceType, string> = {
  openai: '🟢',
  anthropic: '🟠',
  google: '🔵',
  ollama: '⚪',
  openai_compatible: '🟣',
  cohere: '🔴',
  jina: '🟡'
}

interface ProviderBadgeProps {
  interfaceType: InterfaceType
  name: string
  className?: string
}

export function ProviderBadge({ interfaceType, name, className = '' }: ProviderBadgeProps) {
  return (
    <span className={`inline-flex items-center gap-1.5 text-sm text-neutral-300 ${className}`}>
      <span>{providerIcons[interfaceType] ?? '⚪'}</span>
      <span>{name}</span>
    </span>
  )
}
