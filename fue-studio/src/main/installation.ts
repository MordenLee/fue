import { app, dialog } from 'electron'
import { execFile } from 'child_process'
import { existsSync, writeFileSync, readFileSync } from 'fs'
import { join } from 'path'
import { is } from '@electron-toolkit/utils'

export type Runtime = { core_dir: string; python: string; python_home?: string | null; version?: string; api_version?: number; source_revision?: string; managed?: boolean }
type Workspace = { id?: string; name?: string; data_dir: string; valid?: boolean; error?: string }
type Inventory = { default_workspace: string | null; workspaces: Workspace[]; candidates: Workspace[]; runtime: Runtime | null; bundled_revision?: string }
export type Installation = { runtime: Runtime; data_dir: string; initialize: boolean; registered: boolean }
let chosen: Installation | null = null

export function cleanPythonEnv(runtime: Runtime): NodeJS.ProcessEnv {
  const env = { ...process.env }
  delete env.PYTHONHOME
  delete env.PYTHONPATH
  if (runtime.python_home) env.PYTHONHOME = runtime.python_home
  env.PYTHONIOENCODING = 'utf-8'
  return env
}

function bundled(): Runtime {
  const root = join(__dirname, '..', '..', '..')
  const home = join(process.resourcesPath, 'python')
  return {
    core_dir: is.dev ? join(root, 'fue-core') : join(process.resourcesPath, 'core'),
    python: is.dev ? (process.platform === 'win32' ? join(root, '.venv', 'Scripts', 'python.exe') : join(root, '.venv', 'bin', 'python3'))
      : (process.platform === 'win32' ? join(home, 'python.exe') : join(home, 'bin', 'python3')),
    python_home: is.dev ? null : home
  }
}

function command<T>(args: string[], runtime = bundled()): Promise<T> {
  return new Promise((resolve, reject) => {
    execFile(runtime.python, [join(runtime.core_dir, 'fue.py'), 'installation', ...args],
      { cwd: runtime.core_dir, env: cleanPythonEnv(runtime), windowsHide: true, timeout: 600000, maxBuffer: 2 * 1024 * 1024 },
      (error, stdout, stderr) => {
        try {
          const result = JSON.parse(stdout)
          if (!result.ok) reject(new Error(result.error))
          else resolve(result.data as T)
        } catch { reject(new Error(error?.message || stderr || 'Invalid installation response')) }
      })
  })
}

async function chooseExisting(): Promise<string> {
  const result = await dialog.showOpenDialog({ title: '打开已有 FUE 资料库目录（包含 app.db）', properties: ['openDirectory'] })
  if (result.canceled || !result.filePaths[0]) throw new Error('已取消资料库选择')
  return result.filePaths[0]
}

export async function prepareInstallation(): Promise<Installation> {
  if (chosen) return chosen
  const local = bundled()
  const selectionPath = join(app.getPath('userData'), 'workspace-selection.json')
  const savedSelection = existsSync(selectionPath) ? JSON.parse(readFileSync(selectionPath, 'utf-8')) as { data_dir: string } : null
  // Development checkout remains isolated unless registry use was explicitly requested.
  if (is.dev && !process.env.FUE_REGISTRY_PATH && process.env.FUE_USE_REGISTERED_WORKSPACE !== '1' && !savedSelection) {
    const repo = join(__dirname, '..', '..', '..')
    const projectSelection = join(repo, '.fue-workspace.json')
    const selected = existsSync(projectSelection) ? (JSON.parse(readFileSync(projectSelection, 'utf-8')) as { data_dir: string }).data_dir : null
    if (selected && !existsSync(join(selected, 'app.db'))) throw new Error('开发资料库已丢失，不会新建空库替代。')
    const root = process.env.FUE_DATA_DIR || process.env.APP_BACKEND_DATA_DIR || selected ||
      (existsSync(join(repo, 'backend', 'app.db')) ? join(repo, 'backend') : join(repo, 'workspaces', 'development'))
    chosen = { runtime: local, data_dir: root, initialize: !existsSync(join(root, 'app.db')), registered: false }
    return chosen
  }
  const inventory = await command<Inventory>(['inspect'])
  let root = process.env.FUE_DATA_DIR || process.env.APP_BACKEND_DATA_DIR || savedSelection?.data_dir
  let initialize = false
  let makeDefault = false
  if (!root) {
    const entries = [...inventory.workspaces, ...inventory.candidates]
    if (entries.length === 1) {
      if (entries[0].valid === false) throw new Error(entries[0].error || '登记的资料库不可用')
      root = entries[0].data_dir
    } else if (entries.length > 1) {
      const result = await dialog.showMessageBox({ type: 'question', title: '选择 FUE 资料库',
        message: '检测到多个资料库，请选择本次打开的资料库。不会合并或复制数据。',
        buttons: [...entries.map(w => `${w.name || '资料库'} — ${w.data_dir}`), '打开其他已有目录', '取消'],
        cancelId: entries.length + 1, noLink: true })
      if (result.response > entries.length) throw new Error('已取消资料库选择')
      root = result.response === entries.length ? await chooseExisting() : entries[result.response].data_dir
      makeDefault = true
    } else {
      const result = await dialog.showMessageBox({ type: 'question', title: '开始使用 FUE',
        message: '尚未登记资料库。如果曾通过 Agent 使用 FUE，请打开原来的数据目录。',
        buttons: ['创建默认资料库', '打开已有资料库', '取消'], cancelId: 2, noLink: true })
      if (result.response === 2) throw new Error('已取消初始化')
      initialize = result.response === 0
      root = initialize ? join(app.getPath('userData'), 'workspaces', 'default') : await chooseExisting()
      makeDefault = true
    }
  }
  const args = ['install', '--data-dir', root, '--source-core', local.core_dir]
  if (inventory.runtime?.managed && inventory.runtime.source_revision !== inventory.bundled_revision) {
    const decision = await dialog.showMessageBox({ type: 'question', title: '更新 FUE Core',
      message: '此 Studio 携带了新的 Core 实现。更新前请结束其他宿主中的 FUE 任务；资料库将在需要迁移时备份。',
      buttons: ['更新 Core 并启动', '取消'], cancelId: 1, defaultId: 0 })
    if (decision.response !== 0) throw new Error('已取消 Core 更新')
    args.push('--upgrade')
  }
  if (initialize) args.push('--init')
  if (makeDefault) args.push('--make-default')
  if (is.dev) args.push('--register-existing', '--python', local.python)
  else args.push('--bundle-python', local.python_home!)
  const result = await command<{ runtime: Runtime; data_dir: string }>(args)
  if (makeDefault) writeFileSync(selectionPath, JSON.stringify({ data_dir: result.data_dir }))
  chosen = { runtime: result.runtime, data_dir: result.data_dir, initialize: false, registered: true }
  return chosen
}

