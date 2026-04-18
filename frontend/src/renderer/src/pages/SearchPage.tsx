import { useState, useCallback, useEffect } from 'react'
import { Trash2, Plus, X } from 'lucide-react'
import { FolderListSidebar } from '../components/shared/FolderListSidebar'
import { SearchHeader } from '../components/search/SearchHeader'
import { SearchBar } from '../components/search/SearchBar'
import { SearchResultList } from '../components/search/SearchResultList'
import { ResizablePanel } from '../components/ui/ResizablePanel'
import { KBSelectionModal } from '../components/search/KBSelectionModal'
import { useKBSearch } from '../hooks/useKBSearch'
import { useFolders } from '../hooks/useFolders'
import { knowledgeService } from '../services/knowledge'
import { storageGet, storageSet, storageRemove } from '../utils/storage'
import type { SearchHistoryItem, SearchOptions } from '../types/search'
import type { KnowledgeBaseOut, SearchResult } from '../types/knowledge'
import { useI18n } from '../i18n'

function generateId() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2)
}

export function SearchPage() {
  const { language, t } = useI18n()
  const [history, setHistory] = useState<SearchHistoryItem[]>(() => storageGet<SearchHistoryItem[]>('search_history', []))
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [options, setOptions] = useState<SearchOptions>({ kbIds: [], searchType: 'semantic', topK: 5, rerank: true, diversity: false })
  const [hasSearched, setHasSearched] = useState(false)
  const { folders, createFolder, renameFolder, deleteFolder } = useFolders('search')

  const { results, isSearching, error, search, clear, loadCachedResults } = useKBSearch()

  // --- KB Management ---
  const [kbs, setKbs] = useState<KnowledgeBaseOut[]>([])
  const [kbModalOpen, setKbModalOpen] = useState(false)

  useEffect(() => {
    knowledgeService.list().then(setKbs).catch(console.error)
  }, [])

  const selectedKbs = kbs.filter(kb => options.kbIds.includes(kb.id))
  
  const removeKb = (id: number) => {
    setOptions(prev => ({ ...prev, kbIds: prev.kbIds.filter(x => x !== id) }))
  }
  // ---------------------

  const handleSearch = useCallback(async (query: string) => {
    const searchedResults = await search(query, options)
    setHasSearched(true)
    const item: SearchHistoryItem = {
      id: generateId(),
      query,
      kbIds: options.kbIds,
      searchType: options.searchType,
      topK: options.topK,
      rerank: options.rerank,
      diversity: options.diversity,
      resultCount: searchedResults?.length ?? 0,
      createdAt: new Date().toISOString(),
      folderId: null
    }
    // Cache the actual results separately, keyed by history item id
    if (searchedResults && searchedResults.length > 0) {
      storageSet(`search_results_${item.id}`, searchedResults)
    }
    setHistory((prev) => {
      const next = [item, ...prev]
      storageSet('search_history', next)
      return next
    })
    setSelectedId(item.id)
  }, [options, search])

  const handleSelectHistory = useCallback((item: SearchHistoryItem) => {
    setSelectedId(item.id)
    setOptions({ kbIds: item.kbIds, searchType: item.searchType, topK: item.topK, rerank: item.rerank, diversity: item.diversity ?? false })
    // Try to load cached results first; fall back to live search if not found
    const cached = storageGet<SearchResult[] | null>(`search_results_${item.id}`, null)
    if (cached && cached.length > 0) {
      loadCachedResults(cached)
    } else {
      search(item.query, { kbIds: item.kbIds, searchType: item.searchType, topK: item.topK, rerank: item.rerank, diversity: item.diversity ?? false })
    }
    setHasSearched(true)
  }, [search])

  const handleDelete = useCallback((id: string) => {
    setHistory((prev) => {
      const next = prev.filter((h) => h.id !== id)
      storageSet('search_history', next)
      return next
    })
    storageRemove(`search_results_${id}`)
    if (selectedId === id) {
      setSelectedId(null)
      clear()
      setHasSearched(false)
    }
  }, [selectedId, clear])

  const handleNew = useCallback(() => {
    setSelectedId(null)
    clear()
    setHasSearched(false)
  }, [clear])

  const handleOptionsChange = useCallback((patch: Partial<SearchOptions>) => {
    setOptions((prev) => ({ ...prev, ...patch }))
  }, [])

  return (
    <div className="flex h-full">
      <ResizablePanel defaultWidth={260} minWidth={200} maxWidth={400} storageKey="search_sidebar_width">
        <FolderListSidebar
          items={history}
          folders={folders}
          selectedId={selectedId}
          onSelect={handleSelectHistory}
          onCreateNew={handleNew}
          onSearch={() => {}}
          renderItem={(item) => (
            <div className="flex flex-col min-w-0">
              <span className="truncate">{item.query}</span>
              <span className="text-xs text-neutral-500">{new Date(item.createdAt).toLocaleDateString(language === 'en' ? 'en-US' : 'zh-CN')}</span>
            </div>
          )}
          title={t('nav.search')}
          createLabel={t('search.new_search')}
          searchPlaceholder={t('search.history_placeholder')}
          getItemFolder={(id) => history.find((h) => h.id === id)?.folderId ?? null}
          getContextMenuItems={(item) => [
            { label: t('common.delete'), icon: <Trash2 className="h-4 w-4" />, onClick: () => handleDelete(item.id), danger: true }
          ]}
          getFolderContextMenuItems={(folder) => [
            { label: t('common.rename'), onClick: () => renameFolder(folder.id, folder.name) },
            { label: t('common.delete_folder'), icon: <Trash2 className="h-4 w-4" />, onClick: () => deleteFolder(folder.id), danger: true }
          ]}
          onCreateFolder={() => createFolder(t('common.new_folder'))}
        />
      </ResizablePanel>

      <div className="flex-1 flex flex-col min-w-0">
        <SearchHeader options={options} onChange={handleOptionsChange} />
        
        <div className="flex flex-col border-b border-neutral-200 dark:border-white/10 pb-3 pt-2 bg-neutral-50 dark:bg-transparent">
          <SearchBar onSearch={handleSearch} isSearching={isSearching} />
          
          <div className="px-4 flex items-center gap-2 flex-wrap">
            <span className="text-xs text-neutral-500 mr-1">{t('search.searching_in')}</span>
            <button
              onClick={() => setKbModalOpen(true)}
              className="flex items-center gap-1 px-2 py-1 bg-white dark:bg-white/5 border border-dashed border-neutral-300 dark:border-neutral-600 rounded-full text-xs text-neutral-600 dark:text-neutral-300 hover:text-blue-600 hover:border-blue-400 transition"
            >
              <Plus className="w-3 h-3" />
              {t('search.select_kb')}
            </button>
            
            {options.kbIds.length === 0 ? (
              <span className="text-xs text-neutral-400 italic px-2 py-1 bg-neutral-100 dark:bg-white/5 rounded-full border border-transparent">
                {t('search.all_kbs')}
              </span>
            ) : (
              // Use slice or just horizontal scroll if too many
              <div className="flex items-center gap-2 flex-wrap max-w-full overflow-hidden">
                {selectedKbs.map((kb) => (
                  <div key={kb.id} className="flex items-center gap-1 px-2.5 py-1 bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-300 rounded-full border border-blue-200 dark:border-blue-500/20 text-xs shadow-sm">
                    <span className="truncate max-w-[120px]">{kb.name}</span>
                    <button
                      onClick={() => removeKb(kb.id)}
                      className="text-blue-400 hover:text-blue-600 dark:hover:text-blue-200 rounded-full p-0.5 hover:bg-blue-100 dark:hover:bg-blue-500/20"
                      title={t('common.delete')}
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                ))}
                {options.kbIds.length > 0 && (
                  <button
                    onClick={() => setOptions(prev => ({ ...prev, kbIds: [] }))}
                    className="text-xs text-neutral-400 hover:text-red-500 transition-colors ml-1"
                  >
                    {t('common.clear')}
                  </button>
                )}
              </div>
            )}
          </div>
        </div>

        <SearchResultList results={results} isSearching={isSearching} error={error} hasSearched={hasSearched} />
      </div>

      <KBSelectionModal
        open={kbModalOpen}
        onOpenChange={setKbModalOpen}
        kbs={kbs}
        selectedIds={options.kbIds}
        onChange={(ids) => setOptions(prev => ({ ...prev, kbIds: ids }))}
      />
    </div>
  )
}
