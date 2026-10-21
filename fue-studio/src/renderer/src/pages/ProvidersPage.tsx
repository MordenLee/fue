import { useState, useCallback } from 'react'
import { Server, Trash2 } from 'lucide-react'
import { FolderListSidebar } from '../components/shared/FolderListSidebar'
import { ProviderConfig } from '../components/providers/ProviderConfig'
import { ProviderForm } from '../components/providers/ProviderForm'
import { ModelList } from '../components/providers/ModelList'
import { ModelForm } from '../components/providers/ModelForm'
import { ResizablePanel } from '../components/ui/ResizablePanel'
import { EmptyState } from '../components/ui/EmptyState'
import { ConfirmDialog } from '../components/ui/ConfirmDialog'
import { Switch } from '../components/ui/Switch'
import { useProviders } from '../hooks/useProviders'
import { useToast } from '../contexts/ToastContext'
import { modelsService } from '../services/models'
import { getProviderLogo } from '../utils/providerLogos'
import type { AIModelOut, AIModelCreate, AIModelUpdate } from '../types/provider'
import { useI18n } from '../i18n'

export function ProvidersPage() {
  const { t } = useI18n()
  const {
    providers, models, createProvider, updateProvider, removeProvider,
    toggleProvider, reloadModels, reorderProviders
  } = useProviders()
  const toast = useToast()

  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [showProviderForm, setShowProviderForm] = useState(false)
  const [showModelForm, setShowModelForm] = useState(false)
  const [editModel, setEditModel] = useState<AIModelOut | null>(null)
  const [deleteConfirm, setDeleteConfirm] = useState<{ type: 'provider' | 'model'; id: number } | null>(null)

  const selected = providers.find((p) => p.id === selectedId)
  const providerModels = models.filter((m) => m.provider_id === selectedId)

  const handleDeleteConfirm = useCallback(async () => {
    if (!deleteConfirm) return
    try {
      if (deleteConfirm.type === 'provider') {
        await removeProvider(deleteConfirm.id)
        if (selectedId === deleteConfirm.id) setSelectedId(null)
        toast.success(t('providers.deleted_provider'))
      } else {
        await modelsService.remove(deleteConfirm.id)
        await reloadModels(selectedId ?? undefined)
        toast.success(t('providers.deleted_model'))
      }
    } catch {
      toast.error(t('common.delete_failed'))
    }
    setDeleteConfirm(null)
  }, [deleteConfirm, removeProvider, selectedId, reloadModels, toast, t])

  const handleToggleModel = useCallback(async (modelId: number, enabled: boolean) => {
    if (enabled && selected && !selected.is_enabled) {
      toast.error(t('providers.enable_provider_first'))
      return
    }
    try {
      await modelsService.setEnabled(modelId, enabled)
      await reloadModels(selectedId ?? undefined)
    } catch {
      toast.error(t('common.operation_failed'))
    }
  }, [selectedId, selected, reloadModels, toast, t])

  const handleModelSubmit = useCallback(async (data: AIModelCreate | AIModelUpdate) => {
    try {
      if (editModel) {
        await modelsService.update(editModel.id, data as AIModelUpdate)
      } else {
        await modelsService.create(data as AIModelCreate)
      }
      await reloadModels(selectedId ?? undefined)
      toast.success(editModel ? t('providers.model_updated') : t('providers.model_created'))
      setEditModel(null)
    } catch {
      toast.error(t('common.operation_failed'))
    }
  }, [editModel, selectedId, reloadModels, toast, t])

  const handleSetDefault = useCallback(async (modelId: number) => {
    try {
      await modelsService.update(modelId, { is_default: true })
      await reloadModels()
      toast.success(t('providers.set_default_success'))
    } catch {
      toast.error(t('common.operation_failed'))
    }
  }, [reloadModels, toast, t])

  const handleReorderProviders = useCallback((activeId: string | number, overId: string | number) => {
    const activeIndex = providers.findIndex((p) => p.id === Number(activeId))
    const overIndex = providers.findIndex((p) => p.id === Number(overId))
    if (activeIndex < 0 || overIndex < 0 || activeIndex === overIndex) return

    const reordered = [...providers]
    const [moved] = reordered.splice(activeIndex, 1)
    reordered.splice(overIndex, 0, moved)
    void reorderProviders(reordered)
  }, [providers, reorderProviders])

  return (
    <div className="flex h-full">
      <ResizablePanel defaultWidth={240} minWidth={180} maxWidth={360} storageKey="providers_sidebar_width">
        <FolderListSidebar
          items={providers}
          folders={[]}
          selectedId={selectedId}
          onSelect={(p) => setSelectedId(p.id)}
          onCreateNew={() => setShowProviderForm(true)}
          renderItem={(p) => {
            const logo = getProviderLogo(p.name)
            return (
              <div className="flex items-center gap-2 min-w-0 w-full">
                {logo ? (
                  <span className="flex items-center justify-center h-5 w-5 shrink-0 rounded bg-neutral-200 dark:bg-neutral-700">
                    <img src={logo} alt="" className="h-3.5 w-3.5" />
                  </span>
                ) : (
                  <span className={`h-2 w-2 rounded-full shrink-0 ${p.is_enabled ? 'bg-green-400' : 'bg-neutral-600'}`} />
                )}
                <span className="truncate flex-1">{p.name}</span>
                <span onClick={(e) => e.stopPropagation()} onMouseDown={(e) => e.stopPropagation()}>
                  <Switch checked={p.is_enabled} onCheckedChange={(v) => toggleProvider(p.id, v)} />
                </span>
              </div>
            )
          }}
          title={t('nav.providers')}
          createLabel={t('providers.add_provider')}
          searchPlaceholder={t('providers.search_provider')}
          onSearch={() => {}}
          getItemFolder={() => null}
          getContextMenuItems={(p) => [
            { label: t('common.delete'), icon: <Trash2 className="h-4 w-4" />, onClick: () => setDeleteConfirm({ type: 'provider', id: p.id }), danger: true }
          ]}
          getFolderContextMenuItems={() => []}
          onReorder={handleReorderProviders}
        />
      </ResizablePanel>

      {selected ? (
        <div className="flex-1 flex flex-col min-w-0">
          <ProviderConfig
            provider={selected}
            models={providerModels}
            onUpdate={async (id, data) => { await updateProvider(id, data) }}
            onToggle={async (id, enabled) => { await toggleProvider(id, enabled) }}
            onDelete={(id) => setDeleteConfirm({ type: 'provider', id })}
          />
          <ModelList
            models={providerModels}
            onAdd={() => { setEditModel(null); setShowModelForm(true) }}
            onToggle={handleToggleModel}
            onEdit={(m) => { setEditModel(m); setShowModelForm(true) }}
            onDelete={(id) => setDeleteConfirm({ type: 'model', id })}
            onSetDefault={handleSetDefault}
          />
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center">
          <EmptyState
            icon={<Server className="h-12 w-12" />}
            title={t('providers.empty_title')}
            description={t('providers.empty_desc')}
            action={{ label: t('providers.add_provider'), onClick: () => setShowProviderForm(true) }}
          />
        </div>
      )}

      <ProviderForm
        open={showProviderForm}
        onClose={() => setShowProviderForm(false)}
        onSubmit={async (data) => { await createProvider(data) }}
      />

      {selectedId && (
        <ModelForm
          open={showModelForm}
          onClose={() => { setShowModelForm(false); setEditModel(null) }}
          onSubmit={handleModelSubmit}
          providerId={selectedId}
          initialData={editModel}
        />
      )}

      <ConfirmDialog
        open={!!deleteConfirm}
        onOpenChange={() => setDeleteConfirm(null)}
        onConfirm={handleDeleteConfirm}
        title={deleteConfirm?.type === 'provider' ? t('providers.delete_provider_title') : t('providers.delete_model_title')}
        description={deleteConfirm?.type === 'provider' ? t('providers.delete_provider_desc') : t('providers.delete_model_desc')}
        danger
      />
    </div>
  )
}
