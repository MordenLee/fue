export interface Folder {
  id: string
  name: string
  scope: 'conversations' | 'knowledge' | 'search'
  createdAt: string
}
