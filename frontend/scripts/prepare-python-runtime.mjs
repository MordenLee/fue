import { cpSync, existsSync, mkdirSync, readFileSync, rmSync } from 'node:fs'
import { basename, dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const frontendDir = resolve(__dirname, '..')
const repoRoot = resolve(frontendDir, '..')
const venvDir = resolve(repoRoot, '.venv')
const venvConfigPath = join(venvDir, 'pyvenv.cfg')
const outputDir = resolve(frontendDir, 'build', 'python-runtime')

if (!existsSync(venvConfigPath)) {
  throw new Error(`Virtual environment config not found: ${venvConfigPath}`)
}

const cfg = readFileSync(venvConfigPath, 'utf8')
const homeLine = cfg
  .split(/\r?\n/)
  .map((line) => line.trim())
  .find((line) => line.startsWith('home = '))

if (!homeLine) {
  throw new Error(`Unable to locate Python home in ${venvConfigPath}`)
}

const pythonHome = homeLine.slice('home = '.length).trim()
if (!existsSync(pythonHome)) {
  throw new Error(`Python home does not exist: ${pythonHome}`)
}

function normalizePath(value) {
  return value.replace(/\\/g, '/')
}

function shouldSkipBaseRuntime(src) {
  const rel = normalizePath(relative(pythonHome, src))
  if (!rel || rel === '') return false

  const parts = rel.split('/')
  const name = basename(src)

  if (parts.includes('__pycache__')) return true
  if (name.endsWith('.pyc') || name.endsWith('.pyo')) return true
  if (rel.startsWith('Lib/site-packages')) return true
  if (rel.startsWith('Scripts')) return true
  if (rel.startsWith('Doc')) return true
  if (rel.startsWith('Tools')) return true
  if (rel.startsWith('share')) return true
  return false
}

function shouldSkipSitePackages(src) {
  const rel = normalizePath(relative(venvDir, src))
  if (!rel || rel === '') return false

  const parts = rel.split('/')
  const name = basename(src)

  if (parts.includes('__pycache__')) return true
  if (name.endsWith('.pyc') || name.endsWith('.pyo')) return true
  if (rel.startsWith('Lib/site-packages/pip')) return true
  if (/^Lib\/site-packages\/pip-[^/]+\.dist-info/.test(rel)) return true
  return false
}

rmSync(outputDir, { recursive: true, force: true })
mkdirSync(outputDir, { recursive: true })

console.log(`Preparing portable Python runtime from ${pythonHome}`)

cpSync(pythonHome, outputDir, {
  recursive: true,
  filter: (src) => !shouldSkipBaseRuntime(src)
})

const targetSitePackages = join(outputDir, 'Lib', 'site-packages')
mkdirSync(targetSitePackages, { recursive: true })
cpSync(join(venvDir, 'Lib', 'site-packages'), targetSitePackages, {
  recursive: true,
  filter: (src) => !shouldSkipSitePackages(src)
})

const venvShare = join(venvDir, 'share')
if (existsSync(venvShare)) {
  cpSync(venvShare, join(outputDir, 'share'), {
    recursive: true,
    filter: (src) => !shouldSkipSitePackages(src)
  })
}

console.log(`Portable Python runtime prepared at ${outputDir}`)