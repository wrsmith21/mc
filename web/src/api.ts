/* eslint-disable @typescript-eslint/no-explicit-any */
export type Json = any

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function call(path: string, init?: RequestInit): Promise<Json> {
  const res = await fetch(path, { credentials: 'include', ...init })
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail ?? detail
    } catch {
      /* non-JSON error body */
    }
    if (res.status === 401) window.dispatchEvent(new Event('mc-auth-required'))
    throw new ApiError(res.status, detail)
  }
  return res.json()
}

const post = (path: string, body: unknown = {}) =>
  call(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export const api = {
  meta: () => call('/api/meta'),
  queue: () => call('/api/queue'),
  summary: () => call('/api/summary'),
  invoice: (id: string) => call(`/api/invoices/${id}`),
  audit: (id: string) => call(`/api/invoices/${id}/audit`),
  requestReceipt: (id: string, actor: string) => post(`/api/invoices/${id}/receipt/request`, { actor }),
  confirmReceipt: (id: string, by: string, note: string) => post(`/api/invoices/${id}/receipt/confirm`, { by, note }),
  tasks: (person?: string) => call(`/api/tasks${person ? `?person=${person}` : ''}`),
  decide: (id: string, body: Json) => post(`/api/invoices/${id}/decision`, body),
  approve: (id: string, approver: string) => post(`/api/invoices/${id}/approve`, { approver }),
  anomalies: () => call('/api/anomalies'),
  procurement: () => call('/api/insights/procurement'),
  vendor: (id: string) => call(`/api/vendors/${id}`),
  reset: () => post('/api/reset'),
  login: (passcode: string) => post('/api/login', { passcode }),
  wildcard: async (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return call('/api/wildcard', { method: 'POST', body: fd })
  },
}

export function runStream(id: string, pace: number, onEvent: (e: Json) => void): () => void {
  const es = new EventSource(`/api/invoices/${id}/run?pace=${pace}`, { withCredentials: true })
  es.onmessage = (m) => {
    const ev = JSON.parse(m.data)
    onEvent(ev)
    if (ev.type === 'result') es.close()
  }
  es.onerror = () => {
    es.close()
    onEvent({ type: 'error' })
  }
  return () => es.close()
}
