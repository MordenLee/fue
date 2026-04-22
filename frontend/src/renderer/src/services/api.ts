import type { SSEEvent } from '../types/chat'

// ─── Dynamic backend URL ───
// Resolved at startup via IPC from Electron main process.
// Falls back to env variable or default for non-Electron development.
let _baseUrl: string = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'
let _baseUrlReady: Promise<string>

if (window.api?.getBackendUrl) {
  // getBackendUrl() only resolves after the main process has confirmed the backend
  // is responding to /api/ping — no need to poll again here.
  _baseUrlReady = window.api.getBackendUrl().then((url) => {
    _baseUrl = url
    return url
  })
} else {
  _baseUrlReady = Promise.resolve(_baseUrl)
}

async function resolveBackendUrl(forceRefresh = false): Promise<string> {
  if (window.api?.getBackendUrl && forceRefresh) {
    _baseUrlReady = window.api.getBackendUrl().then((url) => {
      _baseUrl = url
      return url
    })
  }
  return _baseUrlReady
}

async function fetchWithBackendRetry(input: string, init?: RequestInit): Promise<Response> {
  await resolveBackendUrl()

  try {
    return await fetch(`${getBaseUrl()}${input}`, init)
  } catch (error) {
    if (!window.api?.getBackendUrl || !(error instanceof TypeError)) {
      throw error
    }

    await resolveBackendUrl(true)
    return fetch(`${getBaseUrl()}${input}`, init)
  }
}

/** Wait for the backend URL to be resolved before making API calls */
export function waitForBackend(): Promise<string> {
  return resolveBackendUrl()
}

function getBaseUrl(): string {
  return _baseUrl
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string
  ) {
    super(detail)
    this.name = 'ApiError'
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { ...init?.headers as Record<string, string> }
  if (init?.body && !(init.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
  }
  const res = await fetchWithBackendRetry(path, { ...init, headers })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new ApiError(res.status, body.detail ?? res.statusText)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export function streamRequest(
  path: string,
  body: object,
  onEvent: (event: SSEEvent) => void
): AbortController {
  const controller = new AbortController()

  ;(async () => {
    const res = await fetchWithBackendRetry(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal
    })

    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}))
      onEvent({ type: 'error', data: errBody.detail ?? res.statusText })
      return
    }

    const reader = res.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const raw = line.slice(6)

        if (raw === '[DONE]') {
          onEvent({ type: 'done' })
        } else if (raw.startsWith('[SEARCHING] ')) {
          try { onEvent({ type: 'searching', data: JSON.parse(raw.slice(12)) }) } catch { /* ignore parse error */ }
        } else if (raw.startsWith('[TOOL_CALL] ')) {
          onEvent({ type: 'tool_call', data: JSON.parse(raw.slice(12)) })
        } else if (raw.startsWith('[CITATIONS] ')) {
          onEvent({ type: 'citations', data: JSON.parse(raw.slice(12)) })
        } else if (raw.startsWith('[SUMMARY] ')) {
          onEvent({ type: 'summary', data: JSON.parse(raw.slice(10)) })
        } else if (raw.startsWith('[PROGRESS] ')) {
          onEvent({ type: 'progress', data: JSON.parse(raw.slice(11)) })
        } else if (raw === '[CLEAR]') {
          onEvent({ type: 'clear' })
        } else if (raw.startsWith('[REPLACE] ')) {
          try { onEvent({ type: 'replace', data: JSON.parse(raw.slice(10)) }) } catch { /* ignore parse error */ }
        } else if (raw.startsWith('[ERROR] ')) {
          onEvent({ type: 'error', data: raw.slice(8) })
        } else {
          onEvent({ type: 'token', data: raw })
        }
      }
    }
  })().catch((err) => {
    if (err.name !== 'AbortError') {
      onEvent({ type: 'error', data: err.message })
    }
  })

  return controller
}

export const api = {
  ping: () => request<{ message: string }>('/api/ping')
}
