import { app, shell, BrowserWindow, ipcMain, dialog } from 'electron'
import { appendFileSync, mkdirSync } from 'fs'
import { join } from 'path'
import { electronApp, optimizer, is } from '@electron-toolkit/utils'
import icon from '../../resources/icon.png?asset'
import { registerWritingDocuments } from './writingDocuments'
import { initializeCoreAccess, ensureCore, releaseCore } from './coreClient'

// ─── File logging (production only) ───
let _logFile: string | null = null
function initLog(): void {
  if (is.dev) return
  const logDir = join(app.getPath('userData'), 'logs')
  mkdirSync(logDir, { recursive: true })
  _logFile = join(logDir, 'main.log')
  flog(`=== App started at ${new Date().toISOString()} ===`)
}
function flog(msg: string): void {
  if (!_logFile) return
  try { appendFileSync(_logFile, `${new Date().toISOString()} ${msg}\n`) } catch { /* ignore */ }
}

// ─── Backend process management ───
function createWindow(): void {
  // Create the browser window.
  const mainWindow = new BrowserWindow({
    width: 900,
    height: 670,
    show: false,
    autoHideMenuBar: true,
    backgroundColor: '#171717',
    titleBarStyle: 'hidden',
    ...(process.platform === 'win32'
      ? { titleBarOverlay: { color: '#171717', symbolColor: '#a3a3a3', height: 28 } }
      : {}),
    icon,
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false
    }
  })
  registerWritingDocuments(mainWindow)

  // Update title bar overlay and window background when theme changes (Windows only)
  if (process.platform === 'win32') {
    let currentTheme = 'dark'

    ipcMain.on('titlebar-theme', (_, theme: string) => {
      currentTheme = theme
      if (theme === 'dark') {
        mainWindow.setBackgroundColor('#171717')
        mainWindow.setTitleBarOverlay({ color: '#171717', symbolColor: '#a3a3a3', height: 28 })
      } else {
        mainWindow.setBackgroundColor('#ffffff')
        mainWindow.setTitleBarOverlay({ color: '#ffffff', symbolColor: '#6b7280', height: 28 })
      }
    })

    // Dim title bar when modal overlay is shown
    ipcMain.on('titlebar-modal-overlay', (_, dimmed: boolean) => {
      if (dimmed) {
        // Match the bg-black/60 overlay: blend current theme color 60% toward black
        if (currentTheme === 'dark') {
          mainWindow.setTitleBarOverlay({ color: '#0a0a0a', symbolColor: '#414141', height: 28 })
        } else {
          mainWindow.setTitleBarOverlay({ color: '#666666', symbolColor: '#444444', height: 28 })
        }
      } else {
        if (currentTheme === 'dark') {
          mainWindow.setTitleBarOverlay({ color: '#171717', symbolColor: '#a3a3a3', height: 28 })
        } else {
          mainWindow.setTitleBarOverlay({ color: '#ffffff', symbolColor: '#6b7280', height: 28 })
        }
      }
    })
  }

  mainWindow.on('ready-to-show', () => {
    mainWindow.show()
  })

  mainWindow.webContents.setWindowOpenHandler((details) => {
    shell.openExternal(details.url)
    return { action: 'deny' }
  })

  // HMR for renderer base on electron-vite cli.
  // Load the remote URL for development or the local html file for production.
  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL'])
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

// This method will be called when Electron has finished
// initialization and is ready to create browser windows.
// Some APIs can only be used after this event occurs.
app.whenReady().then(async () => {
  // Set app user model id for windows
  electronApp.setAppUserModelId('com.fue')

  initLog()

  // Default open or close DevTools by F12 in development
  // and ignore CommandOrControl + R in production.
  // see https://github.com/alex8088/electron-toolkit/tree/master/packages/utils
  app.on('browser-window-created', (_, window) => {
    optimizer.watchWindowShortcuts(window)
  })

  // IPC test
  ipcMain.on('ping', () => console.log('pong'))

  initializeCoreAccess()
  ipcMain.handle('get-backend-url', async () => `http://127.0.0.1:${await ensureCore()}`)

  // IPC: open native file dialog and return selected file paths
  ipcMain.handle('dialog-open-files', async (_, options: { filters?: { name: string; extensions: string[] }[]; title?: string }) => {
    const win = BrowserWindow.getFocusedWindow()
    if (!win) return []
    const result = await dialog.showOpenDialog(win, {
      title: options.title ?? '选择文件',
      properties: ['openFile', 'multiSelections'],
      filters: options.filters
    })
    return result.canceled ? [] : result.filePaths
  })

  try {
    await ensureCore()
  } catch (error) {
    dialog.showErrorBox('Core startup failed', error instanceof Error ? error.message : String(error))
    app.quit()
    return
  }

  // Backend is ready — create and show the main window
  createWindow()

  app.on('activate', function () {
    // On macOS it's common to re-create a window in the app when the
    // dock icon is clicked and there are no other windows open.
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

// Quit when all windows are closed, except on macOS. There, it's common
// for applications and their menu bar to stay active until the user quits
// explicitly with Cmd + Q.
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

let released = false
app.on('before-quit', event => {
  if (released) return
  event.preventDefault()
  void releaseCore().finally(() => { released = true; app.quit() })
})

// In this file you can include the rest of your app's specific main process
// code. You can also put them in separate files and require them here.
