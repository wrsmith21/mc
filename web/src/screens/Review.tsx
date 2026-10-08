import { QRCodeSVG } from 'qrcode.react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { api, runStream, type Json } from '../api'
import ProcessRail from '../components/ProcessRail'
import RunConsole from '../components/RunConsole'
import StatusChip from '../components/StatusChip'
import { personName, useApp, useCan } from '../context'
import { dateShort, dateTime, money, pct } from '../format'

const EVENT_LABEL: Record<string, string> = {
  RECEIVED: 'Invoice received', EXTRACTED: 'Fields extracted', RECOMMENDED: 'Coding recommended', FLAGGED: 'Flag raised',
  ROUTED: 'Approval route set', RECEIPT_REQUESTED: 'Receipt confirmation requested', RECEIPT_CONFIRMED: 'Receipt confirmed',
  ACCEPTED: 'Recommendation accepted', CODING_OVERRIDDEN: 'Coding overridden', HISTORY_UPDATED: 'History updated',
  SUBMITTED_FOR_APPROVAL: 'Submitted for approval', APPROVED_STEP: 'Approved (step)', APPROVED: 'Approved',
  REJECTED: 'Rejected', EXPORTED: 'Added to R12 AP interface file', RUN_COMPLETED: 'Agent run completed',
  RECEIPT_REMINDER: 'Reminder sent', RECEIPT_ESCALATED: 'Escalated', SUPPLIER_CONTACTED: 'Supplier contacted',
  CALLBACK_COMPLETED: 'Call-back completed', SUPPLIER_ONBOARDED: 'Supplier onboarded',
}
const BAND_LABEL: Record<string, string> = { fast_track: 'Fast-track band', review: 'Review band', manual: 'Needs a person' }

function describe(e: Json): string {
  const p = e.payload || {}
  switch (e.kind) {
    case 'RECEIVED': return `${p.channel ?? ''} ${p.from ? 'from ' + p.from : ''}`.trim()
    case 'EXTRACTED': return `${p.fields?.vendor_name} · ${p.fields?.invoice_num} · ${p.fields?.currency} ${p.fields?.total?.toLocaleString()} (${p.source}${p.latency_ms ? `, ${(p.latency_ms / 1000).toFixed(1)}s` : ''})`
    case 'RECOMMENDED': return `${p.account} ${p.account_name} / ${p.cost_centre} at ${Math.round(p.confidence * 100)}%. ${p.reason ?? ''}`
    case 'FLAGGED': return `${p.title}: ${p.detail}`
    case 'ROUTED': return `${(p.chain || []).join(' → ')}${p.sod ? ` · ${p.sod}` : ''}`
    case 'RECEIPT_REQUESTED': return `Sent to ${p.to}`
    case 'RECEIPT_CONFIRMED': return `${p.by}${p.note ? ` — “${p.note}”` : ''}`
    case 'CODING_OVERRIDDEN': return `${p.from_account}/${p.from_cost_centre} → ${p.account}/${p.cost_centre}. Reason: ${p.reason}`
    case 'HISTORY_UPDATED': return p.lesson
    case 'SUBMITTED_FOR_APPROVAL': return (p.chain || []).join(' → ')
    case 'APPROVED_STEP': case 'APPROVED': return `${p.by} (${p.step} of ${p.of})`
    case 'REJECTED': return p.reason
    case 'EXPORTED': return `${p.file} · group ${p.group_id}`
    case 'RUN_COMPLETED': return `${p.run_id} · ${p.trigger} · ${Math.round(p.ms)} ms · ${p.tool_calls} tool calls · ${p.status}`
    case 'RECEIPT_REMINDER': return `To ${p.to} after ${p.business_days} business days`
    case 'RECEIPT_ESCALATED': return `To ${p.to}${p.from ? ` (from ${p.from})` : ''} after ${p.business_days} business days`
    case 'SUPPLIER_CONTACTED': return p.why
    case 'CALLBACK_COMPLETED': return `${p.outcome}: ${p.note}`
    default: return typeof p === 'object' ? Object.values(p).filter((v) => typeof v === 'string').join(' · ') : String(p)
  }
}

const TRIGGER: Record<string, string> = { batch: 'overnight batch', manual: 'manual run', mailbox: 'mailbox run', rerun: 're-run' }

