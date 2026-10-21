import { request } from './api'
import type { ActivityEvent } from '../types/chat'

export interface WorkingState {
  summary: { id: string; markdown: string; projection_state: string } | null
  pairs: Array<{ id: string; question: string; position: number; material: { id: string; status: string; decision: string; result: string } | null }>
  next_offset: number | null
  events: Array<{ id: string; sequence: number; type: string; timestamp: number; data: Record<string, unknown> }>
  usage: Array<ActivityEvent & { run_id: string }>
}
export interface MemoryPage { text: string; next_offset: number | null; total_chars: number }
export const workingMemory = {
  get: (cid: number, offset = 0) => request<WorkingState>(`/api/memory/conversations/${cid}/context?offset=${offset}`),
  material: (cid: number, pair_id: string, status: 'pending' | 'completed', decision: string, result: string) =>
    request(`/api/memory/conversations/${cid}/material`, { method: 'PUT', body: JSON.stringify({ pair_id, status, decision, result }) }),
  read: (cid: number, ref: string, offset = 0) => request<MemoryPage>(`/api/memory/conversations/${cid}/read?ref=${encodeURIComponent(ref)}&offset=${offset}`)
}
