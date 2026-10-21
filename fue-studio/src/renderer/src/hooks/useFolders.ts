import { useState, useCallback, useEffect } from 'react'
import { foldersService } from '../services/folders'
import type { Folder } from '../types/folder'

export function useFolders(scope: Folder['scope']) {
  const [folders, setFolders] = useState<Folder[]>([])

  const loadFolders = useCallback(async () => {
    try {
      const data = await foldersService.list(scope)
      setFolders(data)
    } catch {
      // ignore load errors silently
    }
  }, [scope])

  useEffect(() => {
    loadFolders()
  }, [loadFolders])

  const createFolder = useCallback(
    async (name: string) => {
      const folder = await foldersService.create(name, scope)
      setFolders((prev) => [...prev, folder])
      return folder
    },
    [scope]
  )

  const renameFolder = useCallback(async (id: string, name: string) => {
    const updated = await foldersService.rename(id, name)
    setFolders((prev) => prev.map((f) => (f.id === id ? updated : f)))
  }, [])

  const deleteFolder = useCallback(async (id: string) => {
    await foldersService.delete(id)
    setFolders((prev) => prev.filter((f) => f.id !== id))
  }, [])

  return { folders, createFolder, renameFolder, deleteFolder }
}

