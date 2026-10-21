import { existsSync, rmSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const frontendDir = resolve(__dirname, '..')

const targets = [
  resolve(frontendDir, 'dist', 'test-data'),
  resolve(frontendDir, 'dist', 'test-data2'),
  resolve(frontendDir, 'dist', '_fresh-test-data'),
  resolve(frontendDir, 'dist', '_fresh-test-data-verify')
]

let removedCount = 0

for (const target of targets) {
  if (!existsSync(target)) continue
  try {
    rmSync(target, { recursive: true, force: true })
    removedCount += 1
    console.log(`[clean-dist-test-data] removed ${target}`)
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    console.warn(`[clean-dist-test-data] skipped ${target}: ${message}`)
  }
}

if (removedCount === 0) {
  console.log('[clean-dist-test-data] no test-data directories found')
}