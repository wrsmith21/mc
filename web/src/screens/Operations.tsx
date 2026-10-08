import { useEffect, useState } from 'react'
import { api, type Json } from '../api'
import { useApp } from '../context'
import { money, num, pct } from '../format'

const AGENT: Record<string, string> = {
  intake: 'Intake & extraction', supplier: 'Supplier & validity', coding: 'Coding & treatment', price: 'Price',
  approval: 'Approval & receipt', risk: 'Payment risk', investigator: 'Investigator', supervisor: 'Supervisor',
}
const ms = (v: number | null) => (v == null ? '—' : v < 1 ? '<1 ms' : `${Math.round(v)} ms`)

export default function Operations() {
  const { version } = useApp()
  const [o, setO] = useState<Json | null>(null)
  useEffect(() => { api.operations().then(setO) }, [version])
  if (!o) return <p className="muted">Loading run telemetry…</p>
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Operations</h1>
          <p>How the agent is running, from the stored run records: volume, latency per agent, model use and cost, failures and refused actions. In production the same figures stream to CloudWatch or Azure Monitor.</p>
        </div>
        <span className="muted small">Model {o.model}</span>
      </div>
      <section className="kpis">
        <div className="kpi"><b>{num(o.runs)}</b><span>Agent runs ({Object.entries(o.by_trigger).map(([k, v]) => `${v} ${k}`).join(', ')})</span></div>
        <div className="kpi"><b>{ms(o.run_ms.p50)}</b><span>Typical run · slowest {ms(o.run_ms.max)}</span></div>
        <div className="kpi"><b>{num(o.tool_calls)}</b><span>Tool calls on current results</span></div>
        <div className="kpi"><b>{pct(o.cache_hit_rate)}</b><span>Model calls served from cache</span></div>
        <div className="kpi"><b>{money(o.est_cost_usd, 'USD', 2)}</b><span>Live model spend ({num(o.tokens.input + o.tokens.output)} tokens)</span></div>
        <div className="kpi"><b>{o.failed}</b><span>Failed tool calls · {o.access_denied} refused actions</span></div>
      </section>
      <div className="insight-grid">
        <div className="card">
          <h3>Latency by agent</h3>
          <table className="evidence">
            <thead><tr><th>Agent</th><th className="num">Typical</th><th className="num">Slowest 5%</th><th className="num">Steps</th></tr></thead>
            <tbody>{o.agents.map((a: Json) => (
              <tr key={a.agent}><td>{AGENT[a.agent] ?? a.agent}</td><td className="num">{ms(a.p50)}</td><td className="num">{ms(a.p95)}</td><td className="num">{num(a.steps)}</td></tr>
            ))}</tbody>
          </table>
          <p className="muted small" style={{ marginTop: 8 }}>Deterministic agents run in milliseconds; time goes to the model calls and live registry checks (EU VIES).</p>
        </div>
        <div className="card">
          <h3>Where the model is used</h3>
          <table className="evidence">
            <thead><tr><th>Call</th><th>Sources</th></tr></thead>
            <tbody>{Object.entries(o.sources).map(([k, v]: [string, Json]) => (
              <tr key={k}><td>{k === 'reason' ? 'Reviewer reason' : k === 'extraction' ? 'PDF extraction' : 'Exception investigation'}</td>
                <td className="small">{Object.entries(v).map(([s, n]) => `${n} ${s}`).join(' · ') || '—'}</td></tr>
            ))}</tbody>
          </table>
          <p className="muted small" style={{ marginTop: 8 }}>“template” means the deterministic fallback was used: the run completes without the model.</p>
          {o.failed_calls.length > 0 && (
            <>
              <h3 style={{ marginTop: 14 }}>Recent failed calls</h3>
              <ul className="small">{o.failed_calls.map((f: Json, i: number) => <li key={i}>{f.intake_id} · {f.tool}: {f.error}</li>)}</ul>
            </>
          )}
        </div>
      </div>
    </>
  )
}
