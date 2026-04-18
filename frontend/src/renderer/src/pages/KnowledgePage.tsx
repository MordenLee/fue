import { useState, useCallback } from 'react'
import { Database, Pencil, Trash2, FolderInput } from 'lucide-react'
import { FolderListSidebar } from '../components/shared/FolderListSidebar'
import { RenameDialog } from '../components/shared/RenameDialog'
import { MoveFolderDialog } from '../components/shared/MoveFolderDialog'
import { KBInfoPanel } from '../components/knowledge/KBInfoPanel'
import { KBCreateForm } from '../components/knowledge/KBCreateForm'
import { DocumentTable } from '../components/knowledge/DocumentTable'
import { DocumentDetail } from '../components/knowledge/DocumentDetail'
import { CitationForm } from '../components/knowledge/CitationForm'
import { DuplicateFilesDialog, type DuplicateAction } from '../components/knowledge/DuplicateFilesDialog'
import { ResizablePanel } from '../components/ui/ResizablePanel'
import { EmptyState } from '../components/ui/EmptyState'
import { ConfirmDialog } from '../components/ui/ConfirmDialog'
import { FormModal } from '../components/ui/FormModal'
import { FormField } from '../components/ui/FormField'
import { Input } from '../components/ui/Input'
import { Textarea } from '../components/ui/Textarea'
import { useKnowledgeBases } from '../hooks/useKnowledgeBases'
import { useDocuments } from '../hooks/useDocuments'
import { useFolders } from '../hooks/useFolders'
import { useToast } from '../contexts/ToastContext'
import { citationsService } from '../services/citations'
import { knowledgeService } from '../services/knowledge'
import type { DocumentFileOut, CitationCreate } from '../types/knowledge'
import { useI18n } from '../i18n'

