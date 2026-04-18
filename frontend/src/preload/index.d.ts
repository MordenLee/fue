import { ElectronAPI } from '@electron-toolkit/preload'

declare global {
  interface Window {
    electron: ElectronAPI
    api: {
      getBackendUrl: () => Promise<string>
      setModalOverlay: (dimmed: boolean) => void
      openFileDialog: (options?: { filters?: { name: string; extensions: string[] }[]; title?: string }) => Promise<string[]>
    }
  }
}
