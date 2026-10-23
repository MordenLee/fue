import { contextBridge, ipcRenderer } from 'electron'
import { electronAPI } from '@electron-toolkit/preload'

// Custom APIs for renderer
const api = {
  getCoreUrl: (): Promise<string> => ipcRenderer.invoke('get-core-url'),
  getBackendUrl: (): Promise<string> => ipcRenderer.invoke('get-core-url'),
  checkHostSkill: (): Promise<string | null> => ipcRenderer.invoke('installation-check'),
  installationInfo: () => ipcRenderer.invoke('installation-info'),
  installHostSkill: (): Promise<string | null> => ipcRenderer.invoke('installation-skill'),
  openWorkspaceNextLaunch: (): Promise<string | null> => ipcRenderer.invoke('installation-workspace'),
  setModalOverlay: (dimmed: boolean): void => ipcRenderer.send('titlebar-modal-overlay', dimmed),
  openFileDialog: (options?: { filters?: { name: string; extensions: string[] }[]; title?: string }): Promise<string[]> =>
    ipcRenderer.invoke('dialog-open-files', options ?? {}),
  writingList: (): Promise<{ id: string; title: string; updatedAt: string }[]> => ipcRenderer.invoke('writing-list'),
  writingRead: (id: string): Promise<{ id: string; title: string; content: unknown; updatedAt: string }> => ipcRenderer.invoke('writing-read', id),
  writingCreate: (): Promise<{ id: string; title: string; content: unknown; updatedAt: string }> => ipcRenderer.invoke('writing-create'),
  writingSave: (document: { id: string; title: string; content: unknown }): Promise<{ updatedAt: string }> =>
    ipcRenderer.invoke('writing-save', document),
  writingSaveSync: (document: { id: string; title: string; content: unknown }): { updatedAt?: string; error?: string } =>
    ipcRenderer.sendSync('writing-save-sync', document)
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
