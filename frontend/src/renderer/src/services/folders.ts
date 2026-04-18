import { request } from './api'
import type { Folder } from '../types/folder'

interface FolderRaw {
  id: number
  name: string
  scope: string
  created_at: string
}

function toFolder(raw: FolderRaw): Folder {
  return {
    id: String(raw.id),
    name: raw.name,
    scope: raw.scope as Folder['scope'],
    createdAt: raw.created_at,
  }
}

export const foldersService = {
  list: (scope: Folder['scope']) =>
    request<FolderRaw[]>(`/api/folders?scope=${scope}`).then((list) => list.map(toFolder)),

  create: (name: string, scope: Folder['scope']) =>
    request<FolderRaw>('/api/folders', {
      method: 'POST',
      body: JSON.stringify({ name, scope }),
    }).then(toFolder),

  rename: (id: string, name: string) =>
    request<FolderRaw>(`/api/folders/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    }).then(toFolder),

  delete: (id: string) =>
    request<void>(`/api/folders/${id}`, { method: 'DELETE' }),
}
