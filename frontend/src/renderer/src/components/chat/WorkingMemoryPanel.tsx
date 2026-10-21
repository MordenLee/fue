import { useEffect, useState } from 'react'
import { workingMemory } from '../../services/workingMemory'
import type { WorkingState, MemoryPage } from '../../services/workingMemory'
import type { ActivityEvent } from '../../types/chat'
import { useI18n } from '../../i18n'

export function WorkingMemoryPanel({ conversationId, activity, busy, revision }: {
  conversationId: number; activity: ActivityEvent[]; busy: boolean; revision: number
}) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const [state, setState] = useState<WorkingState | null>(null)
  const [offset, setOffset] = useState(0)
  const [editing, setEditing] = useState<string | null>(null)
  const [result, setResult] = useState('')
  const [decision, setDecision] = useState('undecided')
  const [error, setError] = useState('')
  const [page, setPage] = useState<MemoryPage | null>(null)
  const [ref, setRef] = useState('')
  const [saving, setSaving] = useState(false)
  useEffect(() => { setState(null); setOffset(0); setPage(null); setEditing(null); setError('') }, [conversationId])
  useEffect(() => {
    if (!open) return
    let active = true
    const refresh = () => { void workingMemory.get(conversationId, offset).then(s => { if (active) setState(s) }).catch(e => { if (active) setError(String(e.message ?? e)) }) }
    refresh()
    const timer = window.setInterval(refresh, busy ? 5000 : 15000)
    return () => { active = false; window.clearInterval(timer) }
  }, [conversationId, offset, open, busy, revision])
  const refresh = async () => setState(await workingMemory.get(conversationId, offset))
  const read = async (source: string, next = 0) => {
    try { setError(''); setPage(await workingMemory.read(conversationId, source, next)); setRef(source) }
    catch (e) { setError(e instanceof Error ? e.message : String(e)) }
  }
  const update = async (id: string, status: 'pending' | 'completed') => {
    setSaving(true)
    try { setError(''); await workingMemory.material(conversationId, id, status, decision, result); setEditing(null); await refresh() }
    catch (e) { setError(e instanceof Error ? e.message : String(e)) }
    finally { setSaving(false) }
  }
  const label = (e: ActivityEvent) => {
    const text = t(`working.events.${e.type}`)
    if (e.type === 'usage_updated') {
      return `${text} · ${e.category ?? ''} · ${e.usage ? t('working.actual') : t('working.estimated')} ${e.usage?.input_tokens ?? e.input_estimated ?? '?'} / ${e.usage?.output_tokens ?? e.output_estimated ?? '?'} token`
    }
    return `${text}${e.name ? ` · ${e.name}` : ''}${e.step ? ` #${e.step}` : ''}${e.count ? ` · ${e.count}` : ''}${e.status ? ` · ${e.status}` : ''}`
  }
  return <div className="border-b border-neutral-200 dark:border-white/10 text-xs">
    <button type="button" className="w-full px-4 py-2 text-left text-neutral-500 hover:text-blue-500" onClick={() => setOpen(!open)}>
      {open ? '▾' : '▸'} {t('working.panel')}{activity.length > 0 && ` · ${label(activity[activity.length - 1])}`}
    </button>
    {open && <div className="max-h-80 overflow-y-auto px-4 pb-3 space-y-3">
      {error && <p role="alert" className="text-red-500">{error}</p>}
      {activity.length > 0 && <ol className="space-y-1">{activity.map((e, i) => <li key={i}>{label(e)}</li>)}</ol>}
      <p className="text-neutral-500">{t('working.material_hint')}</p>
      <details><summary className="cursor-pointer">{t('working.summary')}</summary>
        <pre className="whitespace-pre-wrap break-words mt-2">{state?.summary?.markdown ?? t('working.no_summary')}</pre>
        {state?.summary && <p className="break-all">{t('working.version')}: {state.summary.id}</p>}
        {[...new Set(state?.summary?.markdown.match(/chat:[A-Za-z0-9-]+/g) ?? [])].slice(0, 10).map(source =>
          <button key={source} className="mr-3 text-blue-500" onClick={() => void read(source)}>{t('working.read')} {source.slice(0, 17)}…</button>)}
        {state?.summary && <p>{t('working.file_state')}: {state.summary.projection_state}</p>}
      </details>
      <details><summary className="cursor-pointer">{t('working.materials')}</summary>
        {state?.pairs.map(p => <div key={p.id} className="py-2 border-b border-neutral-200 dark:border-white/10 space-y-2">
          <p className="whitespace-pre-wrap">{p.question}</p>
          <div className="flex flex-wrap gap-3">
            <button className="text-blue-500" onClick={() => void read(`chat:${p.id}`)}>{t('working.read')}</button>
            <button disabled={busy || saving} className="text-blue-500 disabled:opacity-40" onClick={() => {
              setEditing(p.id); setResult(p.material?.result ?? ''); setDecision(p.material?.decision ?? 'undecided')
            }}>{p.material?.status === 'completed' ? t('working.edit_result') : t('working.complete')}</button>
          </div>
          {p.material?.status === 'completed' && <p>{t('working.completed')}: {p.material.result}</p>}
          {editing === p.id && <div className="space-y-2">
            <select className="bg-white dark:bg-neutral-800 border rounded p-1" value={decision} onChange={e => setDecision(e.target.value)}>
              {['undecided', 'selected', 'not_selected'].map(v => <option key={v} value={v}>{t(`working.${v}`)}</option>)}
            </select>
            <textarea maxLength={800} className="w-full bg-transparent border rounded p-2" rows={3} value={result} onChange={e => setResult(e.target.value)} placeholder={t('working.result_hint')} />
            <div className="flex gap-4"><button disabled={saving || !result.trim()} className="text-blue-500 disabled:opacity-40" onClick={() => void update(p.id, 'completed')}>{t('working.save_result')}</button>
              <button disabled={saving} onClick={() => void update(p.id, 'pending')}>{t('working.restore')}</button>
              <button onClick={() => setEditing(null)}>{t('common.cancel')}</button></div>
          </div>}
        </div>)}
        <div className="flex gap-4 mt-2"><button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 20))}>{t('working.previous')}</button>
          <button disabled={state?.next_offset == null} onClick={() => setOffset(state?.next_offset ?? 0)}>{t('working.next')}</button></div>
      </details>
      <details><summary className="cursor-pointer">{t('working.records')}</summary>
        {state?.events.map(e => <div key={e.id} className="py-1">#{e.sequence} {t(`working.events.${e.type}`)}
          {e.type === 'compaction_completed' && <button className="ml-3 text-blue-500" onClick={() => void read(`compaction:${e.id}`)}>{t('working.read')}</button>}
        </div>)}
        <p>{t('working.usage_hint')}</p>
        {state?.usage.slice(0, 20).map((u, i) => <p key={i}>{u.category} · {u.status} · {u.usage ? t('working.actual') : t('working.estimated')} {u.usage?.input_tokens ?? u.input_estimated} / {u.usage?.output_tokens ?? u.output_estimated} token · {u.elapsed_ms} ms</p>)}
      </details>
      {page && <div className="border rounded p-2 space-y-2">
        <p>{ref}</p><pre className="whitespace-pre-wrap break-words">{page.text}</pre>
        {[...new Set(page.text.match(/chat:[A-Za-z0-9-]+/g) ?? [])].map(source => <button key={source} className="mr-3 text-blue-500" onClick={() => void read(source)}>{t('working.read')} {source.slice(0, 17)}…</button>)}
        {page.next_offset != null && <button className="text-blue-500" onClick={() => void read(ref, page.next_offset!)}>{t('working.next')}</button>}
        <button className="ml-3" onClick={() => setPage(null)}>{t('common.close')}</button>
      </div>}
    </div>}
  </div>
}
