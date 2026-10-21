/** Validate packaged provider presets and exclusions without touching development data. */
import { readFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import yaml from 'js-yaml'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const presets = JSON.parse(readFileSync(resolve(scriptDir, '../../shared/providers.json'), 'utf8'))
if (presets.some((provider) => provider.api_key?.trim())) {
  throw new Error('shared/providers.json contains a nonempty API key; packaging stopped.')
}

// A developer database may contain credentials. It must never be shipped.
// Check the actual packaging rules instead of requiring deletion of local keys.
const config = yaml.load(readFileSync(resolve(scriptDir, '../electron-builder.yml'), 'utf8'))
const backend = config.extraResources?.find((resource) => resource.from === '../backend')
const required = ['!app.db*', '!chroma_data/**', '!logs/**', '!.env*']
if (!backend || required.some((rule) => !backend.filter?.includes(rule))) {
  throw new Error('Backend packaging must exclude databases, vector data, logs and environment files.')
}
console.log('[check-providers] Provider presets are clean and development data is excluded.')
