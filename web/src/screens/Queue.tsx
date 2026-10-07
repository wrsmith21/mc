import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type Json } from '../api'
import StatusChip from '../components/StatusChip'
import { useApp } from '../context'
import { dateTime, money, num, pct } from '../format'

const FILTERS: { key: string; label: string; test: (r: Json) => boolean }[] = [
  { key: 'attention', label: 'Needs a person', test: (r) => !['APPROVED', 'IN_APPROVAL', 'FAST_TRACK', 'REJECTED'].includes(r.status) },
  { key: 'story', label: 'Workshop scenarios', test: (r) => !!r.scene || ['eu_vat', 'open_po', 'unknown_vendor', 'learning_1', 'learning_2', 'po_breach_marketing', 'utility_spike', 'wildcard'].includes(r.storyboard_key) },
  { key: 'held', label: 'Held by controls', test: (r) => ['HELD', 'VENDOR_ONBOARDING', 'MATCH_TO_PO'].includes(r.status) },
  { key: 'fast', label: 'Fast-tracked', test: (r) => r.agent_status === 'FAST_TRACK' },
  { key: 'all', label: 'All', test: () => true },
]

export default function Queue() {
  const { version } = useApp()
  const [rows, setRows] = useState<Json[]>([])
  const [summary, setSummary] = useState<Json | null>(null)
  const [filter, setFilter] = useState('story')
  const [q, setQ] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    api.queue().then(setRows)
    api.summary().then(setSummary)
  }, [version])

  const shown = useMemo(() => {
    const f = FILTERS.find((x) => x.key === filter)!
    const needle = q.toLowerCase()
    return rows
      .filter(f.test)
      .filter((r) => !needle || `${r.vendor} ${r.invoice_num} ${r.account ?? ''}`.toLowerCase().includes(needle))
      .sort((a, b) => (filter === 'story' ? (a.scene ?? 9) - (b.scene ?? 9) || a.received_at.localeCompare(b.received_at) : 0))
  }, [rows, filter, q])

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Non-PO invoices</h1>
          <p>
            Every invoice that arrived without a purchase order. The agent reads each one, recommends coding from
            {summary ? ` ${num(summary.history.lines)} ` : ' '}coded lines of history, checks it against policy and
            routes it to someone allowed to approve it. A person approves every posting.
          </p>
        </div>
      </div>

      {summary && (
        <section className="kpis" data-tour="kpis" aria-label="Today at a glance">
          <div className="kpi"><b>{summary.processed}</b><span>Invoices read by the agent</span></div>
          <div className="kpi"><b>{summary.fast_tracked}</b><span>Fast-tracked within policy</span></div>
          <div className="kpi"><b>{pct(summary.touchless_rate)}</b><span>Approved without re-coding</span></div>
          <div className="kpi"><b>{summary.held}</b><span>Held by controls · {money(summary.held_value_usd, 'USD', 0)}</span></div>
          <div className="kpi"><b>{summary.po_policy_breaches}</b><span>Should have been a PO</span></div>
          <div className="kpi"><b>{summary.hours_saved}h</b><span>Handling time saved (illustrative)</span></div>
        </section>
      )}

      <div className="filters" data-tour="filters">
        {FILTERS.map((f) => (
          <button key={f.key} type="button" className={filter === f.key ? 'on' : ''} onClick={() => setFilter(f.key)}>
            {f.label} <span className="muted">{rows.filter(f.test).length}</span>
          </button>
        ))}
        <input type="search" placeholder="Search supplier, invoice or account" value={q} onChange={(e) => setQ(e.target.value)}
          aria-label="Search the queue" />
      </div>

      <div className="table-wrap" data-tour="queue-table">
        <table className="grid">
          <thead>
            <tr>
              <th>Received</th><th>Supplier and invoice</th><th className="num">Amount</th><th>Recommended coding</th>
              <th className="num">Confidence</th><th>Flags</th><th>Status</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.intake_id} className={r.scene ? 'story' : ''} onClick={() => navigate(`/invoice/${r.intake_id}`)}
                data-tour={r.storyboard_key ? `row-${r.storyboard_key}` : undefined}>
                <td className="small">{dateTime(r.received_at)}</td>
                <td className="vendor-cell">
                  <b>{r.vendor}</b>
                  <span>{r.invoice_num} · {r.entity}{r.scene ? ` · Scene ${r.scene}` : ''}</span>
                </td>
                <td className="num">{money(r.total, r.currency)}</td>
                <td>{r.account ? <><b>{r.account}</b> <span className="muted small">{r.account_name} · {r.cost_centre}</span></> : <span className="muted">—</span>}</td>
                <td className="num">{pct(r.confidence)}</td>
                <td>
                  <div className="flagdots">
                    {r.flags.filter((f: Json) => f.severity !== 'info').slice(0, 2).map((f: Json) => (
                      <span key={f.code} className={`flagdot ${f.severity}`}>{f.title}</span>
                    ))}
                  </div>
                </td>
                <td><StatusChip status={r.status} label={r.status_label} /></td>
              </tr>
            ))}
            {shown.length === 0 && (
              <tr><td colSpan={7} className="muted">Nothing here. Try another filter.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  )
}