export async function installationInfo() {
  const state = await prepareInstallation()
  const selected = join(app.getPath('userData'), 'workspace-selection.json')
  const pending = existsSync(selected) ? (JSON.parse(readFileSync(selected, 'utf-8')) as { data_dir: string }).data_dir : null
  let version = '', connected = false
  try { const status = await coreCommand(state, ['status', '--json']); version = String(status.version ?? ''); connected = true } catch { /* Show disconnected state without losing workspace identity. */ }
  return { data_dir: state.data_dir, core_dir: state.runtime.core_dir, registered: state.registered,
    name: state.data_dir.split(/[\\/]/).pop() || state.data_dir, version, connected,
    pending_data_dir: pending && pending !== state.data_dir ? pending : null }
}

export async function installHostSkill(): Promise<string | null> {
  const selection = await dialog.showOpenDialog({ title: '选择宿主的 skills 目录（将在其中创建 fue-skill）', properties: ['openDirectory', 'createDirectory'] })
  if (selection.canceled) return null
  const current = await prepareInstallation()
  const skill = is.dev ? join(__dirname, '..', '..', '..', 'fue-skill') : join(process.resourcesPath, 'fue-skill')
  const args = ['install', '--data-dir', current.data_dir, '--skill-source', skill, '--skill-dir', selection.filePaths[0], '--update-skill']
  if (!current.registered) args.push('--register-existing', '--python', current.runtime.python)
  const result = await command<{ skill: string }>(args)
  return result.skill
}

export async function openWorkspaceNextLaunch(): Promise<string | null> {
  const root = await chooseExisting()
  await command(['register', '--data-dir', root, '--make-default'])
  writeFileSync(join(app.getPath('userData'), 'workspace-selection.json'), JSON.stringify({ data_dir: root }))
  return root
}

function coreCommand(state: Installation, args: string[]): Promise<Record<string, unknown>> {
  return new Promise((resolve, reject) => execFile(state.runtime.python,
    [join(state.runtime.core_dir, 'fue.py'), '--data-dir', state.data_dir, ...args],
    { env: cleanPythonEnv(state.runtime), windowsHide: true, timeout: 30000 }, (error, stdout) => {
      try { const result = JSON.parse(stdout); if (error || !result.ok) reject(new Error(result.error || 'Core unavailable')); else resolve(result.data) }
      catch { reject(new Error('Core connection check failed')) }
    }))
}

export async function checkHostSkill(): Promise<string | null> {
  const selection = await dialog.showOpenDialog({ title: '选择已安装的 fue-skill 目录', properties: ['openDirectory'] })
  if (selection.canceled) return null
  const script = join(selection.filePaths[0], 'scripts', 'fue.py')
  if (!existsSync(script)) throw new Error('所选目录没有 scripts/fue.py，请选择 fue-skill 目录。')
  const state = await prepareInstallation()
  return new Promise((resolve, reject) => execFile(state.runtime.python, [script, '--auto-start', 'status', '--json'],
    { env: cleanPythonEnv(state.runtime), windowsHide: true, timeout: 120000 }, (error, stdout) => {
      try { const result = JSON.parse(stdout); if (error || !result.ok) reject(new Error(JSON.stringify(result.error || '连接失败')))
        else resolve(`连接成功 · Core ${result.data.version} · ${result.data.data_dir}`) }
      catch { reject(new Error('Skill 连接检测失败，请检查安装目录和资料库配置。')) }
    }))
}
