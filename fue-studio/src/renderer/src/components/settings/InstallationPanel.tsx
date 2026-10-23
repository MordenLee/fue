import { useEffect, useState } from 'react'
import { Button } from '../ui/Button'
import { useI18n } from '../../i18n'

export function InstallationPanel() {
  const { t } = useI18n()
  const [info, setInfo] = useState<Awaited<ReturnType<typeof window.api.installationInfo>> | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  useEffect(() => { void window.api.installationInfo().then(setInfo).catch(e => setMessage(String(e))) }, [])
  async function run(action: 'skill' | 'workspace' | 'check') {
    setBusy(true)
    setMessage('')
    try {
      const result = await (action === 'skill' ? window.api.installHostSkill() : action === 'check' ? window.api.checkHostSkill() : window.api.openWorkspaceNextLaunch())
      if (result) setMessage(action === 'check' ? result : t(action === 'skill' ? 'installation.installed' : 'installation.selected', { path: result }))
      setInfo(await window.api.installationInfo())
    } catch (error) { setMessage(error instanceof Error ? error.message : String(error)) }
    finally { setBusy(false) }
  }
  return <section className="space-y-3 rounded-lg border border-neutral-200 dark:border-white/10 p-4">
    <h3 className="font-medium">{t('installation.title')}</h3>
    <p className="text-sm text-neutral-500">{t('installation.description')}</p>
    {info && <div className="space-y-1 text-sm break-all">
      <p>{info.name} · Core {info.version || '—'} · {t(info.connected ? 'installation.connected' : 'installation.disconnected')}</p>
      <p>{t('installation.workspace')}: {info.data_dir}</p>
      <p>Core: {info.core_dir}</p>
      {!info.registered && <p className="text-neutral-500">{t('installation.development')}</p>}
      {info.pending_data_dir && <p className="text-amber-600">{t('installation.pending', { path: info.pending_data_dir })}</p>}
    </div>}
    <div className="flex flex-wrap gap-2">
      <Button variant="secondary" disabled={busy} onClick={() => void run('skill')}>{t('installation.skill')}</Button>
      <Button variant="secondary" disabled={busy} onClick={() => void run('workspace')}>{t('installation.open')}</Button>
      <Button variant="secondary" disabled={busy} onClick={() => void run('check')}>{t('installation.check')}</Button>
    </div>
    {busy && <p role="status" className="text-sm">{t('installation.busy')}</p>}
    {message && <p role="status" className="text-sm whitespace-pre-wrap break-words">{message}</p>}
  </section>
}
