import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, type Json } from '../api'
import { useApp, useCan } from '../context'
import { dateShort, dateTime, money, num, pct } from '../format'

const SOURCES = [
  { key: 'journals', label: 'Record to report', sub: 'SEP-26 close journals' },
  { key: 'ap_ledger', label: 'Procure to pay', sub: 'AP subledger, Apr–Sep 2026' },
  { key: 'cash', label: 'Cash application', sub: '14 Oct settlement receipts' },
]
const STATUSES = ['Open', 'Pending approval', 'Approved', 'Exported', 'Dismissed']
const DISMISS = [['valid_as_posted', 'Valid as posted'], ['already_corrected', 'Already corrected'],
  ['below_materiality', 'Below materiality'], ['false_positive', 'False positive']]

function CaseDrawer({ id, onClose, onChanged }: { id: string; onClose: () => void; onChanged: () => void }) {
  const { toast } = useApp()
  const can = useCan()
  const [c, setC] = useState<Json | null>(null)
  const [note, setNote] = useState('')
  const [account, setAccount] = useState('')
  const [reason, setReason] = useState('valid_as_posted')
  const [busy, setBusy] = useState(false)

  const load = () => api.caseDetail(id).then((x) => {
    setC(x)
    setAccount(x.fix?.lines?.[0]?.account ?? '')
  })
  useEffect(() => { load() }, [id]) // eslint-disable-line react-hooks/exhaustive-deps

  const act = async (action: string, body: Json, ok: string) => {
    setBusy(true)
    try {
      if (action === 'investigate') await api.caseAction(id, 'investigate', body)
      else setC(await api.caseAction(id, action, body))
      await load()
      onChanged()
      toast(ok)
    } catch (e) {
      toast((e as Error).message, 'error')
    } finally {
      setBusy(false)
    }
  }

  if (!c) return <aside className="drawer"><p className="muted">Loading case…</p></aside>
  const f = c.finding
  const prep = can(`case_prepare_${c.source}`)
  const appr = can(`case_approve_${c.source}`)
  const inv = c.investigation

  return (
    <aside className="drawer" aria-label={`Case ${c.case_id}`}>
      <div className="drawer-head">
        <div>
          <span className="muted small">{c.case_id} · {c.reference}</span>
          <h2>{c.type_label}</h2>
        </div>
        <button type="button" className="btn small quiet" onClick={onClose}>Close</button>
      </div>
      <div className="drawer-meta">
        <span className={`case-status s-${c.status.replace(/ /g, '-').toLowerCase()}`}>{c.status}</span>
        <span>{money(c.amount, c.currency)}</span>
        <span>Owner {c.owner_name}</span>
        <span className={c.overdue ? 'late' : ''}>SLA {dateShort(c.sla_due)}{c.overdue ? ' · overdue' : ''}</span>
      </div>
      <p>{c.detail}</p>
      {f.description && <p className="muted small">“{f.description}”{f.created_by ? ` · posted by ${f.created_by}` : ''}{f.approved_by ? `, approved by ${f.approved_by}` : ''}{f.applied_by ? ` · applied by ${f.applied_by}` : ''}</p>}

      <h3>Fix drafted by the agent</h3>
      {c.fix.lines.length > 0 ? (
        <table className="evidence">
          <thead>{c.fix.kind === 'reclass' || c.fix.kind === 'reversal'
            ? <tr><th>Account</th><th>Cost centre</th><th className="num">Debit</th><th className="num">Credit</th></tr>
            : <tr><th>Action</th><th>Customer</th><th>Invoice</th><th className="num">Amount</th></tr>}</thead>
          <tbody>
            {c.fix.lines.map((l: Json, i: number) => (c.fix.kind === 'reclass' || c.fix.kind === 'reversal') ? (
              <tr key={i}><td><b>{l.account}</b></td><td>{l.cost_centre}</td><td className="num">{l.dr ? money(l.dr) : ''}</td><td className="num">{l.cr ? money(l.cr) : ''}</td></tr>
            ) : (
              <tr key={i}><td>{l.action}</td><td>{l.customer}</td><td>{l.invoice ?? '—'}</td><td className="num">{money(l.amount, c.currency)}</td></tr>
            ))}
          </tbody>
        </table>
      ) : <p className="muted">No ledger entry: {c.fix.note}</p>}
      {c.fix.lines.length > 0 && <p className="muted small">{c.fix.note}</p>}

      <div className="drawer-section">
        <div className="card-head">
          <h3>Investigation</h3>
          {can('case_investigate') && <button type="button" className="btn small" disabled={busy}
            onClick={() => act('investigate', {}, 'Investigation complete')}>{inv ? 'Investigate again' : 'Investigate with Claude'}</button>}
        </div>
        {inv ? (
          <>
            <p>{inv.summary}</p>
            <ul className="cited">{inv.evidence.map((e: Json) => <li key={e.tool_call_id + e.text}><span className="cite">{e.tool_call_id}</span>{e.text}</li>)}</ul>
            <p className="next-action"><b>Recommended:</b> {inv.next_action} <span className="muted small">· {inv.source} · {inv.trace?.[0]?.tool_calls?.length ?? 0} read-only tool calls</span></p>
          </>
        ) : <p className="muted small">Claude can check the entry, the supplier's history and the customer's open items before you decide. It reads; it cannot act.</p>}
      </div>

      {(c.status === 'Open' || c.status === 'Pending approval') && (
        <div className="drawer-section">
          <h3>Decide</h3>
          <label className="field">Note for the record<textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} /></label>
          <div className="drawer-actions">
            {c.status === 'Open' && prep && (
              <>
                {c.fix.kind === 'reclass' && <label className="field inline">Reclass to<input className="text-input" value={account} onChange={(e) => setAccount(e.target.value)} /></label>}
                <button type="button" className="btn primary" disabled={busy}
                  onClick={() => act('prepare', { note, account }, 'Prepared and sent for approval')}>Prepare and submit</button>
              </>
            )}
            {c.status === 'Pending approval' && appr && (
              <>
                <button type="button" className="btn primary" disabled={busy} onClick={() => act('approve', { note }, 'Approved')}>Approve</button>
                <button type="button" className="btn" disabled={busy || !note} onClick={() => act('send-back', { reason: note }, 'Sent back to the preparer')}>Send back</button>
              </>
            )}
            {(prep || appr) && (
              <span className="dismiss">
                <select value={reason} onChange={(e) => setReason(e.target.value)} aria-label="Dismissal reason">
                  {DISMISS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                </select>
                <button type="button" className="btn quiet" disabled={busy} onClick={() => act('dismiss', { reason, note }, 'Dismissed')}>Dismiss</button>
              </span>
            )}
            {!prep && !appr && <p className="muted small">Read-only for your role. Preparer: {c.owner_name}.</p>}
          </div>
          {c.status === 'Pending approval' && <p className="muted small">Prepared by {c.decision_log.at(-1)?.by_name}. The preparer, and whoever posted the original entry, cannot approve.</p>}
        </div>
      )}

      <div className="drawer-section">
        <h3>Decision log</h3>
        {c.decision_log.length === 0 ? <p className="muted small">No decisions yet.</p> : (
          <ol className="timeline">{c.decision_log.map((d: Json, i: number) => (
            <li key={i} className="human"><time>{dateTime(d.at)}</time><div><div className="kind">{d.action}</div><div className="who">{d.by_name}</div>{d.note && <div className="payload">{d.note}</div>}</div></li>
          ))}</ol>
        )}
      </div>
    </aside>
  )
}

