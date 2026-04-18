import { contextBridge, ipcRenderer } from 'electron'
import { electronAPI } from '@electron-toolkit/preload'

// Custom APIs for renderer
const api = {
  getBackendUrl: (): Promise<string> => ipcRenderer.invoke('get-backend-url'),
  setModalOverlay: (dimmed: boolean): void => ipcRenderer.send('titlebar-modal-overlay', dimmed),
  openFileDialog: (options?: { filters?: { name: string; extensions: string[] }[]; title?: string }): Promise<string[]> =>
    ipcRenderer.invoke('dialog-open-files', options ?? {})
}

// Use `contextBridge` APIs to expose Electron APIs to
// renderer only if context isolation is enabled, otherwise
// just add to the DOM global.
if (process.contextIsolated) {
  try {
    contextBridge.exposeInMainWorld('electron', electronAPI)
    contextBridge.exposeInMainWorld('api', api)
  } catch (error) {
    console.error(error)
  }
} else {
  // @ts-ignore (define in dts)
  window.electron = electronAPI
  // @ts-ignore (define in dts)
  window.api = api
}
