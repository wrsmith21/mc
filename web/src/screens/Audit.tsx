import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Json } from '../api'
import { dateTime, num } from '../format'

function target(key: string) {
  if (key.startsWith('IN-') || key.startsWith('WC-')) return <Link to={`/invoice/${key}`}>{key}</Link>
  if (/^(JR|AP|CA)-/.test(key)) return <Link to={`/close?case=${key}`}>{key}</Link>
  return <span className="muted">{key}</span>
}

function summary(p: Json) {
  if (!p || typeof p !== 'object') return ''
  const v = p.reason ?? p.note ?? p.detail ?? p.title ?? p.lesson ?? p.action ?? p.status ?? p.outcome ?? ''
  return typeof v === 'string' ? v : JSON.stringify(v)
}

export default function Audit() {
  const [data, setData] = useState<Json | null>(null)
  const [kind, setKind] = useState('')
  const [who, setWho] = useState('')

  useEffect(() => {
    const q = new URLSearchParams()
    if (kind) q.set('kind', kind)
    if (who) q.set('actor', who)
    api.auditLog(q.toString() ? `?${q}` : '').then(setData)
  }, [kind, who])

  if (!data) return <p className="muted">Loading the audit log…</p>
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Audit log</h1>
          <p>Every action by the agent and by people, including actions the server refused, newest first. Per-invoice SOX evidence packs are generated from the same record.</p>
        </div>
        <span className="muted small">{num(data.total)} events</span>
      </div>
      <div className="filters">
        <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Event type" className="select">
          <option value="">All event types</option>
          {data.kinds.map((k: string) => <option key={k} value={k}>{k.replace(/_/g, ' ').toLowerCase()}</option>)}
        </select>
        <button type="button" className={kind === 'ACCESS_DENIED' ? 'on' : ''} onClick={() => setKind(kind === 'ACCESS_DENIED' ? '' : 'ACCESS_DENIED')}>Refused actions</button>
        <button type="button" className={who === 'AGENT' ? 'on' : ''} onClick={() => setWho(who === 'AGENT' ? '' : 'AGENT')}>Agent only</button>
      </div>
      <div className="table-wrap">
        <table className="grid">
          <thead><tr><th>When</th><th>Who</th><th>What</th><th>On</th><th>Detail</th></tr></thead>
          <tbody>
            {data.events.map((e: Json) => (
              <tr key={e.id} className={e.kind === 'ACCESS_DENIED' ? 'denied' : ''}>
                <td className="small">{dateTime(e.ts)}</td>
                <td>{e.actor_name}</td>
                <td><b>{e.kind.replace(/_/g, ' ').toLowerCase()}</b></td>
                <td className="small">{target(e.invoice_key)}</td>
                <td className="small">{summary(e.payload)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
