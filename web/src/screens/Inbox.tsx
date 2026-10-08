import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, mailboxStream, type Json } from '../api'
import StatusChip from '../components/StatusChip'
import { useApp, useCan } from '../context'
import { dateTime, money } from '../format'

type Item = { key: string; to: string; title: string; sub: string; amount?: string; chip?: Json; due?: string; late?: boolean }

function Section({ title, why, items, empty, action }: { title: string; why: string; items: Item[]; empty: string; action?: React.ReactNode }) {
  const navigate = useNavigate()
  return (
    <section className="card inbox-section">
      <div className="card-head">
        <div>
          <h3>{title} <span className="count-pill">{items.length}</span></h3>
          <p className="muted small">{why}</p>
        </div>
        {action}
      </div>
      {items.length === 0 ? <p className="muted">{empty}</p> : (
        <ul className="inbox-list">
          {items.slice(0, 12).map((i) => (
            <li key={i.key}>
              <button type="button" onClick={() => navigate(i.to)}>
                <div><b>{i.title}</b><span>{i.sub}</span></div>
                {i.amount && <span className="amt">{i.amount}</span>}
                {i.chip}
                {i.due && <span className={`due${i.late ? ' late' : ''}`}>{i.late ? 'Overdue · ' : 'Due '}{i.due}</span>}
              </button>
            </li>
          ))}
          {items.length > 12 && <li className="muted small">…and {items.length - 12} more</li>}
        </ul>
      )}
    </section>
  )
}