export function KnowledgePage() {
  const { knowledgeBases, create, update, remove } = useKnowledgeBases()
  const { folders, createFolder, renameFolder, deleteFolder } = useFolders('knowledge')
  const toast = useToast()
  const { t } = useI18n()

  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [showEdit, setShowEdit] = useState(false)
  const [selectedDocId, setSelectedDocId] = useState<number | null>(null)
  const [deleteConfirm, setDeleteConfirm] = useState<{ type: 'kb' | 'doc'; id: number } | null>(null)
  const [citationDoc, setCitationDoc] = useState<DocumentFileOut | null>(null)
  const [citationInitialData, setCitationInitialData] = useState<import('../types/knowledge').CitationOut | null>(null)
  const [citationVersion, setCitationVersion] = useState(0)
  const [dupDialog, setDupDialog] = useState<{ paths: string[]; duplicates: string[] } | null>(null)

  // Rename / move-to-folder dialog state
  const [movingKBId, setMovingKBId] = useState<number | null>(null)
  const [renamingFolder, setRenamingFolder] = useState<import('../types/folder').Folder | null>(null)

  const { documents, loading: docsLoading, load, addBatch, reindex, remove: removeDoc, batchDelete, batchReindex, batchMatchText, cancel } = useDocuments(selectedId)

  const selected = knowledgeBases.find((k) => k.id === selectedId)
  const selectedDoc = documents.find((d) => d.id === selectedDocId)

  const handleExport = useCallback(async () => {
    if (!selectedId) return
    try {
      const blob = await knowledgeService.exportKB(selectedId)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `kb_${selectedId}_export.json`
      a.click()
      URL.revokeObjectURL(url)
      toast.success(t('knowledge.export_success'))
    } catch {
      toast.error(t('knowledge.export_failed'))
    }
  }, [selectedId, toast, t])

  const handleAddDocs = useCallback(async () => {
    try {
      const paths = await window.api.openFileDialog({
        title: t('knowledge.select_docs'),
        filters: [{ name: t('knowledge.documents_filter_name'), extensions: ['pdf', 'md', 'txt', 'docx', 'html'] }]
      })
      if (!paths.length) return

      // Check for duplicates against existing documents
      const existingNames = new Set(documents.map((d) => d.original_filename))
      const selectedNames = paths.map((p) => p.replace(/\\/g, '/').split('/').pop()!)
      const duplicates = selectedNames.filter((name) => existingNames.has(name))

      if (duplicates.length > 0) {
        setDupDialog({ paths, duplicates })
        return
      }

      await addBatch(paths)
      toast.success(t('knowledge.added_n_files', { count: paths.length }))
    } catch {
      toast.error(t('knowledge.add_doc_failed'))
    }
  }, [addBatch, documents, toast, t])

  const handleDuplicateAction = useCallback(async (action: DuplicateAction) => {
    if (!dupDialog) return
    setDupDialog(null)
    try {
      await addBatch(dupDialog.paths, action)
      toast.success(t('knowledge.added_files'))
    } catch {
      toast.error(t('knowledge.add_doc_failed'))
    }
  }, [dupDialog, addBatch, toast, t])

  const handleDeleteConfirm = useCallback(async () => {
    if (!deleteConfirm) return
    try {
      if (deleteConfirm.type === 'kb') {
        await remove(deleteConfirm.id)
        if (selectedId === deleteConfirm.id) setSelectedId(null)
        toast.success(t('knowledge.deleted_kb'))
      } else {
        await removeDoc(deleteConfirm.id)
        if (selectedDocId === deleteConfirm.id) setSelectedDocId(null)
        toast.success(t('knowledge.deleted_doc'))
      }
    } catch {
      toast.error(t('common.delete_failed'))
    }
    setDeleteConfirm(null)
  }, [deleteConfirm, remove, removeDoc, selectedId, selectedDocId, toast, t])

  const handleCitationSubmit = useCallback(async (data: CitationCreate) => {
    if (!selectedId || !citationDoc) return
    try {
      await citationsService.upsert(selectedId, citationDoc.id, data)
      toast.success(t('knowledge.citation_saved'))
      setCitationDoc(null)
      setCitationVersion((v) => v + 1)
      load()
    } catch {
      toast.error(t('knowledge.citation_save_failed'))
    }
  }, [selectedId, citationDoc, load, toast, t])

  const openCitationForm = useCallback(async (doc: DocumentFileOut) => {
    setCitationDoc(doc)
    setCitationInitialData(null)
    if (doc.has_citation && selectedId) {
      try {
        const data = await citationsService.get(selectedId, doc.id)
        setCitationInitialData(data)
      } catch { /* no citation yet */ }
    }
  }, [selectedId])

  const handleBatchDelete = useCallback(async (docIds: number[]) => {
    try {
      await batchDelete(docIds)
      if (selectedDocId && docIds.includes(selectedDocId)) setSelectedDocId(null)
      toast.success(t('knowledge.deleted_n_docs', { count: docIds.length }))
    } catch {
      toast.error(t('knowledge.batch_delete_failed'))
    }
  }, [batchDelete, selectedDocId, toast, t])

  const handleBatchReindex = useCallback(async (docIds: number[]) => {
    try {
      await batchReindex(docIds)
      toast.success(t('knowledge.batch_reindex_triggered', { count: docIds.length }))
    } catch {
      toast.error(t('knowledge.batch_reindex_failed'))
    }
  }, [batchReindex, toast, t])

  // Called by DocumentTable after streaming parse completes — just reload docs
  const handleBatchAIParse = useCallback(async (_docIds: number[]) => {
    await load()
  }, [load])

  const handleBatchMatchText = useCallback(async (docIds: number[], text: string) => {
    try {
      await batchMatchText(docIds, text)
      toast.success(t('knowledge.match_done'))
      setCitationVersion((v) => v + 1)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : t('common.operation_failed')
      toast.error(t('knowledge.match_failed_with_reason', { reason: msg }))
      throw err
    }
  }, [batchMatchText, toast, t])

  const handleCitationChange = useCallback(() => {
    setCitationVersion((v) => v + 1)
    load()
  }, [load])

  const handleCancel = useCallback(async (docId: number) => {
    try {
      await cancel(docId)
      toast.success(t('knowledge.cancel_doc_processing_success'))
    } catch {
      toast.error(t('common.cancel_failed'))
    }
  }, [cancel, toast, t])

  const handleMoveKBConfirm = useCallback(async (folderId: string | null) => {
    if (movingKBId === null) return
    try {
      await update(movingKBId, { folder_id: folderId ? Number(folderId) : null })
    } catch {
      toast.error(t('common.move_failed'))
    }
  }, [movingKBId, update, toast, t])

  const handleRenameFolderConfirm = useCallback(async (name: string) => {
    if (!renamingFolder) return
    try {
      await renameFolder(renamingFolder.id, name)
    } catch {
      toast.error(t('knowledge.rename_folder_failed'))
    }
  }, [renamingFolder, renameFolder, toast, t])

  const handleDragMoveToFolder = useCallback(async (itemId: string | number, folderId: string | null) => {
    try {
      await update(Number(itemId), { folder_id: folderId ? Number(folderId) : null })
    } catch {
      toast.error(t('common.move_failed'))
    }
  }, [update, toast, t])

  // Edit KB form state
  const [editName, setEditName] = useState('')
  const [editDesc, setEditDesc] = useState('')

  const openEdit = useCallback(() => {
    if (!selected) return
    setEditName(selected.name)
    setEditDesc(selected.description ?? '')
    setShowEdit(true)
  }, [selected])

  const handleEdit = useCallback(async () => {
    if (!selectedId) return
    await update(selectedId, { name: editName.trim(), description: editDesc.trim() || null })
    setShowEdit(false)
    toast.success(t('knowledge.updated_kb'))
  }, [selectedId, editName, editDesc, update, toast, t])

  return (
    <div className="flex h-full">
      <ResizablePanel defaultWidth={260} minWidth={200} maxWidth={400} storageKey="kb_sidebar_width">
        <FolderListSidebar
          items={knowledgeBases}
          folders={folders}
          selectedId={selectedId}
          onSelect={(kb) => { setSelectedId(kb.id); setSelectedDocId(null) }}
          onCreateNew={() => setShowCreate(true)}
          onSearch={() => {}}
          renderItem={(kb) => (
            <div className="flex flex-col min-w-0">
              <span className="truncate">{kb.name}</span>
              <span className="text-xs text-neutral-500">{t('knowledge.doc_count', { count: kb.document_count })}</span>
            </div>
          )}
          title={t('nav.knowledge')}
          createLabel={t('knowledge.new_kb')}
          searchPlaceholder={t('knowledge.search_kb')}
          getItemFolder={(id) => {
            const kb = knowledgeBases.find((k) => k.id === id)
            return kb?.folder_id ? String(kb.folder_id) : null
          }}
          getContextMenuItems={(kb) => [
            { label: t('common.rename'), icon: <Pencil className="h-4 w-4" />, onClick: openEdit },
            { label: t('common.move_to_folder'), icon: <FolderInput className="h-4 w-4" />, onClick: () => setMovingKBId(kb.id) },
            { label: t('common.delete'), icon: <Trash2 className="h-4 w-4" />, onClick: () => setDeleteConfirm({ type: 'kb', id: kb.id }), danger: true }
          ]}
          getFolderContextMenuItems={(folder) => [
            { label: t('common.rename'), onClick: () => setRenamingFolder(folder) },
            { label: t('common.delete_folder'), icon: <Trash2 className="h-4 w-4" />, onClick: () => deleteFolder(folder.id), danger: true }
          ]}
          onCreateFolder={() => createFolder(t('common.new_folder'))}
          onMoveToFolder={handleDragMoveToFolder}
        />
      </ResizablePanel>

      {selected ? (
        <div className="flex-1 flex flex-col min-w-0">
          <KBInfoPanel kb={selected} onEdit={openEdit} onExport={handleExport} />
          {selectedDoc && (
            <DocumentDetail
              kbId={selected.id}
              doc={selectedDoc}
              onEditCitation={openCitationForm}
              onReindex={() => reindex(selectedDoc.id)}
              onDelete={() => setDeleteConfirm({ type: 'doc', id: selectedDoc.id })}
            />
          )}
          <DocumentTable
            kbId={selected.id}
            documents={documents}
            loading={docsLoading}
            onAdd={handleAddDocs}
            onReindex={(docId) => reindex(docId)}
            onDelete={(docId) => setDeleteConfirm({ type: 'doc', id: docId })}
            onCancel={handleCancel}
            onSelect={(doc) => setSelectedDocId(doc.id === selectedDocId ? null : doc.id)}
            onEditCitation={openCitationForm}
            onBatchDelete={handleBatchDelete}
            onBatchReindex={handleBatchReindex}
            onBatchParse={handleBatchAIParse}
            onParseFromText={handleBatchMatchText}
            onCitationChange={handleCitationChange}
            selectedDocId={selectedDocId}
            citationVersion={citationVersion}
          />
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center">
          <EmptyState
            icon={<Database className="h-12 w-12" />}
            title={t('knowledge.empty_title')}
            description={t('knowledge.empty_desc')}
            action={{ label: t('knowledge.new_kb'), onClick: () => setShowCreate(true) }}
          />
        </div>
      )}

      <KBCreateForm
        open={showCreate}
        onClose={() => setShowCreate(false)}
        onSubmit={async (data) => { await create(data) }}
      />

      <FormModal
        open={showEdit}
        onOpenChange={(v) => { if (!v) setShowEdit(false) }}
        title={t('knowledge.edit_kb')}
        onSubmit={handleEdit}
        submitLabel={t('common.save')}
      >
        <div className="space-y-3">
          <FormField label={t('common.name')}>
            <Input value={editName} onChange={(e) => setEditName(e.target.value)} />
          </FormField>
          <FormField label={t('common.description')}>
            <Textarea value={editDesc} onChange={(e) => setEditDesc(e.target.value)} rows={2} />
          </FormField>
        </div>
      </FormModal>

      <ConfirmDialog
        open={!!deleteConfirm}
        onOpenChange={() => setDeleteConfirm(null)}
        onConfirm={handleDeleteConfirm}
        title={deleteConfirm?.type === 'kb' ? t('knowledge.delete_kb_title') : t('knowledge.delete_doc_title')}
        description={deleteConfirm?.type === 'kb' ? t('knowledge.delete_kb_desc') : t('knowledge.delete_doc_desc')}
        danger
      />

      {citationDoc && (
        <CitationForm
          open={!!citationDoc}
          onClose={() => { setCitationDoc(null); setCitationInitialData(null) }}
          onSubmit={handleCitationSubmit}
          initialData={citationInitialData}
        />
      )}

      <DuplicateFilesDialog
        open={!!dupDialog}
        onOpenChange={() => setDupDialog(null)}
        duplicateNames={dupDialog?.duplicates ?? []}
        onAction={handleDuplicateAction}
      />

      {/* Move KB to folder dialog */}
      <MoveFolderDialog
        open={movingKBId !== null}
        onOpenChange={(v) => { if (!v) setMovingKBId(null) }}
        folders={folders}
        currentFolderId={(() => {
          const kb = knowledgeBases.find((k) => k.id === movingKBId)
          return kb?.folder_id ? String(kb.folder_id) : null
        })()}
        onConfirm={handleMoveKBConfirm}
      />

      {/* Rename folder dialog */}
      <RenameDialog
        open={!!renamingFolder}
        onOpenChange={(v) => { if (!v) setRenamingFolder(null) }}
        title={t('common.rename_folder')}
        initialValue={renamingFolder?.name ?? ''}
        onConfirm={handleRenameFolderConfirm}
      />
    </div>
  )
}
