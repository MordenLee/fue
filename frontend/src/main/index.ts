import { app, shell, BrowserWindow, ipcMain, dialog } from 'electron'
import { appendFileSync, copyFileSync, cpSync, existsSync, mkdirSync } from 'fs'
import { request as httpRequest } from 'http'
import { createServer } from 'net'
import { join } from 'path'
import { spawn, type ChildProcess } from 'child_process'
import { electronApp, optimizer, is } from '@electron-toolkit/utils'
import icon from '../../resources/icon.png?asset'

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
let backendProcess: ChildProcess | null = null
let backendPort: number | null = null
let backendReady: Promise<number>
let resolveBackendReady: (port: number) => void
let rejectBackendReady: (error: Error) => void
let backendReadySettled = false
let backendStartupTimer: NodeJS.Timeout | null = null

// Create promise that resolves when backend reports its port
backendReady = new Promise((resolve, reject) => {
  resolveBackendReady = (port: number) => {
    if (backendReadySettled) return
    backendReadySettled = true
    resolve(port)
  }
  rejectBackendReady = (error: Error) => {
    if (backendReadySettled) return
    backendReadySettled = true
    reject(error)
  }
})

function getBackendDir(): string {
  if (is.dev) {
    return join(__dirname, '..', '..', '..', 'backend')
  }
  return join(process.resourcesPath, 'backend')
}

function getProjectRoot(): string {
  if (is.dev) {
    return join(__dirname, '..', '..', '..')
  }
  return process.resourcesPath
}

function getBundledPythonDir(): string {
  return join(process.resourcesPath, 'python')
}

function getPythonCommand(): string {
  if (is.dev) {
    const projectRoot = getProjectRoot()
    if (process.platform === 'win32') {
      const venvPython = join(projectRoot, '.venv', 'Scripts', 'python.exe')
      return existsSync(venvPython) ? venvPython : 'python'
    }
    const venvPython = join(projectRoot, '.venv', 'bin', 'python3')
    return existsSync(venvPython) ? venvPython : 'python3'
  }

  if (process.platform === 'win32') {
    return join(getBundledPythonDir(), 'python.exe')
  }
  return join(getBundledPythonDir(), 'bin', 'python3')
}

function findAvailablePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = createServer()

    server.on('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const address = server.address()
      if (!address || typeof address === 'string') {
        server.close(() => reject(new Error('Unable to allocate backend port')))
        return
      }
      const port = address.port
      server.close((err) => {
        if (err) {
          reject(err)
          return
        }
        resolve(port)
      })
    })
  })
}

function pingBackend(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const req = httpRequest(
      {
        host: '127.0.0.1',
        port,
        path: '/api/ping',
        method: 'GET',
        timeout: 1500
      },
      (res) => {
        const code = res.statusCode ?? 0
        res.resume()
        resolve(code >= 200 && code < 300)
      }
    )
    req.on('error', () => resolve(false))
    req.on('timeout', () => {
      req.destroy()
      resolve(false)
    })
    req.end()
  })
}

async function waitUntilBackendReady(port: number): Promise<void> {
  while (!backendReadySettled) {
    const ok = await pingBackend(port)
    if (ok) {
      backendPort = port
      flog(`Backend started on port ${backendPort}`)
      console.log(`Backend started on port ${backendPort}`)
      clearBackendStartupTimer()
      resolveBackendReady(backendPort)
      return
    }
    await new Promise((resolve) => setTimeout(resolve, 300))
  }
}

function clearBackendStartupTimer(): void {
  if (backendStartupTimer) {
    clearTimeout(backendStartupTimer)
    backendStartupTimer = null
  }
}

function failBackendStartup(message: string): void {
  if (backendReadySettled) return
  clearBackendStartupTimer()
  const error = new Error(message)
  console.error(message)
  rejectBackendReady(error)
  if (!is.dev) {
    dialog.showErrorBox('后端启动失败', message)
  }
}

function getBackendDataDir(): string {
  if (is.dev) {
    return getBackendDir()
  }
  return join(app.getPath('userData'), 'backend-data')
}