export default function Inbox() {
  const { session, version, bump, toast } = useApp()
  const can = useCan()
  const [rows, setRows] = useState<Json[]>([])
  const [work, setWork] = useState<Json | null>(null)
  const [cases, setCases] = useState<Json[]>([])
  const [mine, setMine] = useState<Json[]>([])
  const [mailbox, setMailbox] = useState<{ done: number; total: number; running: boolean }>({ done: 0, total: 0, running: false })
  const me = session?.person?.id

  useEffect(() => {
    api.queue().then(setRows)
    api.work().then(setWork)
    api.cases().then(setCases)
    if (me) api.tasks(me).then(setMine)
  }, [version, me])

  const runMailbox = () => {
    setMailbox({ done: 0, total: 0, running: true })
    mailboxStream((e) => {
      if (e.type === 'start') setMailbox({ done: 0, total: e.count, running: true })
      if (e.type === 'invoice') setMailbox((m) => ({ ...m, done: m.done + 1 }))
      if (e.type === 'done') {
        setMailbox((m) => ({ ...m, running: false }))
        toast(`Agent worked ${e.count} invoices in ${(e.ms / 1000).toFixed(1)} s`)
        bump()
      }
      if (e.type === 'error' && !e.intake_id) {
        setMailbox((m) => ({ ...m, running: false }))
        toast(e.message, 'error')
      }
    })
  }

  const inv = (r: Json, sub?: string): Item => ({
    key: r.intake_id, to: `/invoice/${r.intake_id}`, title: r.vendor, amount: money(r.total, r.currency),
    sub: sub ?? `${r.invoice_num} · received ${dateTime(r.received_at)}`, chip: <StatusChip status={r.status} label={r.status_label} />,
  })
  const caseItem = (c: Json): Item => ({
    key: c.case_id, to: `/close?case=${c.case_id}`, title: c.type_label, sub: `${c.reference} · ${c.case_id}`,
    amount: money(c.amount, c.currency, 0), due: c.sla_due, late: c.overdue,
  })

  const fresh = rows.filter((r) => r.status === 'NEW')
  const toDecide = rows.filter((r) => !r.decided && ['RECOMMENDED', 'NEEDS_CODING', 'FAST_TRACK'].includes(r.status))
  const held = rows.filter((r) => ['HELD', 'VENDOR_ONBOARDING', 'MATCH_TO_PO', 'AWAITING_CONFIRMATION'].includes(r.status) && !r.decided)
  const toApprove = rows.filter((r) => r.next_approver === me)
  const roles = session?.roles ?? []
  const prepJ = cases.filter((c) => c.status === 'Open' && c.source !== 'cash')
  const apprJ = cases.filter((c) => c.status === 'Pending approval' && c.source !== 'cash')
  const prepC = cases.filter((c) => c.status === 'Open' && c.source === 'cash')
  const apprC = cases.filter((c) => c.status === 'Pending approval' && c.source === 'cash')

  return (
    <>
      <div className="page-head">
        <div>
          <h1>My work</h1>
          <p>{session?.person?.name}, {session?.person?.title}. What is waiting for you, oldest and most urgent first. Everything else is visible but read-only.</p>
        </div>
      </div>

      <div className="inbox-grid" data-tour="inbox">
        {roles.includes('ap_specialist') && (
          <>
            <Section title="This morning's mailbox" why="Arrived since 06:00 and not yet worked by the agent."
              items={fresh.map((r) => inv(r))} empty="Everything received has been worked."
              action={can('run_agent') && fresh.length > 0 && (
                <button type="button" className="btn accent" onClick={runMailbox} disabled={mailbox.running} data-tour="run-mailbox">
                  {mailbox.running ? `Working ${mailbox.done} of ${mailbox.total}…` : `Run the agent on ${fresh.length}`}
                </button>
              )} />
            <Section title="Ready for your decision" why="Worked by the agent; accept, override with a reason, or reject."
              items={toDecide.map((r) => inv(r, `${r.account ?? '—'} · ${Math.round((r.confidence ?? 0) * 100)}% · ${r.invoice_num}`))}
              empty="Nothing waiting for a coding decision." />
            <Section title="Held or waiting" why="Controls holding an invoice, or a requester yet to confirm receipt."
              items={held.map((r) => inv(r, r.flags[0]?.title ?? r.status_label))} empty="No holds." />
          </>
        )}
        {roles.includes('approver') && (
          <Section title="Waiting for your approval" why="You are the next approver in the chain. Out-of-turn approvals are refused."
            items={toApprove.map((r) => inv(r))} empty="Nothing waiting for your approval." />
        )}
        {mine.length > 0 && (
          <Section title="Confirm you received it" why="You asked for these. With no PO, your confirmation is the evidence of receipt."
            items={mine.map((t) => ({ key: t.intake_id, to: `/invoice/${t.intake_id}`, title: t.vendor,
              sub: `${t.invoice_num} · ${t.description}`, amount: money(t.amount, t.currency), due: t.sla?.reminder ? 'reminder sent' : undefined }))}
            empty="" />
        )}
        {roles.includes('gl_accountant') && (
          <Section title="Corrections to prepare" why="Journal and AP findings with a drafted fix. Review, adjust, submit."
            items={prepJ.map(caseItem)} empty="No open findings." />
        )}
        {roles.includes('controller') && (
          <Section title="Corrections to approve" why="Prepared by someone else; you cannot approve your own or a fix to an entry you posted."
            items={apprJ.map(caseItem)} empty="Nothing waiting for approval."
            action={<Link className="btn small" to="/close">Close dashboard</Link>} />
        )}
        {roles.includes('cash_preparer') && (
          <Section title="Cash to re-apply or match" why="Misapplied receipts and unapplied cash with a proposed match."
            items={prepC.map(caseItem)} empty="No open cash exceptions." />
        )}
        {roles.includes('cash_lead') && (
          <Section title="Cash fixes to approve" why="Prepared re-applications and matches." items={apprC.map(caseItem)} empty="Nothing waiting." />
        )}
        {roles.includes('vendor_master') && work && (
          <>
            <Section title="Call-back verification" why="Bank details changed recently on a held invoice. Call the supplier on the number on file."
              items={work.vendor_review.map((r: Json) => inv(r, `Bank change ${r.bank_change?.date ?? ''} via ${r.bank_change?.request_channel ?? '—'}`))}
              empty="No call-backs outstanding." />
            <Section title="Supplier onboarding" why="Invoices from suppliers not in the vendor master." items={work.onboarding.map((r: Json) => inv(r))}
              empty="No suppliers waiting." />
          </>
        )}
        {roles.includes('procurement') && work && (
          <Section title="PO compliance" why="Invoices that should have had a PO, and blanket-PO requests raised."
            items={[...rows.filter((r) => r.flags.some((f: Json) => f.code === 'PO_POLICY')).map((r) => inv(r, 'Should have been a PO')),
              ...work.po_requests.map((p: Json) => ({ key: p.vendor_id, to: '/insights', title: `${p.kind}: ${p.vendor}`, sub: `Requested by ${p.by_name}` }))]}
            empty="No breaches today." action={<Link className="btn small" to="/insights">Blanket-PO candidates</Link>} />
        )}
        {roles.includes('admin') && (
          <Section title="Administration" why="Policy versions, the demo clock and the audit log."
            items={[{ key: 'p', to: '/policies', title: 'Policies', sub: 'Approval matrix, thresholds, confidence bands' },
              { key: 'a', to: '/audit', title: 'Audit log', sub: 'Every action, including refused ones' },
              { key: 'o', to: '/operations', title: 'Operations', sub: 'Runs, latency, model usage' }]} empty="" />
        )}
      </div>
    </>
  )
}