export default function Review() {
  const { id = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const { meta, session, toast, bump, slow } = useApp()
  const can = useCan()
  const me = session?.person?.id
  const [r, setR] = useState<Json | null>(null)
  const [live, setLive] = useState<Json[] | null>(null)
  const [running, setRunning] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [tab, setTab] = useState<'decision' | 'console' | 'audit'>('decision')
  const [docTab, setDocTab] = useState<'pdf' | 'fields'>('pdf')
  const [audit, setAudit] = useState<Json[]>([])
  const [overriding, setOverriding] = useState<null | 'override' | 'reject'>(null)
  const [form, setForm] = useState({ account: '', cost_centre: '', reason: '' })
  const [actualMs, setActualMs] = useState<number | null>(null)
  const stopRef = useRef<() => void>(undefined)
  const buffer = useRef<Json[]>([])
  const timer = useRef<number | undefined>(undefined)

  const load = useCallback(async () => {
    const res = await api.invoice(id)
    setR(res)
    setDocTab(res.pdf ? 'pdf' : 'fields')
    return res
  }, [id])
  const loadAudit = useCallback(() => api.audit(id).then(setAudit), [id])

  const apply = useCallback((ev: Json) => {
    if (ev.type === 'stage') setRunning(ev.label)
    if (ev.type === 'tool') {
      setLive((steps) => {
        const s = steps ?? []
        const i = s.findIndex((x) => x.key === ev.key && x.open)
        if (i < 0) return [...s, { key: ev.key, label: '', agent: '', status: 'running', open: true, tool_calls: [ev.call] }]
        if (s[i].tool_calls.some((t: Json) => t.id === ev.call.id)) return s
        return s.map((x, j) => (j === i ? { ...x, tool_calls: [...x.tool_calls, ev.call] } : x))
      })
    }
    if (ev.type === 'step') {
      setLive((steps) => [...(steps ?? []).filter((x) => !(x.key === ev.key && x.open)), ev])
      setRunning(null)
    }
    if (ev.type === 'result') {
      setR(ev.result)
      setRunning(null)
      setLive(null)
      setActualMs(ev.result.run?.ms ?? null)
      bump()
      loadAudit()
    }
    if (ev.type === 'error') {
      setRunning(null)
      setLive(null)
      toast(ev.message ?? 'The run stopped', 'error')
      load()
    }
  }, [bump, load, loadAudit, toast])

  const run = useCallback(() => {
    stopRef.current?.()
    window.clearInterval(timer.current)
    buffer.current = []
    setLive([])
    setActualMs(null)
    setRunning('Starting')
    setTab('console')
    if (slow) {
      timer.current = window.setInterval(() => {
        const ev = buffer.current.shift()
        if (ev) apply(ev)
        if (ev?.type === 'result' || ev?.type === 'error') window.clearInterval(timer.current)
      }, 220)
    }
    stopRef.current = runStream(id, (ev) => (slow ? buffer.current.push(ev) : apply(ev)))
  }, [id, slow, apply])

  useEffect(() => {
    setR(null)
    setLive(null)
    setTab('decision')
    setOverriding(null)
    load().then(() => {
      if (params.get('run')) {
        params.delete('run')
        setParams(params, { replace: true })
        run()
      }
    })
    loadAudit()
    return () => {
      stopRef.current?.()
      window.clearInterval(timer.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  useEffect(() => {
    if (r?.status !== 'AWAITING_CONFIRMATION') return
    const t = window.setInterval(async () => {
      const fresh = await api.invoice(id)
      if (fresh.status !== 'AWAITING_CONFIRMATION') {
        setR(fresh)
        loadAudit()
        bump()
        toast(`${fresh.receipt_task?.confirmed_by_name ?? 'The requester'} confirmed receipt`)
      }
    }, 2500)
    return () => window.clearInterval(t)
  }, [r?.status, id, loadAudit, bump, toast])

  const act = async (fn: () => Promise<Json>, ok: string) => {
    setBusy(true)
    try {
      const res = await fn()
      if (res?.intake_id) setR(res)
      else await load()
      await loadAudit()
      bump()
      toast(ok)
    } catch (e) {
      toast((e as Error).message, 'error')
    } finally {
      setBusy(false)
    }
  }

  const steps = useMemo(() => live ?? r?.trace ?? [], [live, r])
  const railSteps = useMemo(() => Object.fromEntries(steps.filter((s: Json) => !s.open).map((s: Json) => [s.key, s])), [steps])
  const cited = useMemo(() => new Set<string>((r?.investigation?.evidence ?? []).map((e: Json) => e.tool_call_id)), [r])

  if (!r) return <p className="muted">Loading invoice…</p>
  const doc = r.document
  const c = r.coding
  const rec0 = c?.lines?.[0]?.rec
  const contrast = c?.default_contrast
  const requester = r.requester?.person
  const task = r.receipt_task
  const decision = r.decision
  const chain = r.approval?.steps ?? []
  const nextApprover = decision?.status === 'IN_APPROVAL' ? decision.chain[decision.approvals.length] : null
  const learned = c?.lines?.find((l: Json) => l.rec?.learned)?.rec?.learned
  const canSubmit = !['HELD', 'MATCH_TO_PO', 'VENDOR_ONBOARDING', 'AWAITING_CONFIRMATION', 'APPROVED', 'IN_APPROVAL', 'REJECTED', 'ROUTED_OUT', 'NEW'].includes(r.status)
  const isRunning = live !== null
  const phoneUrl = requester ? `${window.location.origin}/requester?person=${requester.id}&t=${r.requester_link_token}` : ''
  const explainSrc = r.explanation_meta?.source
  const alternatives: Json[] = rec0?.alternatives ?? []
  const worked = !!r.run
  const diff: Json[] = (r.run?.diff ?? []).filter((d: Json) => d.field !== 'No change')
  const iAmRequester = !!me && (me === task?.assignee_id || me === requester?.id)
  const inv = r.investigation
  const second = rec0?.model?.second_opinion

  return (
    <div className="review">
      <section className="doc-pane" data-tour="document" aria-label="Invoice document">
        <div className="doc-head">
          <div className="tabs" style={{ margin: 0, border: 0 }}>
            {r.pdf && <button type="button" className={docTab === 'pdf' ? 'on' : ''} onClick={() => setDocTab('pdf')}>Invoice PDF</button>}
            <button type="button" className={docTab === 'fields' ? 'on' : ''} onClick={() => setDocTab('fields')}>What the agent read</button>
          </div>
          <span className="muted">{r.channel.replace('_', ' ').toLowerCase()} · {dateTime(r.received_at)}</span>
        </div>
        {docTab === 'pdf' && r.pdf ? (
          <div className="doc-image">
            <img src={`/api/pdf/${id}/preview`} alt={`Invoice ${doc.invoice_num} from ${doc.vendor_name}`} />
            <a className="btn small quiet" href={`/api/pdf/${id}`} target="_blank" rel="noreferrer">Open original PDF</a>
          </div>
        ) : (
          <div className="doc-fields">
            {!worked && <p className="muted small" style={{ marginBottom: 10 }}>As captured by the intake channel. The agent has not read it yet.</p>}
            <dl>
              <dt>Supplier</dt><dd>{doc.vendor_name}</dd>
              <dt>Invoice</dt><dd>{doc.invoice_num}</dd>
              <dt>Date</dt><dd>{doc.invoice_date}</dd>
              <dt>Due</dt><dd>{doc.due_date ?? '—'}</dd>
              <dt>Bill to</dt><dd>{doc.bill_to?.name ?? doc.entity}</dd>
              {doc.matter && <><dt>Matter</dt><dd>{doc.matter}</dd></>}
              {doc.service_period && <><dt>Service period</dt><dd>{doc.service_period.start} → {doc.service_period.end}</dd></>}
              {doc.vendor_tax_id && <><dt>Tax ID</dt><dd>{doc.vendor_tax_id}</dd></>}
              <dt>Total</dt><dd>{money(doc.total, doc.currency)}</dd>
            </dl>
            <table>
              <tbody>
                {doc.lines.map((l: Json, i: number) => (
                  <tr key={i}><td>{l.description}</td><td className="num">{l.qty} × {money(l.unit_price, doc.currency)}</td>
                    <td className="num">{money(l.amount, doc.currency)}</td></tr>
                ))}
              </tbody>
            </table>
            {r.extraction?.agreement && (
              <>
                <h3 style={{ marginTop: 18 }}>Cross-check: intake record vs what Claude read</h3>
                <table>
                  <tbody>
                    {r.extraction.agreement.map((a: Json) => (
                      <tr key={a.field}><td>{a.field}</td><td>{String(a.intake)}</td><td>{String(a.extracted)}</td><td>{a.match ? '✓' : '✗'}</td></tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </div>
        )}
      </section>

      <section className="decide" aria-label="Agent run and decision">
        <div className="card title-row" data-tour="invoice-head">
          <div className="who">
            <b>{r.vendor?.name ?? doc.vendor_name}</b>
            <span>{doc.invoice_num} · {money(doc.total, doc.currency)}{doc.currency !== 'USD' ? ` (${money(r.total_usd)})` : ''} · {doc.entity}</span>
            <span className="run-line" data-tour="run-line">
              {isRunning ? 'The agent is working this invoice now' :
                worked ? `Worked by the ${TRIGGER[r.run.trigger] ?? r.run.trigger} at ${dateTime(r.run.started_at)} · ${Math.round(r.run.ms)} ms · ${r.run.tool_calls} tool calls · policy v${r.run.policy_version ?? 1}` :
                  'Not yet worked by the agent'}
            </span>
          </div>
          <div className="head-actions">
            <StatusChip status={r.status} label={r.status_label} />
            {can('run_agent') && (
              <button type="button" className="btn accent" onClick={run} disabled={isRunning} data-tour="run-agent">
                {isRunning ? 'Agent working…' : worked ? 'Re-run the agent' : 'Run the agent'}
              </button>
            )}
            {worked && <a className="btn small quiet" href={`/api/invoices/${id}/evidence`} target="_blank" rel="noreferrer">Evidence pack</a>}
          </div>
        </div>

        {slow && actualMs != null && !isRunning && (
          <p className="pace-note">Display slowed for presentation · actual run {Math.round(actualMs)} ms</p>
        )}
        {r.stale && <div className="banner warn" role="status">{r.stale}</div>}
        {diff.length > 0 && !isRunning && (
          <div className="card diff" data-tour="diff">
            <h3>What changed since the last run</h3>
            <p className="muted small">{diff[0].cause}</p>
            <table className="evidence"><tbody>
              {diff.map((d) => (
                <tr key={d.field}><td>{d.field}</td><td><s>{Array.isArray(d.before) ? d.before.join(', ') || '—' : String(d.before ?? '—')}</s></td>
                  <td><b>{Array.isArray(d.after) ? d.after.join(', ') || '—' : String(d.after ?? '—')}</b></td></tr>
              ))}
            </tbody></table>
          </div>
        )}

        {!worked && !isRunning ? (
          <div className="card not-worked" data-tour="not-worked">
            <h3>Waiting for the agent</h3>
            <p>This invoice arrived in this morning's mailbox. Nothing has been checked or recommended yet: no supplier match, no coding, no route.</p>
            <p className="muted small">Running the agent executes every control in order. Each step acts only through registered tools, and every call is timed and recorded.</p>
            {!can('run_agent') && <p className="muted small">Only the AP team runs the agent. You are signed in as {session?.person?.name}.</p>}
          </div>
        ) : (
          <>
            <div className="tabs">
              <button type="button" className={tab === 'decision' ? 'on' : ''} onClick={() => setTab('decision')}>Recommendation</button>
              <button type="button" className={tab === 'console' ? 'on' : ''} onClick={() => setTab('console')} data-tour="console-tab">
                Agent console <span className="muted small">{steps.reduce((n: number, s: Json) => n + (s.tool_calls?.length ?? 0), 0)}</span>
              </button>
              <button type="button" className={tab === 'audit' ? 'on' : ''} onClick={() => { setTab('audit'); loadAudit() }} data-tour="audit-tab">
                Audit trail <span className="muted small">{audit.length}</span>
              </button>
            </div>

            {tab === 'console' && <RunConsole steps={steps} running={running} run={isRunning ? null : r.run} cited={cited} />}

            {tab === 'audit' && (
              <div className="card" data-tour="audit">
                <div className="card-head">
                  <h3>Every step, who did it, and why</h3>
                  <a className="btn small" href={`/api/invoices/${id}/evidence`} target="_blank" rel="noreferrer">SOX evidence pack</a>
                </div>
                <ol className="timeline">
                  {audit.map((e) => (
                    <li key={e.id ?? `${e.ts}${e.kind}`} className={e.actor !== 'AGENT' ? 'human' : ''}>
                      <time>{dateTime(e.ts)}</time>
                      <div>
                        <div className="kind">{EVENT_LABEL[e.kind] ?? e.kind}
                          <span className={`tag ${e.actor !== 'AGENT' ? 'person' : ''}`}>{e.actor === 'AGENT' ? 'Agent' : 'Person'}</span>
                        </div>
                        <div className="who">{e.actor_name}{e.actor_title ? ` · ${e.actor_title}` : ''}</div>
                        <div className="payload">{describe(e)}</div>
                      </div>
                    </li>
                  ))}
                </ol>
              </div>
            )}

            {tab === 'decision' && (
              <>
                {isRunning && <div className="card"><ProcessRail steps={railSteps} running={null} compact /></div>}
                {!isRunning && c && (
                  <div className="card" data-tour="recommendation">
                    <div className="rec">
                      <div>
                        <div className="code">{(decision?.override?.account) ?? c.account}<small>{decision?.override?.cost_centre ?? c.cost_centre} · {c.entity}</small></div>
                        <div className="name">{c.account_name}</div>
                        {r.amortisation && <div className="cc">Amortise {r.amortisation.months} × {money(r.amortisation.monthly_amount)} to {r.amortisation.expense_account}</div>}
                      </div>
                      <div className={`gauge ${c.band}`} data-tour="confidence">
                        <b>{pct(c.confidence)}</b>
                        <div className="bar"><i style={{ width: `${c.confidence * 100}%` }} /></div>
                        <span className="small muted">{BAND_LABEL[c.band]} · calibrated</span>
                      </div>
                    </div>
                    {contrast && (
                      <div className="override-strip" data-tour="default-override">
                        <div className="was old"><span>Vendor master default</span><b>{contrast.vendor_default} {contrast.vendor_default_name}</b></div>
                        <div className="was new"><span>Agent recommends</span><b>{rec0.scored_account} {rec0.scored_account === c.account ? c.account_name : ''}</b></div>
                      </div>
                    )}
                    {learned && (
                      <p className="reason" style={{ borderTop: 0, paddingTop: 0, color: 'var(--green)' }}>
                        Learned from {learned.by}'s correction on {learned.source_invoice} ({dateShort(learned.at)}): {learned.reason}. Cost centre {learned.previous_cost_centre} → {learned.cost_centre}.
                      </p>
                    )}
                    <p className="reason" data-tour="reason">
                      {r.explanation}
                      <span className="src">
                        {explainSrc === 'live' ? `Written by ${r.explanation_meta.model} from the engine's findings` :
                          explainSrc === 'cache' ? 'Written by Claude from the engine’s findings (replayed)' :
                            'Reason assembled from the engine’s findings'} · the account is chosen by the scoring engine, not the language model
                      </span>
                    </p>
                    <div className="signals" data-tour="signals">
                      <div className="signal"><b>{pct(rec0.components.text_vote)}</b><span>Description matches past lines coded {rec0.scored_account}</span></div>
                      <div className="signal"><b>{pct(rec0.components.vendor_freq)}</b><span>Of this supplier's invoices used {rec0.scored_account}</span></div>
                      <div className="signal"><b>{rec0.components.amount_fit >= 1 ? 'In range' : 'Unusual'}</b><span>Amount vs this supplier and similar lines</span></div>
                    </div>
                    <p className="model-line" data-tour="model-line">
                      Raw score {pct(rec0.raw_confidence)} → calibrated {pct(rec0.confidence)} on the May–Jun hold-out ·
                      model {rec0.model?.production} v{rec0.model?.version}
                      {second && <> · second opinion: {second.model} {second.agrees ? 'agrees' : `says ${second.account}`} ({pct(second.confidence)})</>}
                      {' · '}<Link to="/model">how it was measured</Link>
                    </p>
                  </div>
                )}
                {!isRunning && !c && (
                  <div className="card"><h3>No coding recommendation</h3><p>{r.next_action}</p></div>
                )}

                {inv && !isRunning && (
                  <div className="card investigation" data-tour="investigation">
                    <div className="card-head">
                      <h3>What the investigator found</h3>
                      <span className="muted small">{inv.source === 'live' ? `Claude, ${inv.tool_calls?.length ?? 0} read-only tool calls` : inv.source === 'cache' ? 'Claude (replayed), read-only tools' : 'Deterministic summary (model not used)'}</span>
                    </div>
                    <p>{inv.summary}</p>
                    {inv.evidence?.length > 0 && (
                      <ul className="cited">
                        {inv.evidence.map((e: Json) => (
                          <li key={e.tool_call_id + e.text}>
                            <button type="button" className="cite" onClick={() => { setTab('console'); setTimeout(() => document.getElementById(`call-${e.tool_call_id}`)?.scrollIntoView({ block: 'center' }), 50) }}>{e.tool_call_id}</button>
                            {e.text}
                          </li>
                        ))}
                      </ul>
                    )}
                    <p className="next-action"><b>Recommended next action:</b> {inv.next_action} <span className="muted small">· the investigator can read, not act</span></p>
                  </div>
                )}

                {r.flags.length > 0 && !isRunning && (
                  <div className="card" data-tour="flags">
                    <h3>What the agent caught</h3>
                    <div className="flags">
                      {r.flags.map((f: Json) => (
                        <div key={f.code + f.title} className={`flag ${f.severity}`}>
                          <span className="ic">{f.severity === 'hold' ? '!' : f.severity === 'warn' ? '?' : 'i'}</span>
                          <div><b>{f.title}</b><p>{f.detail}</p></div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {!isRunning && (
                  <div className="card">
                    <div className="card-head">
                      <h3>How the agent worked it</h3>
                      <button type="button" className="btn small quiet" onClick={() => setTab('console')}>Open the console</button>
                    </div>
                    <ProcessRail steps={railSteps} running={null} />
                  </div>
                )}

                {!isRunning && r.price && (r.price.rate_card?.lines?.length > 0 || r.price.matter_budget || r.price.sow) && (
                  <div className="card" data-tour="price">
                    <h3>Is the price right?</h3>
                    {r.price.rate_card?.lines?.length > 0 && (
                      <table className="evidence">
                        <thead><tr><th>Role</th><th className="num">Hours</th><th className="num">Billed</th><th className="num">Agreed ({r.price.rate_card.letter})</th><th className="num">Over</th></tr></thead>
                        <tbody>
                          {r.price.rate_card.lines.map((l: Json) => (
                            <tr key={l.role} className={l.excess > 0 ? 'over' : ''}><td>{l.role}</td><td className="num">{l.hours}</td><td className="num">{money(l.billed_rate, 'USD', 0)}</td>
                              <td className="num">{money(l.card_rate, 'USD', 0)}</td><td className="num">{l.excess > 0 ? money(l.excess) : '—'}</td></tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                    {r.price.matter_budget && (
                      <p style={{ marginTop: 10 }}>Matter {r.price.matter_budget.matter}: {money(r.price.matter_budget.after_invoice_usd, 'USD', 0)} of {money(r.price.matter_budget.budget_usd, 'USD', 0)} budget ({pct(r.price.matter_budget.share_after)}) after this invoice.</p>
                    )}
                    {r.price.sow && <p style={{ marginTop: 10 }}>{r.price.sow.sow}: fixed fee {money(r.price.sow.fixed_fee_usd)}, {r.price.sow.matches_fee ? 'invoice matches' : 'invoice differs'}.</p>}
                  </div>
                )}

                {!isRunning && rec0?.evidence?.length > 0 && (
                  <div className="card" data-tour="evidence">
                    <div className="card-head">
                      <h3>Why: the most similar past invoices</h3>
                      <span className="muted small">{c.searched_lines.toLocaleString()} coded lines searched</span>
                    </div>
                    <table className="evidence">
                      <thead><tr><th>Supplier</th><th>Date</th><th>Line</th><th className="num">Amount</th><th>Coded</th><th>Approved by</th></tr></thead>
                      <tbody>
                        {rec0.evidence.map((e: Json) => (
                          <tr key={e.invoice_id + e.description} className={e.same_vendor ? 'same' : ''}>
                            <td>{e.vendor}<div className="small muted">{e.invoice_num}</div></td>
                            <td>{dateShort(e.date)}</td>
                            <td>{e.description}</td>
                            <td className="num">{money(e.amount_usd, 'USD', 0)}</td>
                            <td><b>{e.account}</b> <span className="small muted">{e.cost_centre}</span></td>
                            <td className="small">{e.approved_by}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {!isRunning && (r.capitalisation || r.amortisation || r.cutoff || r.use_tax || c?.splits) && (
                  <div className="card" data-tour="treatment">
                    {r.capitalisation && (
                      <>
                        <h3>Capital asset: route to Fixed Asset Accounting</h3>
                        <p>{r.capitalisation.units} units at {money(r.capitalisation.unit_price)} each meet the {money(r.capitalisation.threshold_per_unit, 'USD', 0)} per-unit threshold for {r.capitalisation.asset_class}. Asset cost including tax {money(r.capitalisation.asset_cost_usd)}; {r.capitalisation.useful_life_months}-month life, about {money(r.capitalisation.monthly_depreciation)} a month. Fixed Asset Accounting makes the capitalisation decision.</p>
                      </>
                    )}
                    {r.amortisation && (
                      <>
                        <div className="card-head">
                          <h3>Prepaid, with the amortisation journal drafted for R2R</h3>
                          <a className="btn small" href={`/api/exports/amortisation/${id}`}>Download GL_INTERFACE file</a>
                        </div>
                        <table className="evidence">
                          <thead><tr><th>Period</th><th>Debit</th><th>Credit</th><th className="num">Amount</th></tr></thead>
                          <tbody>
                            {r.amortisation.schedule.slice(0, 4).map((s: Json) => (
                              <tr key={s.period}><td>{s.period}</td><td>{s.debit}</td><td>{s.credit} Prepaid</td><td className="num">{money(s.amount)}</td></tr>
                            ))}
                            <tr><td colSpan={4} className="muted small">…and {r.amortisation.schedule.length - 4} more months to {r.amortisation.schedule.at(-1).period}</td></tr>
                          </tbody>
                        </table>
                      </>
                    )}
                    {c?.splits && (
                      <>
                        <h3>Split as named on the invoice</h3>
                        <table className="evidence"><tbody>
                          {c.splits.map((s: Json) => (
                            <tr key={s.line}><td>{s.description}</td><td>{s.entity}</td><td>{s.cost_centre}</td><td>{s.account}</td><td className="num">{money(s.amount, doc.currency)}</td></tr>
                          ))}
                        </tbody></table>
                      </>
                    )}
                    {r.cutoff && (
                      <>
                        <h3>Cut-off: {r.cutoff.periods.join(', ')} is closed</h3>
                        <p>{money(r.cutoff.amount_in_closed_usd)} of this service belongs to {r.cutoff.periods.join(', ')}. {r.cutoff.accrued_usd > 0 ? `Accrued ${money(r.cutoff.accrued_usd)} in ${r.cutoff.accrual_je}; the accrual reversed on 1 October, so this invoice books against it.` : `Nothing was accrued at close, so it lands in October. ${r.cutoff.amount_in_closed_usd >= r.cutoff.materiality_usd ? 'Above materiality: reported to Record-to-Report as out-of-period expense.' : 'Below materiality.'}`}</p>
                      </>
                    )}
                    {r.use_tax && (
                      <>
                        <h3>Use tax accrued</h3>
                        <p>The seller in {r.use_tax.seller_region} charged no sales tax on {money(r.use_tax.taxable_usd)} of taxable goods shipped to Missouri. Accrue {money(r.use_tax.amount_usd)} ({pct(r.use_tax.rate, 2)}) to {r.use_tax.account} Use Tax Payable.</p>
                      </>
                    )}
                  </div>
                )}

                {!isRunning && r.receipt && (
                  <div className="card" data-tour="receipt">
                    <h3>Who asked for it, and did we get it?</h3>
                    <div className="receipt">
                      <div>
                        <p><b>{requester?.name ?? 'Not identified'}</b> <span className="muted">{requester?.title}</span></p>
                        <p className="small muted">{r.requester.source}: {r.requester.evidence}</p>
                        <p style={{ marginTop: 8 }}>
                          {r.receipt.rule === 'evidence' ? <span className="ok-text">Evidenced: {r.receipt.evidence.kind.replace(/_/g, ' ')} {r.receipt.evidence.reference}, {r.receipt.evidence.recorded_by_name}, {dateShort(r.receipt.evidence.date)}.</span> :
                            !r.receipt.required ? <span className="ok-text">Covered by the standing receipt rule.</span> :
                              task?.status === 'confirmed' ? <span className="ok-text">Confirmed by {task.confirmed_by_name}, {dateTime(task.confirmed_at)}{task.note ? ` — “${task.note}”` : ''}</span> :
                                task ? <b>Waiting for {task.assignee_name} to confirm receipt (asked {dateTime(task.requested_at)}){task.escalated_from ? `, escalated from ${task.escalated_from}` : ''}.</b> :
                                  <b>Receipt confirmation needed.</b>}
                        </p>
                        {(!r.receipt.required || r.receipt.rule === 'evidence') && <p className="small muted">{r.receipt.detail}</p>}
                        {r.receipt.required && task?.status !== 'confirmed' && (
                          <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
                            {!task && requester && can('request_receipt') && (
                              <button type="button" className="btn small" disabled={busy}
                                onClick={() => act(() => api.requestReceipt(id), `Request sent to ${requester.name}`)}>Send request to {requester.name}</button>
                            )}
                            {iAmRequester && (
                              <button type="button" className="btn primary small" disabled={busy}
                                onClick={() => act(() => api.confirmReceipt(id, 'Confirmed from the desktop'), 'Receipt confirmed')}>Confirm I received it</button>
                            )}
                          </div>
                        )}
                      </div>
                      {r.receipt.required && task?.status !== 'confirmed' && requester && (
                        <div className="qr" data-tour="qr">
                          <QRCodeSVG value={phoneUrl} size={104} />
                          <span className="small muted" style={{ maxWidth: 120 }}>{requester.name.split(' ')[0]}'s phone: scan to open the task</span>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {!isRunning && r.payment && (
                  <div className="card payment">
                    <h3>Paying it</h3>
                    <p>Terms {r.payment.terms}, due {dateShort(r.payment.due_date)}.
                      {r.payment.discount && (r.payment.discount.open ? <> Pay by <b>{dateShort(r.payment.discount.pay_by)}</b> to take {pct(r.payment.discount.rate)} ({money(r.payment.discount.amount, r.payment.discount.currency)}).</> : ' Early-payment discount window has passed.')}
                      {['HELD', 'VENDOR_ONBOARDING'].includes(r.status) && <> <b>Excluded from every payment run while held.</b></>}
                    </p>
                  </div>
                )}

                {!isRunning && chain.length > 0 && (
                  <div className="card" data-tour="approval">
                    <div className="card-head">
                      <h3>Who can approve it</h3>
                      <span className="muted small">{r.approval.tier} · {r.approval.limit_check}</span>
                    </div>
                    <div className="chain">
                      {chain.flatMap((s: Json, i: number) => [
                        ...s.skipped.map((k: Json) => (
                          <div key={`skip-${k.person.id}`} className="skipped">
                            <s>{k.person.name} ({k.role})</s> — {k.reason}
                          </div>
                        )),
                        <div key={s.person.id + i} className={`step ${decision?.approvals?.[i] ? 'done' : nextApprover === s.person.id ? 'next' : ''}`}>
                          <span className="n">{i + 1}</span>
                          <div>
                            <b>{s.person.name}</b> <span className="muted">{s.person.title}</span>
                            <div className="small muted">{s.role_label} · {s.basis}{s.person.approval_limit ? ` · limit ${money(s.person.approval_limit, 'USD', 0)}` : ' · no limit'}</div>
                          </div>
                          {decision?.approvals?.[i] ? <span className="small">Approved {dateTime(decision.approvals[i].at)}</span> :
                            nextApprover === s.person.id ? (me === s.person.id ? (
                              <button type="button" className="btn primary small" disabled={busy}
                                onClick={() => act(() => api.approve(id), 'Approved')}>Approve</button>
                            ) : <span className="small muted">Waiting for {s.person.name.split(' ')[0]}</span>) : null}
                        </div>,
                      ])}
                    </div>
                  </div>
                )}

                {!isRunning && (
                  <div className="actions" data-tour="actions">
                    <span className="next">{decision?.status === 'APPROVED' ? 'Approved. Included in today’s R12 AP interface file.' :
                      decision?.status === 'IN_APPROVAL' ? `With ${personName(meta, nextApprover) || 'the approver'} for approval.` :
                        decision?.status === 'REJECTED' ? `Rejected: ${decision.reason}` : r.next_action}</span>
                    {!decision && c && can('decide') && (
                      <>
                        <button type="button" className="btn primary" disabled={!canSubmit || busy}
                          onClick={() => act(() => api.decide(id, { action: 'accept' }), 'Accepted and sent for approval')}>
                          Accept and send for approval
                        </button>
                        <button type="button" className="btn" disabled={!canSubmit || busy} onClick={() => {
                          setOverriding('override')
                          setForm({ account: c.account, cost_centre: c.cost_centre, reason: '' })
                        }}>Override</button>
                        <button type="button" className="btn danger" disabled={busy} onClick={() => setOverriding('reject')}>Reject</button>
                      </>
                    )}
                    {!decision && !can('decide') && <span className="small muted">Decisions are made by the AP team.</span>}
                    {decision?.status === 'APPROVED' && <a className="btn small" href="/api/exports/ap-interface/lines">Download AP_INVOICE_LINES_INTERFACE</a>}
                    {overriding && (
                      <form className="override-form" onSubmit={(e) => {
                        e.preventDefault()
                        act(() => api.decide(id, { action: overriding, reason: form.reason,
                          override: overriding === 'override' ? { account: form.account, cost_centre: form.cost_centre } : undefined }),
                        overriding === 'override' ? 'Override saved; history updated' : 'Invoice rejected').then(() => setOverriding(null))
                      }}>
                        {overriding === 'override' && (
                          <>
                            <label>Account
                              <select value={form.account} onChange={(e) => setForm({ ...form, account: e.target.value })}>
                                {alternatives.map((a: Json) => <option key={a.account} value={a.account}>{a.account} {a.name}</option>)}
                                {!alternatives.some((a: Json) => a.account === c.account) && <option value={c.account}>{c.account} {c.account_name}</option>}
                              </select>
                            </label>
                            <label>Cost centre
                              <input value={form.cost_centre} onChange={(e) => setForm({ ...form, cost_centre: e.target.value.toUpperCase() })}
                                pattern="CC\d{4}" className="text-input" />
                            </label>
                          </>
                        )}
                        <label className="full">Reason (kept in the audit trail{overriding === 'override' ? ' and used to improve future recommendations' : ''})
                          <textarea required value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} rows={2} />
                        </label>
                        <div className="full" style={{ display: 'flex', gap: 8 }}>
                          <button type="submit" className="btn primary" disabled={busy}>{overriding === 'override' ? 'Save override and send for approval' : 'Reject invoice'}</button>
                          <button type="button" className="btn quiet" onClick={() => setOverriding(null)}>Cancel</button>
                        </div>
                      </form>
                    )}
                  </div>
                )}
              </>
            )}
          </>
        )}
      </section>
    </div>
  )
}