function prepareBackendDataDir(): string {
  const backendDataDir = getBackendDataDir()
  mkdirSync(backendDataDir, { recursive: true })

  if (is.dev) {
    return backendDataDir
  }

  const bundledBackendDir = getBackendDir()
  const bundledDb = join(bundledBackendDir, 'app.db')
  const dataDb = join(backendDataDir, 'app.db')
  if (!existsSync(dataDb) && existsSync(bundledDb)) {
    copyFileSync(bundledDb, dataDb)
  }

  const bundledChromaDir = join(bundledBackendDir, 'chroma_data')
  const dataChromaDir = join(backendDataDir, 'chroma_data')
  if (!existsSync(dataChromaDir) && existsSync(bundledChromaDir)) {
    cpSync(bundledChromaDir, dataChromaDir, { recursive: true })
  }

  return backendDataDir
}

async function startBackend(): Promise<void> {
  const backendDir = getBackendDir()
  const backendDataDir = prepareBackendDataDir()

  const pythonCmd = getPythonCommand()
  const pythonHome = is.dev ? undefined : getBundledPythonDir()
  let expectedBackendPort: number

  try {
    expectedBackendPort = await findAvailablePort()
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    failBackendStartup(`无法分配后端端口：${message}`)
    return
  }

  if (!existsSync(pythonCmd) && !is.dev) {
    failBackendStartup(`Bundled Python runtime not found: ${pythonCmd}`)
    return
  }

  flog(`Starting backend in: ${backendDir} with: ${pythonCmd}`)
  flog(`Backend data dir: ${backendDataDir}`)
  flog(`APP_BACKEND_PORT: ${expectedBackendPort}`)
  flog(`python exists: ${existsSync(pythonCmd)}`)
  console.log(`Starting backend in: ${backendDir} with: ${pythonCmd}`)

  backendStartupTimer = setTimeout(() => {
    failBackendStartup('后端启动超时。请检查安装目录是否完整，或重新安装应用。')
  }, 30000)

  // In production, override PYTHONHOME/PYTHONPATH to point exclusively at the
  // bundled runtime, preventing any system Python installation from interfering.
  const productionPythonEnv = pythonHome
    ? { PYTHONHOME: pythonHome, PYTHONPATH: '' }
    : {}

  backendProcess = spawn(pythonCmd, ['main.py'], {
    cwd: backendDir,
    env: {
      ...process.env,
      APP_BACKEND_DATA_DIR: backendDataDir,
      APP_BACKEND_PORT: String(expectedBackendPort),
      ...productionPythonEnv
    },
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true
  })

  let outputBuffer = ''
  const handleOutput = (data: Buffer): void => {
    outputBuffer += data.toString()
    const lines = outputBuffer.split(/\r?\n/)
    outputBuffer = lines.pop() ?? ''

    for (const line of lines) {
      const text = line.trim()
      if (!text) continue
      flog(`[backend] ${text}`)
      console.log(`[backend] ${text}`)
      const match = text.match(/BACKEND_PORT:(\d+)/)
      if (match) {
        backendPort = parseInt(match[1], 10)
      }
    }
  }

  backendProcess.stdout?.on('data', handleOutput)
  backendProcess.stderr?.on('data', handleOutput)

  void waitUntilBackendReady(expectedBackendPort)

  backendProcess.on('error', (err) => {
    flog(`backend spawn error: ${err.message}`)
    failBackendStartup(`无法启动后端进程：${err.message}`)
  })

  backendProcess.on('exit', (code) => {
    flog(`backend exited with code ${code}`)
    clearBackendStartupTimer()
    if (!backendReadySettled) {
      failBackendStartup(`后端在启动完成前退出，退出码：${code ?? 'unknown'}`)
    }
    console.log(`Backend exited with code ${code}`)
    backendProcess = null
  })
}

function stopBackend(): void {
  if (!backendProcess) return
  console.log('Stopping backend...')
  if (process.platform === 'win32') {
    // On Windows, spawn taskkill to kill the process tree
    spawn('taskkill', ['/pid', String(backendProcess.pid), '/f', '/t'], { windowsHide: true })
  } else {
    backendProcess.kill('SIGTERM')
  }
  backendProcess = null
}

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
    ...(process.platform === 'linux' ? { icon } : {}),
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false
    }
  })

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

  // IPC: renderer can query backend URL (waits until backend is ready)
  ipcMain.handle('get-backend-url', async () => {
    const port = await backendReady
    return `http://127.0.0.1:${port}`
  })

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

  // Start backend server
  void startBackend()

  // Wait for backend to be fully ready before showing the main window
  try {
    await backendReady
  } catch {
    // Error already surfaced via dialog in failBackendStartup
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
  stopBackend()
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('before-quit', () => {
  stopBackend()
})

// In this file you can include the rest of your app's specific main process
// code. You can also put them in separate files and require them here.
