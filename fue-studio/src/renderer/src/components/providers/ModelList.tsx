import { Plus } from 'lucide-react'
import { Button } from '../ui/Button'
import { ModelRow } from './ModelRow'
import type { AIModelOut } from '../../types/provider'
import { useI18n } from '../../i18n'

interface ModelListProps {
  models: AIModelOut[]
  onAdd: () => void
  onToggle: (id: number, enabled: boolean) => void
  onEdit: (model: AIModelOut) => void
  onDelete: (id: number) => void
  onSetDefault: (id: number) => void
}

export function ModelList({ models, onAdd, onToggle, onEdit, onDelete, onSetDefault }: ModelListProps) {
  const { t } = useI18n()

  // Group by series
  const groups = new Map<string, AIModelOut[]>()
  for (const m of models) {
    const key = m.series || t('providers.uncategorized')
    const arr = groups.get(key) ?? []
    arr.push(m)
    groups.set(key, arr)
  }

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="flex items-center gap-2 px-6 py-3 border-b border-white/10">
        <Button size="sm" onClick={onAdd}>
          <Plus className="h-4 w-4 mr-1" />
          {t('providers.add_model')}
        </Button>
      </div>
      <div className="flex-1 overflow-y-auto px-2 py-2">
        {models.length === 0 ? (
          <p className="text-sm text-neutral-500 text-center py-8">{t('providers.no_model_hint')}</p>
        ) : (
          Array.from(groups.entries()).map(([series, seriesModels]) => (
            <div key={series} className="mb-3">
              <h4 className="text-xs text-neutral-500 font-medium px-4 py-1">── {series} ──</h4>
              {seriesModels.map((model) => (
                <ModelRow
                  key={model.id}
                  model={model}
                  onToggle={(enabled) => onToggle(model.id, enabled)}
                  onEdit={() => onEdit(model)}
                  onDelete={() => onDelete(model.id)}
                  onSetDefault={() => onSetDefault(model.id)}
                />
              ))}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
