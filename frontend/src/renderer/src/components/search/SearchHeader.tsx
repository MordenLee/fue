import { HelpCircle } from 'lucide-react'
import { Select } from '../ui/Select'
import { Switch } from '../ui/Switch'
import { Tooltip } from '../ui/Tooltip'
import type { SearchOptions } from '../../types/search'
import { useI18n } from '../../i18n'

interface SearchHeaderProps {
  options: SearchOptions
  onChange: (opts: Partial<SearchOptions>) => void
}

export function SearchHeader({ options, onChange }: SearchHeaderProps) {
  const { t } = useI18n()

  return (
    <div className="flex items-center gap-5 px-4 py-2.5 border-b border-neutral-200 dark:border-white/10 flex-wrap">
      <div className="flex items-center gap-2">
        <span className="text-xs text-neutral-500 dark:text-neutral-400 shrink-0">{t('search.search_type')}</span>
        <Select
          value={options.searchType}
          onValueChange={(v) => onChange({ searchType: v as 'semantic' | 'keyword' })}
          options={[
            { label: t('search.type_semantic'), value: 'semantic' },
            { label: t('search.type_keyword'), value: 'keyword' }
          ]}
        />
      </div>

      <div className="flex items-center gap-2">
        <Tooltip content={t('search.top_k_desc')} side="bottom">
          <div className="flex items-center gap-1 cursor-default">
            <span className="text-xs text-neutral-500 dark:text-neutral-400 shrink-0">{t('search.top_k')}</span>
            <HelpCircle className="w-3 h-3 text-neutral-400 dark:text-neutral-500" />
          </div>
        </Tooltip>
        <input
          type="number"
          value={options.topK}
          onChange={(e) => {
            const val = parseInt(e.target.value)
            if (!isNaN(val) && val > 0) onChange({ topK: val })
          }}
          onBlur={(e) => {
            const val = parseInt(e.target.value)
            if (isNaN(val) || val < 1) onChange({ topK: 5 })
          }}
          min={1}
          max={50}
          className="w-14 h-7 px-2 text-center text-xs border border-neutral-200 dark:border-white/10 rounded-md bg-white dark:bg-white/5 text-neutral-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-blue-500 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
        />
      </div>

      <div className="flex items-center gap-1.5">
        <Tooltip content={t('search.rerank_desc')} side="bottom">
          <div className="flex items-center gap-1 cursor-default">
            <span className="text-xs text-neutral-500 dark:text-neutral-400 shrink-0">{t('search.rerank')}</span>
            <HelpCircle className="w-3 h-3 text-neutral-400 dark:text-neutral-500" />
          </div>
        </Tooltip>
        <Switch checked={options.rerank} onCheckedChange={(rerank) => onChange({ rerank })} />
      </div>

      <div className="flex items-center gap-1.5">
        <Tooltip content={t('search.diversity_desc')} side="bottom">
          <div className="flex items-center gap-1 cursor-default">
            <span className="text-xs text-neutral-500 dark:text-neutral-400 shrink-0">{t('search.diversity')}</span>
            <HelpCircle className="w-3 h-3 text-neutral-400 dark:text-neutral-500" />
          </div>
        </Tooltip>
        <Switch checked={options.diversity} onCheckedChange={(diversity) => onChange({ diversity })} />
      </div>
    </div>
  )
}
