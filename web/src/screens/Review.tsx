import { QRCodeSVG } from 'qrcode.react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { api, runStream, type Json } from '../api'
import ProcessRail from '../components/ProcessRail'
import StatusChip from '../components/StatusChip'
import { personName, useApp } from '../context'
import { dateShort, dateTime, money, pct } from '../format'

const EVENT_LABEL: Record<string, string> = {
  RECEIVED: 'Invoice received', EXTRACTED: 'Fields extracted', RECOMMENDED: 'Coding recommended', FLAGGED: 'Flag raised',
  ROUTED: 'Approval route set', RECEIPT_REQUESTED: 'Receipt confirmation requested', RECEIPT_CONFIRMED: 'Receipt confirmed',
  ACCEPTED: 'Recommendation accepted', CODING_OVERRIDDEN: 'Coding overridden', HISTORY_UPDATED: 'History updated',
  SUBMITTED_FOR_APPROVAL: 'Submitted for approval', APPROVED_STEP: 'Approved (step)', APPROVED: 'Approved',
  REJECTED: 'Rejected', EXPORTED: 'Added to R12 AP interface file',
}
const BAND_LABEL: Record<string, string> = { fast_track: 'High confidence (90%+)', review: 'Review band (60–90%)', manual: 'Needs a person (under 60%)' }

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
    default: return JSON.stringify(p)
  }
}

