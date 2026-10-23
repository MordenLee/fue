import { useEffect, useState } from 'react'
import { request } from '../../services/api'
import type { ActivityEvent } from '../../types/chat'
import { useI18n } from '../../i18n'

type Run = { run_id: string; state: string; created_at: number; error?: string; result?: { content?: string };
  events: { sequence: number; type: string; data: Record<string, unknown>; timestamp: number }[] }

export function ExecutionPanel({ conversationId, activity, busy }: {
  conversationId: number; activity: ActivityEvent[]; busy: boolean
}) {
  const { t } = useI18n()
  const activeId = activity.find(e => e.type === 'run_started')?.run_id
  const [run, setRun] = useState<Run | null>(null)
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState(false)
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    let alive = true
    let timer: ReturnType<typeof setTimeout>
    setRun(null); setError('')
    const refresh = async () => {
      try {
        const id = activeId || (await request<{ run_id: string }[]>(`/api/executions?conversation_id=${conversationId}`))[0]?.run_id
        if (!id || !alive) return
        const result = await request<Run>(`/api/executions/${encodeURIComponent(id)}`)
        if (!alive) return
        setRun(result); setError(''); setNow(Date.now())
        if (result.state === 'running') timer = setTimeout(() => void refresh(), 2000)
      } catch (e) {
        if (alive) { setError(String(e)); if (busy) timer = setTimeout(() => void refresh(), 2000) }
      }
    }
    void refresh()
    return () => { alive = false; clearTimeout(timer) }
  }, [conversationId, activeId, busy])
  if (!run && !busy && !error) return null
  const events = run?.events ?? []
  const usage = events.filter(e => e.type === 'usage_updated')
  const budget = events.find(e => e.type === 'budget')?.data
  const total = (kind: 'input' | 'output') => usage.reduce((n, e) => {
    const actual = e.data.usage as Record<string, number> | null
    return n + Number(actual?.[`${kind}_tokens`] ?? e.data[`${kind}_estimated`] ?? 0)
  }, 0)
  const input = total('input'), output = total('output')
  const estimated = usage.some(e => !e.data.usage)
  const stage = [...events].reverse().find(e => ['model_started', 'tool_started', 'tool_completed'].includes(e.type))
  return <div className="px-4 py-2 border-b border-neutral-200 dark:border-white/10 text-xs space-y-2" aria-live="polite">
    <button className="text-left w-full" onClick={() => setExpanded(!expanded)}>
      {t('execution.title')} · {t(`execution.${run?.state ?? 'running'}`)}
      {run?.state === 'running' && ` · ${Math.max(0, Math.floor(now / 1000 - run.created_at))}s`}
      {run?.state === 'running' && stage && ` · ${t(`working.events.${stage.type}`)}`}
      {' · '}{t('execution.models')}: {events.filter(e => e.type === 'model_started').length}
      {' · '}{t('execution.tools')}: {events.filter(e => e.type === 'tool_started').length}
    </button>
    <p>{usage.length ? `${t(estimated ? 'working.estimated' : 'working.actual')} token: ${input} / ${output}` : t('execution.awaiting_usage')}
      {budget && ` · ${t('execution.remaining')}: ${Math.max(0, Number(budget.input_limit) - input)} / ${Math.max(0, Number(budget.output_limit) - output)}`}</p>
    {expanded && <div className="space-y-2">
      <p className="break-all">{run?.run_id}</p><p>{t('execution.no_auto_retry')}</p>
      {run?.result?.content && <details><summary>{t('execution.saved')}</summary><pre className="whitespace-pre-wrap max-h-64 overflow-auto">{run.result.content}</pre></details>}
      {run?.error && <p>{run.error}</p>}
      {run?.state === 'running' && <button className="text-red-500" onClick={() => {
        void request(`/api/executions/${run.run_id}/cancel`, { method: 'POST' }).catch(e => setError(String(e)))
      }}>{t('execution.stop')}</button>}
    </div>}
    {error && <p className="text-amber-600">{error}</p>}
  </div>
}
