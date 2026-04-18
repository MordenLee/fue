import { useState, useEffect, type ReactNode } from 'react'
import { Plus, ChevronRight, ChevronDown, FolderPlus, GripVertical } from 'lucide-react'
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
  DragOverlay,
  type DragStartEvent,
  type DragEndEvent
} from '@dnd-kit/core'
import {
  SortableContext,
  useSortable,
  verticalListSortingStrategy
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { SearchInput } from '../ui/SearchInput'
import { Button } from '../ui/Button'
import { ContextMenu, type ContextMenuItem } from '../ui/ContextMenu'
import { ScrollArea } from '../ui/ScrollArea'
import type { Folder } from '../../types/folder'

interface FolderListSidebarProps<T extends { id: string | number }> {
  title?: string
  items: T[]
  folders: Folder[]
  selectedId: string | number | null
  onSelect: (item: T) => void
  onCreateNew: () => void
  onSearch: (query: string) => void
  renderItem: (item: T) => ReactNode
  createLabel: string
  searchPlaceholder: string
  getItemFolder: (itemId: string | number) => string | null
  getContextMenuItems: (item: T) => ContextMenuItem[]
  getFolderContextMenuItems: (folder: Folder) => ContextMenuItem[]
  onCreateFolder?: () => void
  headerActions?: ReactNode
  /** Called when an item is dropped onto a folder (or null to remove from folder) */
  onMoveToFolder?: (itemId: string | number, folderId: string | null) => void
  /** Called when unfoldered items are reordered */
  onReorder?: (activeId: string | number, overId: string | number) => void
}

/* ------------------------------------------------------------------ */
/* Draggable item (used both inside folders and in unfoldered list)    */
/* ------------------------------------------------------------------ */
function DraggableItem<T extends { id: string | number }>({
  item, selectedId, onSelect, renderItem, getContextMenuItems, indented
}: {
  item: T
  selectedId: string | number | null
  onSelect: (item: T) => void
  renderItem: (item: T) => ReactNode
  getContextMenuItems: (item: T) => ContextMenuItem[]
  indented?: boolean
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: item.id,
    data: { type: 'item', item }
  })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.3 : undefined,
    zIndex: isDragging ? 10 : undefined
  }

  return (
    <div ref={setNodeRef} style={style}>
      <ContextMenu items={getContextMenuItems(item)}>
        <button
          onClick={() => onSelect(item)}
          className={`flex w-full rounded-md ${indented ? 'pl-7 pr-2' : 'px-2'} py-2 text-left text-sm transition
            ${item.id === selectedId
              ? 'bg-blue-600/10 dark:bg-blue-600/20 text-blue-600 dark:text-blue-400'
              : 'text-neutral-700 dark:text-neutral-300 hover:bg-neutral-200/60 dark:hover:bg-white/5'}`}
        >
          <span
            {...attributes}
            {...listeners}
            className="flex items-center shrink-0 cursor-grab active:cursor-grabbing mr-1 text-neutral-400 dark:text-neutral-500"
            onClick={(e) => e.stopPropagation()}
          >
            <GripVertical className="h-3.5 w-3.5" />
          </span>
          <span className="flex-1 min-w-0">{renderItem(item)}</span>
        </button>
      </ContextMenu>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Folder drop zone (droppable target for items)                      */
/* ------------------------------------------------------------------ */
function DroppableFolder({
  folder, isExpanded, itemCount, onToggle, contextMenuItems, isOver, children
}: {
  folder: Folder
  isExpanded: boolean
  itemCount: number
  onToggle: () => void
  contextMenuItems: ContextMenuItem[]
  isOver: boolean
  children?: ReactNode
}) {
  const { setNodeRef } = useSortable({
    id: `folder:${folder.id}`,
    data: { type: 'folder', folderId: folder.id }
  })

  return (
    <div
      ref={setNodeRef}
      className={`rounded-md transition-colors ${isOver ? 'bg-blue-500/10 ring-1 ring-blue-500/30' : ''}`}
    >
      <ContextMenu items={contextMenuItems}>
        <button
          onClick={onToggle}
          className="flex items-center gap-2 w-full rounded-md px-2 py-1.5 text-sm
            text-neutral-500 dark:text-neutral-400 hover:bg-neutral-200/60 dark:hover:bg-white/5 transition"
        >
          {isExpanded
            ? <ChevronDown className="h-3.5 w-3.5 shrink-0" />
            : <ChevronRight className="h-3.5 w-3.5 shrink-0" />
          }
          <span className="truncate font-medium">{folder.name}</span>
          <span className="ml-auto text-xs text-neutral-600">{itemCount}</span>
        </button>
      </ContextMenu>
      {isExpanded && children}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Static item renderer (used inside DragOverlay)                     */
/* ------------------------------------------------------------------ */
function StaticItemView<T extends { id: string | number }>({
  item, renderItem
}: { item: T; renderItem: (item: T) => ReactNode }) {
  return (
    <div className="flex w-full rounded-md px-2 py-2 text-left text-sm bg-neutral-800 border border-white/10 shadow-xl text-neutral-300">
      <GripVertical className="h-3.5 w-3.5 mr-1 shrink-0 text-neutral-500" />
      <span className="flex-1 min-w-0">{renderItem(item)}</span>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Main component                                                     */
/* ------------------------------------------------------------------ */
export function FolderListSidebar<T extends { id: string | number }>({
  title, items, folders, selectedId, onSelect, onCreateNew, onSearch,
  renderItem, createLabel, searchPlaceholder,
  getItemFolder, getContextMenuItems, getFolderContextMenuItems,
  onCreateFolder, headerActions, onMoveToFolder, onReorder
}: FolderListSidebarProps<T>) {
  const [search, setSearch] = useState('')
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(() => new Set(folders.map((f) => f.id)))
  const [activeId, setActiveId] = useState<string | number | null>(null)
  const [overFolderId, setOverFolderId] = useState<string | null>(null)

  // Keep expandedFolders in sync when new folders appear
  useEffect(() => {
    setExpandedFolders((prev) => {
      const next = new Set(prev)
      for (const f of folders) {
        if (!next.has(f.id)) next.add(f.id)
      }
      return next
    })
  }, [folders])

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } })
  )

  const handleSearch = (q: string) => {
    setSearch(q)
    onSearch(q)
  }

  const toggleFolder = (id: string) => {
    setExpandedFolders((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  // Build item groups
  const folderedItems = new Map<string, T[]>()
  const unfolderedItems: T[] = []

  for (const item of items) {
    const folderId = getItemFolder(item.id)
    if (folderId) {
      const arr = folderedItems.get(folderId) ?? []
      arr.push(item)
      folderedItems.set(folderId, arr)
    } else {
      unfolderedItems.push(item)
    }
  }

  // All item ids for the single SortableContext
  const allSortableIds: (string | number)[] = []
  for (const folder of folders) {
    allSortableIds.push(`folder:${folder.id}`)
    const fi = folderedItems.get(folder.id) ?? []
    for (const item of fi) allSortableIds.push(item.id)
  }
  for (const item of unfolderedItems) allSortableIds.push(item.id)

  const activeItem = activeId !== null ? items.find((i) => i.id === activeId) : undefined

  const handleDragStart = (event: DragStartEvent) => {
    const data = event.active.data.current
    if (data?.type === 'item') {
      setActiveId(event.active.id)
    }
  }

  const handleDragOver = (event: { over: { id: string | number; data: { current?: { type?: string; folderId?: string } } } | null }) => {
    const over = event.over
    if (!over) {
      setOverFolderId(null)
      return
    }
    const overData = over.data.current
    if (overData?.type === 'folder') {
      setOverFolderId(overData.folderId ?? null)
    } else {
      // Check if over-item is inside a folder
      const overItemFolderId = typeof over.id === 'string' || typeof over.id === 'number'
        ? getItemFolder(over.id)
        : null
      setOverFolderId(overItemFolderId)
    }
  }

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    setActiveId(null)
    setOverFolderId(null)

    if (!over || active.id === over.id) return

    const activeData = active.data.current
    if (activeData?.type !== 'item') return

    const overData = over.data.current

    // Case 1: Dropped onto a folder header → move item into that folder
    if (overData?.type === 'folder' && onMoveToFolder) {
      onMoveToFolder(active.id, overData.folderId)
      return
    }

    // Case 2: Dropped onto another item
    const draggedFolderId = getItemFolder(active.id)
    const targetFolderId = getItemFolder(over.id)

    // If target is in a folder, move dragged item into that folder
    if (targetFolderId && targetFolderId !== draggedFolderId && onMoveToFolder) {
      onMoveToFolder(active.id, targetFolderId)
      return
    }

    // If both are unfoldered → reorder
    if (!draggedFolderId && !targetFolderId && onReorder) {
      onReorder(active.id, over.id)
      return
    }

    // If dragged from folder to unfoldered area → remove from folder
    if (draggedFolderId && !targetFolderId && onMoveToFolder) {
      onMoveToFolder(active.id, null)
      return
    }
  }

  const handleDragCancel = () => {
    setActiveId(null)
    setOverFolderId(null)
  }

  return (
    <div className="flex flex-col h-full w-full bg-neutral-50 dark:bg-neutral-900/50">
      {/* Header */}
      <div className="shrink-0 px-3 pt-4 pb-3 flex flex-col gap-3">
        {title && (
          <div className="flex items-center justify-between px-1">
            <h2 className="text-base font-semibold text-neutral-800 dark:text-neutral-100">{title}</h2>
            {headerActions}
          </div>
        )}
        <div className="flex items-center gap-2">
          <Button size="md" onClick={onCreateNew} className="flex-1">
            <Plus className="h-4 w-4" />
            {createLabel}
          </Button>
          {onCreateFolder && (
            <Button size="md" variant="ghost" onClick={onCreateFolder}>
              <FolderPlus className="h-4 w-4" />
            </Button>
          )}
        </div>
        <SearchInput value={search} onChange={handleSearch} placeholder={searchPlaceholder} />
      </div>

      {/* List */}
      <ScrollArea className="flex-1">
        <div className="p-2 flex flex-col gap-1">
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragStart={handleDragStart}
            onDragOver={handleDragOver}
            onDragEnd={handleDragEnd}
            onDragCancel={handleDragCancel}
          >
            <SortableContext items={allSortableIds} strategy={verticalListSortingStrategy}>
              {/* Folders */}
              {folders.map((folder) => {
                const folderItems = folderedItems.get(folder.id) ?? []
                const isExpanded = expandedFolders.has(folder.id)

                return (
                  <DroppableFolder
                    key={folder.id}
                    folder={folder}
                    isExpanded={isExpanded}
                    itemCount={folderItems.length}
                    onToggle={() => toggleFolder(folder.id)}
                    contextMenuItems={getFolderContextMenuItems(folder)}
                    isOver={overFolderId === folder.id}
                  >
                    {folderItems.map((item) => (
                      <DraggableItem
                        key={item.id}
                        item={item}
                        selectedId={selectedId}
                        onSelect={onSelect}
                        renderItem={renderItem}
                        getContextMenuItems={getContextMenuItems}
                        indented
                      />
                    ))}
                  </DroppableFolder>
                )
              })}

              {/* Unfoldered items */}
              {unfolderedItems.map((item) => (
                <DraggableItem
                  key={item.id}
                  item={item}
                  selectedId={selectedId}
                  onSelect={onSelect}
                  renderItem={renderItem}
                  getContextMenuItems={getContextMenuItems}
                />
              ))}
            </SortableContext>

            <DragOverlay dropAnimation={null}>
              {activeItem ? (
                <StaticItemView item={activeItem} renderItem={renderItem} />
              ) : null}
            </DragOverlay>
          </DndContext>
        </div>
      </ScrollArea>
    </div>
  )
}
