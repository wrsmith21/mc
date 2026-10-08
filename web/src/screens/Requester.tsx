import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, type Json } from '../api'
import { brand } from '../brand'
import { useApp } from '../context'
import { dateTime, money } from '../format'

// The requester's phone: open receipt-confirmation tasks, one tap to confirm.
export default function Requester() {
  const [params] = useSearchParams()
  const person = params.get('person') ?? undefined
  const { toast } = useApp()
  const [tasks, setTasks] = useState<Json[]>([])
  const [done, setDone] = useState<Json[]>([])
  const [notes, setNotes] = useState<Record<string, string>>({})

  useEffect(() => {
    const load = () => api.tasks(person).then(setTasks).catch(() => {})
    load()
    const t = window.setInterval(load, 2500)
    return () => window.clearInterval(t)
  }, [person])

  const confirm = async (t: Json) => {
    try {
      await api.confirmReceipt(t.intake_id, notes[t.intake_id] || 'Service received as invoiced.', t.assignee_id)
      setDone((d) => [{ ...t, confirmed_at: new Date().toISOString() }, ...d])
      setTasks((ts) => ts.filter((x) => x.intake_id !== t.intake_id))
      toast('Thanks — Accounts Payable can now approve it')
    } catch (e) {
      toast((e as Error).message, 'error')
    }
  }

  const who = tasks[0]?.assignee_name ?? done[0]?.assignee_name
  return (
    <div className="phone">
      <header>
        {brand.logo && <img src={brand.logo} alt={brand.client} />}
        <div>
          <b>Confirm what you received</b>
          <div className="small muted">{who ? `${who} · ` : ''}Accounts Payable requests</div>
        </div>
      </header>
      {tasks.length === 0 && done.length === 0 && (
        <p className="muted">Nothing to confirm right now. New requests appear here as soon as the agent sends them.</p>
      )}
      {tasks.map((t) => (
        <article key={t.intake_id} className="task">
          <div className="small muted">{t.vendor} · {t.invoice_num} · sent {dateTime(t.requested_at)}</div>
          <div className="amt">{money(t.amount, t.currency)}</div>
          <p>{t.description}</p>
          <p className="small muted" style={{ marginTop: 8 }}>Why you: {t.evidence}</p>
          <textarea placeholder="Optional note, for example what was delivered" value={notes[t.intake_id] ?? ''}
            onChange={(e) => setNotes({ ...notes, [t.intake_id]: e.target.value })} aria-label="Note for Accounts Payable" />
          <button type="button" className="btn accent" onClick={() => confirm(t)}>Yes, we received this</button>
          <p className="small muted" style={{ marginTop: 8 }}>Not yours or not received? Reply to the AP email and it is routed back to Accounts Payable.</p>
        </article>
      ))}
      {done.map((t) => (
        <article key={`done-${t.intake_id}`} className="task done">
          <b>Confirmed</b>
          <div className="small">{t.vendor} · {t.invoice_num} · {money(t.amount, t.currency)}</div>
        </article>
      ))}
      <p className="small muted" style={{ marginTop: 20 }}>{brand.disclaimer}</p>
    </div>
  )
}
