import { ElectronAPI } from '@electron-toolkit/preload'

declare global {
  interface Window {
    electron: ElectronAPI
    api: {
      getBackendUrl: () => Promise<string>
      setModalOverlay: (dimmed: boolean) => void
      openFileDialog: (options?: { filters?: { name: string; extensions: string[] }[]; title?: string }) => Promise<string[]>
      writingList: () => Promise<{ id: string; title: string; updatedAt: string }[]>
      writingRead: (id: string) => Promise<{ id: string; title: string; content: unknown; updatedAt: string }>
      writingCreate: () => Promise<{ id: string; title: string; content: unknown; updatedAt: string }>
      writingSave: (document: { id: string; title: string; content: unknown }) => Promise<{ updatedAt: string }>
      writingSaveSync: (document: { id: string; title: string; content: unknown }) => { updatedAt?: string; error?: string }
    }
  }
}
