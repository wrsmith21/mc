/* eslint-disable @typescript-eslint/no-explicit-any */
export type Json = any

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export const OFFLINE = "Can't reach the server. Check the connection and try again."

async function call(path: string, init?: RequestInit): Promise<Json> {
  let res: Response
  try {
    res = await fetch(path, { credentials: 'include', ...init })
  } catch {
    throw new ApiError(0, OFFLINE)
  }
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail ?? detail
    } catch {
      /* non-JSON error body */
    }
    if (res.status === 401 && detail === 'passcode required') window.dispatchEvent(new Event('mc-auth-required'))
    if (res.status === 401 && detail.startsWith('Sign in')) window.dispatchEvent(new Event('mc-signin-required'))
    throw new ApiError(res.status, detail)
  }
  return res.json()
}

const post = (path: string, body: unknown = {}) =>
  call(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export const api = {
  meta: () => call('/api/meta'),
  session: () => call('/api/session'),
  signIn: (person_id: string) => post('/api/session', { person_id }),
  people: () => call('/api/people'),
  queue: () => call('/api/queue'),
  summary: () => call('/api/summary'),
  work: () => call('/api/work'),
  invoice: (id: string) => call(`/api/invoices/${id}`),
  audit: (id: string) => call(`/api/invoices/${id}/audit`),
  requestReceipt: (id: string) => post(`/api/invoices/${id}/receipt/request`),
  confirmReceipt: (id: string, note: string, by?: string, token?: string) => post(`/api/invoices/${id}/receipt/confirm`, { note, by, token }),
  tasks: (person?: string) => call(`/api/tasks${person ? `?person=${person}` : ''}`),
  decide: (id: string, body: Json) => post(`/api/invoices/${id}/decision`, body),
  approve: (id: string) => post(`/api/invoices/${id}/approve`),
  callback: (vendorId: string, outcome: string, note: string) => post(`/api/vendors/${vendorId}/callback`, { outcome, note }),
  onboard: (id: string, tax_id: string, category: string) => post(`/api/invoices/${id}/onboard`, { tax_id, category }),
  requestPo: (vendor_id: string, kind: string) => post('/api/procurement/requests', { vendor_id, kind }),
  advanceClock: (hours: number) => post('/api/clock/advance', { hours }),
  anomalies: () => call('/api/anomalies'),
  cases: () => call('/api/cases'),
  caseDetail: (id: string) => call(`/api/cases/${id}`),
  caseAction: (id: string, action: string, body: Json = {}) => post(`/api/cases/${id}/${action}`, body),
  bulkPrepare: (min_confidence: number) => post('/api/cases/bulk-prepare', { min_confidence }),
  exportCases: (kind: 'gl' | 'cash') => post('/api/cases/export', { kind }),
  close: () => call('/api/close'),
  model: () => call('/api/model'),
  agents: () => call('/api/agents'),
  policies: () => call('/api/policies'),
  updatePolicies: (changes: Record<string, number>, reason: string) => post('/api/policies', { changes, reason }),
  auditLog: (params = '') => call(`/api/audit${params}`),
  operations: () => call('/api/operations'),
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

/** Server-sent events: each step and tool call arrives the moment the agent completes it. */
export function stream(path: string, onEvent: (e: Json) => void, done: (e: Json) => boolean): () => void {
  const es = new EventSource(path, { withCredentials: true })
  es.onmessage = (m) => {
    const ev = JSON.parse(m.data)
    onEvent(ev)
    if (done(ev)) es.close()
  }
  es.onerror = () => {
    es.close()
    onEvent({ type: 'error', message: 'Connection to the agent closed' })
  }
  return () => es.close()
}

export const runStream = (id: string, onEvent: (e: Json) => void) =>
  stream(`/api/invoices/${id}/run`, onEvent, (e) => e.type === 'result' || e.type === 'error')

export const mailboxStream = (onEvent: (e: Json) => void) =>
  stream('/api/mailbox/run', onEvent, (e) => e.type === 'done')
