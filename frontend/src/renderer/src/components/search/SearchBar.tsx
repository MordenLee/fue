import { useState } from 'react'
import { Search } from 'lucide-react'
import { Button } from '../ui/Button'
import { useI18n } from '../../i18n'

interface SearchBarProps {
  onSearch: (query: string) => void
  isSearching: boolean
}

export function SearchBar({ onSearch, isSearching }: SearchBarProps) {
  const { t } = useI18n()
  const [query, setQuery] = useState('')

  const handleSubmit = () => {
    if (query.trim()) onSearch(query.trim())
  }

  return (
    <div className="flex items-center gap-2 px-4 py-3">
      <div className="flex-1 relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-neutral-500" />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
          placeholder={t('search.input_placeholder')}
          className="w-full pl-10 pr-3 py-2 bg-white dark:bg-white/5 border border-neutral-200 dark:border-white/10 rounded-lg text-sm text-neutral-900 dark:text-neutral-200 placeholder-neutral-400 dark:placeholder-neutral-500 focus:outline-none focus:border-blue-500/50"
        />
      </div>
      <Button onClick={handleSubmit} disabled={!query.trim() || isSearching} loading={isSearching}>
        {t('search.search')}
      </Button>
    </div>
  )
}
