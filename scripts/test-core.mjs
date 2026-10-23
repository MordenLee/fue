import { existsSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const local = resolve(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python3')
const result = spawnSync(existsSync(local) ? local : process.platform === 'win32' ? 'python' : 'python3',
  ['-m', 'unittest', 'discover', '-s', 'fue-core/tests'], { cwd: root, stdio: 'inherit', windowsHide: true })
if (result.error) console.error(result.error.message)
process.exit(result.status ?? 1)
