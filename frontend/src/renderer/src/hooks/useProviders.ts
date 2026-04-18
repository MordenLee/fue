import { useState, useEffect, useCallback } from 'react'
import { providersService } from '../services/providers'
import { modelsService } from '../services/models'
import type { ProviderOut, ProviderCreate, ProviderUpdate } from '../types/provider'
import type { AIModelOut } from '../types/provider'

export function useProviders() {
  const [providers, setProviders] = useState<ProviderOut[]>([])
  const [models, setModels] = useState<AIModelOut[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      setLoading(true)
      const [p, m] = await Promise.all([providersService.list(), modelsService.list()])
      setProviders(p)
      setModels(m)
    } catch (err) {
      console.error('Failed to load providers', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const createProvider = useCallback(async (data: ProviderCreate) => {
    const p = await providersService.create(data)
    setProviders((prev) => [...prev, p])
    return p
  }, [])

  const updateProvider = useCallback(async (id: number, data: ProviderUpdate) => {
    const updated = await providersService.update(id, data)
    setProviders((prev) => prev.map((p) => (p.id === id ? updated : p)))
    return updated
  }, [])

  const removeProvider = useCallback(async (id: number) => {
    await providersService.remove(id)
    setProviders((prev) => prev.filter((p) => p.id !== id))
    setModels((prev) => prev.filter((m) => m.provider_id !== id))
  }, [])

  const toggleProvider = useCallback(async (id: number, enabled: boolean) => {
    const updated = await providersService.setEnabled(id, enabled)
    setProviders((prev) => prev.map((p) => (p.id === id ? updated : p)))
    if (!enabled) {
      // Disable all models under this provider locally
      const providerModelIds = models.filter((m) => m.provider_id === id && m.is_enabled).map((m) => m.id)
      for (const mid of providerModelIds) {
        try { await modelsService.setEnabled(mid, false) } catch { /* ignore */ }
      }
      const refreshed = await modelsService.list({ provider_id: id })
      setModels((prev) => [...prev.filter((x) => x.provider_id !== id), ...refreshed])
    }
  }, [models])

  const reloadModels = useCallback(async (providerId?: number) => {
    const m = await modelsService.list(providerId ? { provider_id: providerId } : undefined)
    if (providerId) {
      setModels((prev) => [...prev.filter((x) => x.provider_id !== providerId), ...m])
    } else {
      setModels(m)
    }
  }, [])

  const reorderProviders = useCallback(async (reordered: ProviderOut[]) => {
    setProviders(reordered)
    const items = reordered.map((p, i) => ({ id: p.id, sort_order: i }))
    await providersService.reorder(items)
  }, [])

  return {
    providers, models, loading, load,
    createProvider, updateProvider, removeProvider, toggleProvider,
    reloadModels, reorderProviders
  }
}
