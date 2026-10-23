import { useEffect, useState, type ComponentType } from 'react'
import { waitForBackend } from './services/api'

export function Startup() {
  const [Application, setApplication] = useState<ComponentType | null>(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [seconds, setSeconds] = useState(0)
  const english = localStorage.getItem('language') === 'en'
  useEffect(() => {
    let alive = true
    const started = performance.now()
    setError(''); setSeconds(0)
    const timer = setInterval(() => setSeconds(Math.floor((performance.now() - started) / 1000)), 1000)
    // Fetch the UI chunk while Core starts. No business requests mount until ready.
    void Promise.all([waitForBackend(attempt > 0), import('./ReadyApp')]).then(([, module]) => {
      if (alive) {
        console.info(`[startup] application-ready: ${Math.round(performance.now() - started)}ms`)
        setApplication(() => module.default)
      }
    }).catch(reason => { if (alive) setError(reason instanceof Error ? reason.message : String(reason)) })
      .finally(() => clearInterval(timer))
    return () => { alive = false; clearInterval(timer) }
  }, [attempt])
  if (Application) return <Application />
  return <div className="h-screen bg-neutral-900 text-neutral-100 flex flex-col">
    <div className="h-7 shrink-0 drag-region" />
    <main className="flex-1 flex flex-col items-center justify-center gap-4 p-8" aria-live="polite">
      <h1 className="text-2xl font-semibold">FUE</h1>
      <p>{error ? (english ? 'Unable to start' : '启动未完成') : (english ? 'Opening your workspace…' : '正在连接资料库并加载界面…')}</p>
      {!error && <p className="text-sm text-neutral-400">{seconds}s · {english ? 'First startup may take longer.' : '首次启动可能需要较长时间，请稍候。'}</p>}
      {error && <><p className="max-w-xl text-sm text-red-300 break-words select-text">{error}</p>
        <button className="px-4 py-2 rounded bg-blue-600" onClick={() => setAttempt(n => n + 1)}>{english ? 'Retry' : '重试'}</button></>}
    </main>
  </div>
}