export default function Close() {
  const { version, bump, toast } = useApp()
  const can = useCan()
  const [params, setParams] = useSearchParams()
  const [dash, setDash] = useState<Json | null>(null)
  const [cases, setCases] = useState<Json[]>([])
  const [source, setSource] = useState('journals')
  const [status, setStatus] = useState('Open')
  const open = params.get('case')

  const load = () => {
    api.close().then(setDash)
    api.cases().then(setCases)
  }
  useEffect(load, [version])

  useEffect(() => {
    const c = cases.find((x) => x.case_id === open)
    if (c) {
      setSource(c.source)
      setStatus(c.status)
    }
  }, [open, cases])

  const shown = useMemo(() => cases.filter((c) => c.source === source && (status === 'All' || c.status === status))
    .sort((a, b) => (b.finding.score ?? b.confidence ?? 0) - (a.finding.score ?? a.confidence ?? 0) || b.amount - a.amount), [cases, source, status])

  const exportBatch = async (kind: 'gl' | 'cash') => {
    try {
      const m = await api.exportCases(kind)
      toast(`${m.batch}: ${m.cases.length} corrections exported`)
      window.open(`/api/cases/batches/${m.batch}.csv`, '_blank')
      bump()
    } catch (e) {
      toast((e as Error).message, 'error')
    }
  }
  const bulk = async () => {
    try {
      const r = await api.bulkPrepare(0.95)
      toast(`${r.prepared.length} matches at 95%+ confidence prepared for approval`)
      bump()
    } catch (e) {
      toast((e as Error).message, 'error')
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Close: one engine, three processes</h1>
          <p>The coding engine and controls, run over the close journals, the AP subledger and a day of cash application. Every finding is a case with an owner, an SLA and a drafted fix; a preparer submits, someone else approves, and approved fixes go to the ledger as standard interface files.</p>
        </div>
        <span className="muted small">{dash?.period}</span>
      </div>

      <div className="sources" data-tour="close-sources">
        {SOURCES.map((s) => {
          const d = dash?.by_source?.[s.key]
          return (
            <button key={s.key} type="button" className={`source ${source === s.key ? 'on' : ''}`} onClick={() => { setSource(s.key); setStatus('Open') }}
              data-tour={s.key === 'cash' ? 'cash-source' : s.key === 'journals' ? 'journal-source' : undefined}>
              <h3>{s.label}</h3>
              <div className="big">{d?.open ?? '—'}<span>open · {money(d?.value_at_risk ?? 0, 'USD', 0)} at risk</span></div>
              <div className="scan">{s.sub} · {d?.pending_approval ?? 0} awaiting approval · {d?.exported ?? 0} posted{d?.overdue ? ` · ${d.overdue} overdue` : ''}</div>
            </button>
          )
        })}
      </div>

      <div className="close-bar">
        <div className="filters" style={{ margin: 0 }}>
          {[...STATUSES, 'All'].map((s) => (
            <button key={s} type="button" className={status === s ? 'on' : ''} onClick={() => setStatus(s)}>
              {s} <span className="muted">{cases.filter((c) => c.source === source && (s === 'All' || c.status === s)).length}</span>
            </button>
          ))}
        </div>
        <div className="close-actions">
          {source === 'cash' && can('case_prepare_cash') && <button type="button" className="btn small" onClick={bulk}>Prepare all matches ≥ 95%</button>}
          {source !== 'cash' && can('case_export_gl') && <button type="button" className="btn small primary" onClick={() => exportBatch('gl')} data-tour="export-gl">Post approved corrections (GL_INTERFACE)</button>}
          {source === 'cash' && can('case_export_cash') && <button type="button" className="btn small primary" onClick={() => exportBatch('cash')}>Export approved re-applications</button>}
        </div>
      </div>

      <div className={`close-body${open ? ' with-drawer' : ''}`}>
        <div className="table-wrap" data-tour="case-table">
          <table className="grid">
            <thead><tr><th>Finding</th><th>Reference</th><th className="num">Amount</th><th>Fix</th><th>Owner</th><th>SLA</th><th>Status</th></tr></thead>
            <tbody>
              {shown.map((c) => (
                <tr key={c.case_id} className={`${open === c.case_id ? 'selected' : ''}${c.finding.description?.includes('Laptop refresh') ? ' story' : ''}`}
                  onClick={() => setParams({ case: c.case_id })} data-tour={c.finding.description?.includes('Laptop refresh') ? 'laptop-journal' : undefined}>
                  <td><b>{c.type_label}</b><div className="small muted">{(c.finding.description ?? c.detail).slice(0, 90)}</div></td>
                  <td className="small">{c.reference}</td>
                  <td className="num">{money(c.amount, c.currency, 0)}</td>
                  <td className="small">{c.fix.kind === 'reclass' ? `${c.fix.lines[1].account} → ${c.fix.lines[0].account}` : c.fix.kind}{c.confidence ? ` · ${pct(c.confidence)}` : ''}</td>
                  <td className="small">{c.owner_name}</td>
                  <td className={`small${c.overdue ? ' late' : ''}`}>{dateShort(c.sla_due)}</td>
                  <td><span className={`case-status s-${c.status.replace(/ /g, '-').toLowerCase()}`}>{c.status}</span></td>
                </tr>
              ))}
              {shown.length === 0 && <tr><td colSpan={7} className="muted">No {status.toLowerCase()} cases here.</td></tr>}
            </tbody>
          </table>
        </div>
        {open && <CaseDrawer id={open} onClose={() => setParams({})} onChanged={load} />}
      </div>

      {dash && dash.batches.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3>Posted to the ledger</h3>
          <table className="evidence">
            <thead><tr><th>Batch</th><th>Kind</th><th className="num">Cases</th><th>Control totals</th><th>By</th><th /></tr></thead>
            <tbody>{dash.batches.map((b: Json) => (
              <tr key={b.batch}><td><b>{b.batch}</b></td><td>{b.kind === 'gl' ? 'GL_INTERFACE' : 'Receipt reapplication'}</td><td className="num">{b.cases.length}</td>
                <td className="small">{b.kind === 'gl' ? `Dr ${money(b.totals.debits)} = Cr ${money(b.totals.credits)} · ${num(b.totals.lines)} lines` : `${money(b.totals.amount)} · ${b.totals.lines} lines`}</td>
                <td className="small">{dateTime(b.at)}</td><td><a className="btn small" href={`/api/cases/batches/${b.batch}.csv`}>CSV</a></td></tr>
            ))}</tbody>
          </table>
        </div>
      )}
      {dash?.suppressed > 0 && <p className="muted small" style={{ marginTop: 10 }}>{dash.suppressed} finding(s) hidden by rules learned from dismissals “valid as posted”.</p>}
    </>
  )
}
