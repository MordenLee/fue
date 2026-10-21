import { app, BrowserWindow, ipcMain } from 'electron'
import { randomUUID } from 'crypto'
import { existsSync, mkdirSync, readFileSync, readdirSync, renameSync, writeFileSync } from 'fs'
import { join } from 'path'

type WritingDocument = {
  id: string
  title: string
  content: unknown
  updatedAt: string
}

const documentId = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const emptyContent = { type: 'doc', content: [{ type: 'paragraph' }] }

export function registerWritingDocuments(window: BrowserWindow): void {
  const channels = ['writing-list', 'writing-read', 'writing-create', 'writing-save']
  for (const channel of channels) ipcMain.removeHandler(channel)
  const directory = join(app.getPath('userData'), 'writing-documents')
  mkdirSync(directory, { recursive: true })
  const pathFor = (id: string): string => {
    if (!documentId.test(id)) throw new Error('Invalid writing document ID')
    return join(directory, `${id}.json`)
  }
  const read = (id: string): WritingDocument => {
    const path = pathFor(id)
    if (!existsSync(path)) throw new Error('Writing document not found')
    return JSON.parse(readFileSync(path, 'utf8')) as WritingDocument
  }
  const fromWindow = (sender: Electron.WebContents): void => {
    if (sender !== window.webContents) throw new Error('Invalid writing document request')
  }
  const persist = (input: { id: string; title: string; content: unknown }): { updatedAt: string } => {
    const path = pathFor(input.id)
    if (!existsSync(path)) throw new Error('Writing document not found')
    if (typeof input.title !== 'string' || input.title.length > 300 ||
        !input.content || typeof input.content !== 'object') throw new Error('Invalid writing document')
    const document: WritingDocument = {
      id: input.id, title: input.title.trim() || '未命名文档', content: input.content,
      updatedAt: new Date().toISOString()
    }
    const serialized = JSON.stringify(document)
    if (serialized.length > 20_000_000) throw new Error('Writing document is too large')
    const temporary = join(directory, `${input.id}.${randomUUID()}.tmp`)
    writeFileSync(temporary, serialized, 'utf8')
    renameSync(temporary, path)
    return { updatedAt: document.updatedAt }
  }

  ipcMain.handle('writing-list', (event) => {
    fromWindow(event.sender)
    return readdirSync(directory)
      .filter((name) => documentId.test(name.slice(0, -5)) && name.endsWith('.json'))
      .map((name) => {
        try {
          const { id, title, updatedAt } = read(name.slice(0, -5))
          return { id, title, updatedAt }
        } catch { return null }
      })
      .filter((item) => item !== null)
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
  })

  ipcMain.handle('writing-read', (event, id: string) => {
    fromWindow(event.sender)
    return read(id)
  })

  ipcMain.handle('writing-create', (event) => {
    fromWindow(event.sender)
    const document: WritingDocument = {
      id: randomUUID(), title: '未命名文档', content: emptyContent,
      updatedAt: new Date().toISOString()
    }
    writeFileSync(pathFor(document.id), JSON.stringify(document), 'utf8')
    return document
  })

  ipcMain.handle('writing-save', (event, input: { id: string; title: string; content: unknown }) => {
    fromWindow(event.sender)
    return persist(input)
  })
  ipcMain.on('writing-save-sync', (event, input: { id: string; title: string; content: unknown }) => {
    try {
      fromWindow(event.sender)
      event.returnValue = persist(input)
    } catch (error) {
      event.returnValue = { error: error instanceof Error ? error.message : String(error) }
    }
  })
  window.on('closed', () => {
    for (const channel of channels) ipcMain.removeHandler(channel)
    ipcMain.removeAllListeners('writing-save-sync')
  })
}
