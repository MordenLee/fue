/**
 * 打包前检查 shared/providers.json 中所有 api_key 均为空字符串。
 * 若发现非空 key，立即以非零退出码中止构建，防止密钥被打入安装包。
 */

import { readFileSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const providersPath = resolve(__dirname, '../../shared/providers.json')

let providers
try {
  providers = JSON.parse(readFileSync(providersPath, 'utf-8'))
} catch (e) {
  console.error(`[check-providers] 无法读取 ${providersPath}:`, e.message)
  process.exit(1)
}

const leaks = providers
  .filter((p) => p.api_key && p.api_key.trim() !== '')
  .map((p) => p.name)

if (leaks.length > 0) {
  console.error(
    '\n[check-providers] ❌ 构建中止！以下供应商的 api_key 非空，打包会泄露密钥：\n' +
      leaks.map((n) => `  - ${n}`).join('\n') +
      '\n\n请清空 shared/providers.json 中对应的 api_key 字段后再重新打包。\n'
  )
  process.exit(1)
}

console.log('[check-providers] ✅ shared/providers.json 中所有 api_key 均为空，可以安全打包。')
