import { MoreVertical, Trash2, Edit, Star, Eye, Brain, Wrench } from 'lucide-react'
import { Badge } from '../ui/Badge'
import { Switch } from '../ui/Switch'
import { DropdownMenu } from '../ui/DropdownMenu'
import { getModelLogo } from '../../utils/modelLogos'
import type { AIModelOut, Capability } from '../../types/provider'
import { useI18n } from '../../i18n'

const capabilityIcons: Record<Capability, { icon: React.ReactNode; color: string }> = {
  vision: { icon: <Eye className="h-3.5 w-3.5" />, color: 'text-blue-400' },
  reasoning: { icon: <Brain className="h-3.5 w-3.5" />, color: 'text-purple-400' },
  function_calling: { icon: <Wrench className="h-3.5 w-3.5" />, color: 'text-amber-400' },
}

interface ModelRowProps {
  model: AIModelOut
  onToggle: (enabled: boolean) => void
  onEdit: () => void
  onDelete: () => void
  onSetDefault: () => void
}

export function ModelRow({ model, onToggle, onEdit, onDelete, onSetDefault }: ModelRowProps) {
  const { t } = useI18n()

  return (
    <div className="flex items-center gap-3 px-4 py-2 hover:bg-neutral-100 dark:hover:bg-white/5 rounded-lg group">
      {getModelLogo(model.display_name || model.api_name) && (
        <span className="flex items-center justify-center h-6 w-6 shrink-0 rounded bg-neutral-200 dark:bg-neutral-700">
          <img src={getModelLogo(model.display_name || model.api_name)!} alt="" className="h-4 w-4" />
        </span>
      )}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm text-neutral-900 dark:text-neutral-200 truncate">{model.display_name || model.api_name}</span>
          <Badge variant={model.model_type === 'chat' ? 'primary' : model.model_type === 'embedding' ? 'success' : 'warning'}>
            {model.model_type}
          </Badge>
          {model.capabilities?.map((cap) => (
            <span key={cap} className={capabilityIcons[cap]?.color} title={cap}>
              {capabilityIcons[cap]?.icon}
            </span>
          ))}
          {model.is_default && (
            <span className="flex items-center gap-0.5 text-xs text-yellow-400">
              <Star className="h-3 w-3 fill-current" />
              {t('providers.default')}
            </span>
          )}
        </div>
        {model.api_name !== model.display_name && (
          <p className="text-xs text-neutral-500 truncate">{model.api_name}</p>
        )}
      </div>

      <Switch
        checked={model.is_enabled}
        onCheckedChange={onToggle}
      />

      <DropdownMenu
        trigger={
          <button className="p-1 rounded hover:bg-white/10 opacity-0 group-hover:opacity-100 transition-opacity">
            <MoreVertical className="h-4 w-4 text-neutral-400" />
          </button>
        }
        items={[
          { label: t('common.edit'), icon: <Edit className="h-4 w-4" />, onClick: onEdit },
          { label: t('providers.set_default'), icon: <Star className="h-4 w-4" />, onClick: onSetDefault },
          { label: t('common.delete'), icon: <Trash2 className="h-4 w-4" />, onClick: onDelete, danger: true }
        ]}
      />
    </div>
  )
}
