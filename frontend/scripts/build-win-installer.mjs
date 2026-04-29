import { copyFileSync, cpSync, existsSync, mkdirSync, readdirSync, rmSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'

const __dirname = dirname(fileURLToPath(import.meta.url))
const frontendDir = resolve(__dirname, '..')
const distDir = resolve(frontendDir, 'dist')
const stagingDir = resolve(frontendDir, 'dist-staging-win')

function runStep(command, args) {
  const result = spawnSync(command, args, {
    cwd: frontendDir,
    stdio: 'inherit',
    shell: process.platform === 'win32',
  })
  if (result.status !== 0) {
    process.exit(result.status ?? 1)
  }
}

function ensureCleanDir(dirPath) {
  rmSync(dirPath, { recursive: true, force: true })
  mkdirSync(dirPath, { recursive: true })
}

function copyIfExists(fromPath, toPath) {
  if (!existsSync(fromPath)) return false
  mkdirSync(dirname(toPath), { recursive: true })
  copyFileSync(fromPath, toPath)
  return true
}

ensureCleanDir(stagingDir)

runStep('npm', ['run', 'clean:dist-test-data'])
runStep('npm', ['run', 'check:providers'])
runStep('npm', ['run', 'build'])
runStep('npm', ['run', 'build:python-runtime'])
runStep('npx', ['electron-builder', '--win', '--config.directories.output=dist-staging-win'])

mkdirSync(distDir, { recursive: true })

const copied = []
for (const fileName of ['fue-1.0.1-setup.exe', 'fue-1.0.1-setup.exe.blockmap', 'latest.yml']) {
  if (copyIfExists(join(stagingDir, fileName), join(distDir, fileName))) {
    copied.push(fileName)
  }
}

const stagingUnpackedDir = join(stagingDir, 'win-unpacked')
const distUnpackedDir = join(distDir, 'win-unpacked')
if (existsSync(stagingUnpackedDir)) {
  try {
    rmSync(distUnpackedDir, { recursive: true, force: true })
    cpSync(stagingUnpackedDir, distUnpackedDir, { recursive: true })
    copied.push('win-unpacked/')
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error)
    console.warn(`[build-win-installer] skipped win-unpacked sync: ${reason}`)
  }
}

if (copied.length === 0) {
  console.error('[build-win-installer] No artifacts were copied back to dist.')
  process.exit(1)
}

console.log(`[build-win-installer] copied to dist: ${copied.join(', ')}`)

const stagingFiles = readdirSync(stagingDir)
console.log(`[build-win-installer] staging artifacts: ${stagingFiles.join(', ')}`)