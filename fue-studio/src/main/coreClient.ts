import { app, session } from 'electron'
import { existsSync, mkdirSync, readFileSync, writeFileSync, renameSync, openSync, closeSync } from 'fs'
import { request } from 'http'
import { join, resolve } from 'path'
import { spawn } from 'child_process'
import { randomUUID } from 'crypto'
import { is } from '@electron-toolkit/utils'

type Discovery = { instance_id: string; data_dir: string; port: number; tokens: { studio: string } }
const clientId = randomUUID()
let connection: Discovery | null = null
let starting: Promise<number> | null = null
let heartbeat: NodeJS.Timeout | null = null
let quitting = false

function componentDir(): string {
  return is.dev ? join(__dirname, '..', '..', '..', 'fue-core') : join(process.resourcesPath, 'backend')
}

function dataDir(): string {
  return process.env.APP_BACKEND_DATA_DIR || (is.dev
    ? join(__dirname, '..', '..', '..', 'backend')
    : join(app.getPath('userData'), 'backend-data'))
}

function python(): string {
  if (!is.dev) return process.platform === 'win32'
    ? join(process.resourcesPath, 'python', 'python.exe')
    : join(process.resourcesPath, 'python', 'bin', 'python3')
  const root = join(__dirname, '..', '..', '..')
  const local = process.platform === 'win32' ? join(root, '.venv', 'Scripts', 'python.exe') : join(root, '.venv', 'bin', 'python3')
  return existsSync(local) ? local : process.platform === 'win32' ? 'python' : 'python3'
}

function call(info: Discovery, path: string, body?: object): Promise<Record<string, unknown>> {
  return new Promise((resolveResult, reject) => {
    const data = body === undefined ? undefined : JSON.stringify(body)
    const req = request({ host: '127.0.0.1', port: info.port, path: `/api/v1/system/${path}`,
      method: data === undefined ? 'GET' : 'POST', timeout: 3000,
      headers: { Authorization: `Bearer ${info.tokens.studio}`, 'Content-Type': 'application/json' }
    }, res => {
      let text = ''
      res.on('data', chunk => { text += chunk })
      res.on('end', () => {
        if ((res.statusCode ?? 500) >= 300) return reject(new Error(`Core ${path}: ${res.statusCode}`))
        try { resolveResult(JSON.parse(text)) } catch (error) { reject(error) }
      })
    })
    req.on('error', reject)
    req.on('timeout', () => req.destroy(new Error('Core request timed out')))
    req.end(data)
  })
}

async function discover(): Promise<Discovery | null> {
  try {
    const info = JSON.parse(readFileSync(join(dataDir(), 'runtime', 'core.json'), 'utf8')) as Discovery
    if (resolve(info.data_dir).toLowerCase() !== resolve(dataDir()).toLowerCase()) return null
    if (!Number.isInteger(info.port) || info.port < 1 || info.port > 65535) return null
    const state = await call(info, 'status')
    return state.instance_id === info.instance_id ? info : null
  } catch { return null }
}

async function attach(info: Discovery): Promise<number> {
  if (quitting) throw new Error('Studio is closing')
  await call(info, 'lease', { client_id: clientId })
  connection = info
  // Stable non-secret connection hints survive Core's idle shutdown.
  const config = join(app.getPath('userData'), 'core-connection.json')
  writeFileSync(config + '.tmp', JSON.stringify({ core_dir: componentDir(), data_dir: dataDir(), python: python() }))
  renameSync(config + '.tmp', config)
  if (!heartbeat) {
    heartbeat = setInterval(() => {
      if (connection && !quitting) void call(connection, 'lease', { client_id: clientId }).catch(() => {
        connection = null
        void ensureCore().catch(error => console.error('Core reconnect failed:', error.message))
      })
    }, 10000)
    heartbeat.unref()
  }
  return info.port
}

async function connectOrStart(): Promise<number> {
  const existing = await discover()
  if (existing) return attach(existing)
  const root = dataDir()
  mkdirSync(join(root, 'runtime'), { recursive: true })
  const log = openSync(join(root, 'runtime', 'studio-core.log'), 'a')
  const pythonHome = join(process.resourcesPath, 'python')
  const args = [join(componentDir(), 'main.py'), '--data-dir', root]
  if (!existsSync(join(root, 'app.db'))) args.push('--init')
  const child = spawn(python(), args, {
    cwd: componentDir(), detached: true, windowsHide: true, stdio: ['ignore', log, log],
    env: { ...process.env, APP_BACKEND_DATA_DIR: root, APP_BACKEND_PORT: '0',
      ...(!is.dev ? { PYTHONHOME: pythonHome, PYTHONPATH: '', PYTHONPYCACHEPREFIX: join(app.getPath('userData'), 'pycache') } : {}) }
  })
  closeSync(log)
  let startupError: Error | null = null
  child.on('error', error => { startupError = error })
  child.unref()
  const deadline = Date.now() + 90000
  while (Date.now() < deadline && !quitting) {
    if (startupError) throw startupError
    const info = await discover()
    if (info) return attach(info)
    if (child.exitCode !== null) {
      // A concurrent Agent start may own the lock. Allow discovery to settle.
      await new Promise(resolveWait => setTimeout(resolveWait, 500))
      const winner = await discover()
      if (winner) return attach(winner)
      throw new Error('Core 启动失败，请查看数据目录 runtime/studio-core.log')
    }
    await new Promise(resolveWait => setTimeout(resolveWait, 250))
  }
  throw new Error('Core 启动超时，请查看数据目录 runtime/studio-core.log')
}

export function initializeCoreAccess(): void {
  // Keep existing renderer API code; attach credentials only to this Core origin.
  session.defaultSession.webRequest.onBeforeSendHeaders((details, callback) => {
    if (connection && details.url.startsWith(`http://127.0.0.1:${connection.port}/`)) {
      details.requestHeaders.Authorization = `Bearer ${connection.tokens.studio}`
    }
    callback({ requestHeaders: details.requestHeaders })
  })
}

export async function ensureCore(): Promise<number> {
  if (quitting) throw new Error('Studio is closing')
  if (starting) return starting
  starting = (async () => {
    if (connection) {
      try {
        await call(connection, 'lease', { client_id: clientId })
        return connection.port
      } catch { connection = null }
    }
    return connectOrStart()
  })().finally(() => { starting = null })
  return starting
}

export async function releaseCore(): Promise<void> {
  quitting = true
  if (heartbeat) clearInterval(heartbeat)
  heartbeat = null
  const previous = connection
  connection = null
  if (previous) await call(previous, 'release', { client_id: clientId }).catch(() => {})
}
