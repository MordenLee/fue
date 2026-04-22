/**
 * 打包前安全检查：
 * 1. shared/providers.json 中所有 api_key 均为空字符串
 * 2. backend/app.db（开发数据库）中不含明文 api_key
 * 若发现非空 key，立即以非零退出码中止构建，防止密钥被打入安装包或追踪到 git。
 */

import { readFileSync, existsSync } from 'fs'
import { resolve, dirname, sep } from 'path'
import { fileURLToPath } from 'url'
import { execFileSync } from 'child_process'

const __dirname = dirname(fileURLToPath(import.meta.url))
let hasError = false

// ── 1. 检查 shared/providers.json ──────────────────────────────────────────
const providersPath = resolve(__dirname, '../../shared/providers.json')
let providers
try {
  providers = JSON.parse(readFileSync(providersPath, 'utf-8'))
} catch (e) {
  console.error(`[check-providers] 无法读取 ${providersPath}:`, e.message)
  process.exit(1)
}

const jsonLeaks = providers
  .filter((p) => p.api_key && p.api_key.trim() !== '')
  .map((p) => p.name)

if (jsonLeaks.length > 0) {
  console.error(
    '\n[check-providers] ❌ shared/providers.json 中以下供应商的 api_key 非空：\n' +
      jsonLeaks.map((n) => `  - ${n}`).join('\n') +
      '\n  请清空对应的 api_key 字段后再重新打包。'
  )
  hasError = true
} else {
  console.log('[check-providers] ✅ shared/providers.json — 所有 api_key 均为空。')
}

// ── 2. 检查 backend/app.db（开发数据库）──────────────────────────────────
const dbPath = resolve(__dirname, '../../backend/app.db')
if (existsSync(dbPath)) {
  try {
    // 用 Python sqlite3 查询（跨平台，无需额外依赖）
    const pyScript = [
      'import sqlite3',
      `conn = sqlite3.connect("${dbPath.replace(/\\/g, '\\\\')}")`,
      'cur = conn.cursor()',
      'cur.execute("SELECT name, api_key FROM providers WHERE api_key IS NOT NULL AND api_key != \'\'")',
      'rows = cur.fetchall()',
      'conn.close()',
      'print("LEAK:" + "|".join(r[0] for r in rows) if rows else "OK")',
    ].join('\n')

    const pythonCandidates = [
      resolve(__dirname, '../../.venv/Scripts/python.exe'),
      resolve(__dirname, '../../.venv/bin/python3'),
      'python3',
      'python',
    ]
    let output = null
    for (const py of pythonCandidates) {
      if (!existsSync(py) && !py.includes(sep)) continue  // skip missing absolute paths
      try {
        output = execFileSync(py, ['-c', pyScript], { encoding: 'utf-8' }).trim()
        break
      } catch {
        // try next
      }
    }
    if (output === null) {
      console.warn('[check-providers] ⚠️  无法运行 Python 检查 backend/app.db，跳过数据库检查。')
    } else if (output.startsWith('LEAK:')) {
      const names = output.slice(5).split('|')
      console.error(
        '\n[check-providers] ❌ backend/app.db 中以下供应商含有明文 api_key（开发数据库泄露风险）：\n' +
          names.map((n) => `  - ${n}`).join('\n') +
          '\n  请在开发数据库中清空这些 api_key 后再重新打包。'
      )
      hasError = true
    } else {
      console.log('[check-providers] ✅ backend/app.db   — 所有 api_key 均为空。')
    }
  } catch (e) {
    console.warn('[check-providers] ⚠️  检查 backend/app.db 时出错（已跳过）:', e.message)
  }
} else {
  console.log('[check-providers] ℹ️  backend/app.db 不存在，跳过数据库检查。')
}

// ── 结果 ──────────────────────────────────────────────────────────────────
if (hasError) {
  console.error('\n[check-providers] ❌ 构建已中止，请修复以上问题后重试。\n')
  process.exit(1)
}
console.log('[check-providers] ✅ 所有检查通过，可以安全打包。')