export default function Review() {
  const { id = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const { persona, meta, toast, bump, pace } = useApp()
  const [r, setR] = useState<Json | null>(null)
  const [steps, setSteps] = useState<Record<string, Json>>({})
  const [running, setRunning] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [tab, setTab] = useState<'decision' | 'audit'>('decision')
  const [docTab, setDocTab] = useState<'pdf' | 'fields'>('pdf')
  const [audit, setAudit] = useState<Json[]>([])
  const [overriding, setOverriding] = useState<null | 'override' | 'reject'>(null)
  const [form, setForm] = useState({ account: '', cost_centre: '', reason: '' })
  const stopRef = useRef<() => void>(undefined)

  const load = useCallback(async () => {
    const res = await api.invoice(id)
    setR(res)
    setSteps(Object.fromEntries(res.trace.map((s: Json) => [s.key, s])))
    setDocTab(res.pdf ? 'pdf' : 'fields')
    return res
  }, [id])

  const loadAudit = useCallback(() => api.audit(id).then(setAudit), [id])

  const run = useCallback(() => {
    stopRef.current?.()
    setSteps({})
    setRunning('intake')
    stopRef.current = runStream(id, pace, (ev) => {
      if (ev.type === 'stage') setRunning(ev.key)
      if (ev.type === 'step') {
        setSteps((s) => ({ ...s, [ev.key]: ev }))
        setRunning(null)
      }
      if (ev.type === 'result') {
        setR(ev.result)
        setRunning(null)
        bump()
        loadAudit()
      }
      if (ev.type === 'error') {
        setRunning(null)
        load()
      }
    })
  }, [id, pace, bump, load, loadAudit])

  useEffect(() => {
    setR(null)
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
    return () => stopRef.current?.()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  // When the requester confirms on their phone, the desk view updates on its own.
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
  const canSubmit = !['HELD', 'MATCH_TO_PO', 'VENDOR_ONBOARDING', 'AWAITING_CONFIRMATION', 'APPROVED', 'IN_APPROVAL', 'REJECTED'].includes(r.status)
  const isRunning = running !== null || (Object.keys(steps).length > 0 && Object.keys(steps).length < r.trace.length)
  const phoneUrl = requester ? `${window.location.origin}/requester?person=${requester.id}` : ''
  const explainSrc = r.explanation_meta?.source
  const alternatives: Json[] = rec0?.alternatives ?? []

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
                <h3 style={{ marginTop: 18 }}>Cross-check: printed vs. extracted</h3>
                <table>
                  <tbody>
                    {r.extraction.agreement.map((a: Json) => (
                      <tr key={a.field}><td>{a.field}</td><td>{String(a.extracted)}</td><td>{a.match ? '✓' : '✗'}</td></tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </div>
        )}
      </section>

      <section className="decide" aria-label="Agent recommendation and decision">
        <div className="card title-row">
          <div className="who">
            <b>{r.vendor?.name ?? doc.vendor_name}</b>
            <span>{doc.invoice_num} · {money(doc.total, doc.currency)}{doc.currency !== 'USD' ? ` (${money(r.total_usd)})` : ''} · {doc.entity}</span>
          </div>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <StatusChip status={r.status} label={r.status_label} />
            <button type="button" className="btn accent" onClick={run} disabled={isRunning} data-tour="run-agent">
              {isRunning ? 'Agent running…' : 'Run the agent'}
            </button>
          </div>
        </div>

        <div className="tabs">
          <button type="button" className={tab === 'decision' ? 'on' : ''} onClick={() => setTab('decision')}>Recommendation</button>
          <button type="button" className={tab === 'audit' ? 'on' : ''} onClick={() => { setTab('audit'); loadAudit() }} data-tour="audit-tab">
            Audit trail <span className="muted small">{audit.length}</span>
          </button>
        </div>

        {tab === 'audit' ? (
          <div className="card" data-tour="audit">
            <div className="card-head">
              <h3>Every step, who did it, and why</h3>
              <span className="muted small">SOX evidence, generated as a by-product</span>
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
        ) : (
          <>
            {c ? (
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
                    <span className="small muted">{BAND_LABEL[c.band]}</span>
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
                  <div className="signal"><b>{rec0.components.amount_fit >= 1 ? 'In range' : 'Unusual'}</b><span>Unit price vs. past lines</span></div>
                </div>
              </div>
            ) : (
              <div className="card"><h3>No coding recommendation</h3><p>{r.next_action}</p></div>
            )}

            {r.flags.length > 0 && (
              <div className="card" data-tour="flags">
                <h3>What the agent caught</h3>
                <div className="flags">
                  {r.flags.map((f: Json) => (
                    <div key={f.code} className={`flag ${f.severity}`}>
                      <span className="ic">{f.severity === 'hold' ? '!' : f.severity === 'warn' ? '?' : 'i'}</span>
                      <div><b>{f.title}</b><p>{f.detail}</p></div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="card">
              <div className="card-head">
                <h3>How the agent worked it</h3>
                <span className="muted small">Mapped to the eight steps of a good non-PO process</span>
              </div>
              <ProcessRail steps={steps} running={running} />
            </div>

            {rec0?.evidence?.length > 0 && (
              <div className="card" data-tour="evidence">
                <div className="card-head">
                  <h3>Why: the most similar past invoices</h3>
                  <span className="muted small">{c.searched_lines.toLocaleString()} coded lines searched</span>
                </div>
                <table className="evidence">
                  <thead><tr><th>Supplier</th><th>Date</th><th>Line</th><th className="num">Amount</th><th>Coded</th><th>Approved by</th></tr></thead>
                  <tbody>
                    {rec0.evidence.map((e: Json) => (
                      <tr key={e.invoice_id} className={e.same_vendor ? 'same' : ''}>
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

            {(r.capitalisation || r.amortisation) && (
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
                          <tr key={s.period}><td>{s.period}</td><td>{s.debit} Software Subscriptions</td><td>{s.credit} Prepaid</td><td className="num">{money(s.amount)}</td></tr>
                        ))}
                        <tr><td colSpan={4} className="muted small">…and {r.amortisation.schedule.length - 4} more months to {r.amortisation.schedule.at(-1).period}</td></tr>
                      </tbody>
                    </table>
                  </>
                )}
              </div>
            )}

            {r.receipt && (
              <div className="card" data-tour="receipt">
                <h3>Who asked for it, and did we get it?</h3>
                <div className="receipt">
                  <div>
                    <p><b>{requester?.name ?? 'Not identified'}</b> <span className="muted">{requester?.title}</span></p>
                    <p className="small muted">{r.requester.source}: {r.requester.evidence}</p>
                    <p style={{ marginTop: 8 }}>
                      {!r.receipt.required ? <span className="ok" style={{ color: 'var(--green)', fontWeight: 700 }}>Covered by standing rule.</span> :
                        task?.status === 'confirmed' ? <span style={{ color: 'var(--green)', fontWeight: 700 }}>Confirmed by {task.confirmed_by_name}, {dateTime(task.confirmed_at)}{task.note ? ` — “${task.note}”` : ''}</span> :
                          task ? <b>Waiting for {task.assignee_name} to confirm receipt (sent {dateTime(task.requested_at)}).</b> :
                            <b>Receipt confirmation needed.</b>}
                    </p>
                    {!r.receipt.required && <p className="small muted">{r.receipt.detail}</p>}
                    {r.receipt.required && task?.status !== 'confirmed' && requester && (
                      <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
                        {!task && <button type="button" className="btn small" disabled={busy}
                          onClick={() => act(() => api.requestReceipt(id, persona), `Request sent to ${requester.name}`)}>Send request to {requester.name}</button>}
                        <button type="button" className="btn small quiet" disabled={busy}
                          onClick={() => act(() => api.confirmReceipt(id, requester.id, 'Confirmed from the desktop'), `${requester.name} confirmed receipt`)}>
                          Confirm on {requester.name.split(' ')[0]}'s behalf
                        </button>
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

            {chain.length > 0 && (
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
                        nextApprover === s.person.id ? (
                          <button type="button" className="btn primary small" disabled={busy}
                            onClick={() => act(() => api.approve(id, s.person.id), `Approved by ${s.person.name}`)}>
                            Approve as {s.person.name.split(' ')[0]}
                          </button>
                        ) : null}
                    </div>,
                  ])}
                </div>
              </div>
            )}

            <div className="actions" data-tour="actions">
              <span className="next">{decision?.status === 'APPROVED' ? 'Approved. Included in today’s R12 AP interface file.' :
                decision?.status === 'IN_APPROVAL' ? `With ${personName(meta, nextApprover) || 'the approver'} for approval.` :
                  decision?.status === 'REJECTED' ? `Rejected: ${decision.reason}` : r.next_action}</span>
              {!decision && c && (
                <>
                  <button type="button" className="btn primary" disabled={!canSubmit || busy}
                    onClick={() => act(() => api.decide(id, { action: 'accept', actor: persona }), 'Accepted and sent for approval')}>
                    Accept and send for approval
                  </button>
                  <button type="button" className="btn" disabled={!canSubmit || busy} onClick={() => {
                    setOverriding('override')
                    setForm({ account: c.account, cost_centre: c.cost_centre, reason: '' })
                  }}>Override</button>
                  <button type="button" className="btn danger" disabled={busy} onClick={() => setOverriding('reject')}>Reject</button>
                </>
              )}
              {decision?.status === 'APPROVED' && <a className="btn small" href="/api/exports/ap-interface/lines">Download AP_INVOICE_LINES_INTERFACE</a>}
              {overriding && (
                <form className="override-form" onSubmit={(e) => {
                  e.preventDefault()
                  act(() => api.decide(id, { action: overriding, actor: persona, reason: form.reason,
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
                          pattern="CC\d{4}" style={{ border: '1px solid var(--line)', borderRadius: 6, padding: '8px 10px' }} />
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
          </>
        )}
      </section>
    </div>
  )
}
