import { ElectronAPI } from '@electron-toolkit/preload'

declare global {
  interface Window {
    electron: ElectronAPI
    api: {
      getCoreUrl: () => Promise<string>
      checkHostSkill: () => Promise<string | null>
      getBackendUrl: () => Promise<string>
      installationInfo: () => Promise<{ data_dir: string; core_dir: string; registered: boolean; name: string; version: string; connected: boolean; pending_data_dir: string | null }>
      installHostSkill: () => Promise<string | null>
      openWorkspaceNextLaunch: () => Promise<string | null>
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
