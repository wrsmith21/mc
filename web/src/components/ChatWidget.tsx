import { Fragment, useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { api } from '../api'
import { brand } from '../brand'
import { useApp } from '../context'
import Icon from './Icon'

type Msg = { role: 'user' | 'assistant'; content: string; checked?: string[]; error?: boolean; greeting?: boolean }

const SUGGESTIONS = [
  'What’s held today, and why?',
  'Why is the Dell invoice going to 1540, not 6420?',
  'Which cash receipt was applied to the wrong customer?',
  'Where should we set up a blanket PO?',
]

// Invoice and case IDs in an answer become links into the app.
const ID = /\b(IN-\d{4}-\d{5}|WC-[A-Z0-9]{6}|[A-Z]{2}-[0-9A-F]{8})\b/g

function inline(text: string, key: string): ReactNode[] {
  const out: ReactNode[] = []
  text.split(/(\*\*[^*]+\*\*)/g).forEach((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      out.push(<b key={`${key}-b${i}`}>{part.slice(2, -2)}</b>)
      return
    }
    let last = 0
    for (const m of part.matchAll(ID)) {
      if (m.index! > last) out.push(part.slice(last, m.index))
      const id = m[1]
      const to = id.startsWith('IN-') || id.startsWith('WC-') ? `/invoice/${id}` : `/close?case=${id}`
      out.push(<Link key={`${key}-l${i}-${m.index}`} to={to}>{id}</Link>)
      last = m.index! + id.length
    }
    if (last < part.length) out.push(part.slice(last))
  })
  return out
}

function Rich({ text }: { text: string }) {
  const blocks: ReactNode[] = []
  let bullets: string[] = []
  const flush = (k: number) => {
    if (bullets.length) {
      blocks.push(<ul key={`u${k}`}>{bullets.map((b, i) => <li key={i}>{inline(b, `u${k}-${i}`)}</li>)}</ul>)
      bullets = []
    }
  }
  text.split('\n').forEach((line, k) => {
    const t = line.trim()
    if (/^[-•*] /.test(t)) {
      bullets.push(t.slice(2))
      return
    }
    flush(k)
    if (t) blocks.push(<p key={`p${k}`}>{inline(t, `p${k}`)}</p>)
  })
  flush(-1)
  return <>{blocks}</>
}

function pageContext(pathname: string, search: string) {
  const inv = pathname.match(/^\/invoice\/([^/]+)/)
  if (inv) return { page: 'invoice review', intake_id: inv[1] }
  const c = new URLSearchParams(search).get('case')
  if (c) return { page: 'close case', case_id: c }
  return { page: pathname === '/' ? 'my work' : pathname.slice(1) }
}

export default function ChatWidget() {
  const { session } = useApp()
  const location = useLocation()
  const first = session?.person?.name?.split(' ')[0]
  const greeting: Msg = {
    role: 'assistant', greeting: true,
    content: `Hi${first ? ` ${first}` : ''}, I’m the ${brand.product} assistant. Ask me anything about this morning’s non-PO invoices, the close or cash application: why something was coded or held, who approves it, what the agent found. I read the same data the agent works from; a person still makes every decision.`,
  }
  const [open, setOpen] = useState(false)
  const [msgs, setMsgs] = useState<Msg[]>([greeting])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' })
  }, [msgs, busy, open])

  const ask = async (question: string) => {
    const q = question.trim()
    if (!q || busy) return
    const next = [...msgs, { role: 'user' as const, content: q }]
    setMsgs(next)
    setText('')
    setBusy(true)
    try {
      const history = next.filter((m) => !m.greeting && !m.error).map(({ role, content }) => ({ role, content }))
      const r = await api.chat(history, pageContext(location.pathname, location.search))
      const checked = [...new Set<string>(r.checked.map((c: { tool: string }) => c.tool.replace(/_/g, ' ')))]
      setMsgs((m) => [...m, { role: 'assistant', content: r.reply, checked }])
    } catch (e) {
      setMsgs((m) => [...m, { role: 'assistant', content: (e as Error).message, error: true }])
    } finally {
      setBusy(false)
    }
  }

  const onKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      ask(text)
    }
    if (e.key === 'Escape') setOpen(false)
  }

  return (
    <>
      {open && (
        <section className="chat-panel" role="dialog" aria-label={`${brand.product} assistant`}>
          <header className="chat-head">
            <div>
              <b>Ask {brand.product}</b>
              <span>Answers from today’s invoices, close and cash · read-only</span>
            </div>
            <button type="button" className="chat-icon-btn" onClick={() => setOpen(false)} aria-label="Close assistant">
              <Icon name="dismiss" />
            </button>
          </header>
          <div className="chat-body" aria-live="polite">
            {msgs.map((m, i) => (
              <Fragment key={i}>
                <div className={`chat-msg ${m.role}${m.error ? ' error' : ''}`}>
                  {m.role === 'assistant' ? <Rich text={m.content} /> : <p>{m.content}</p>}
                  {m.checked && m.checked.length > 0 && <span className="chat-checked">Checked: {m.checked.join(' · ')}</span>}
                </div>
                {m.greeting && msgs.length === 1 && (
                  <div className="chat-suggestions">
                    {SUGGESTIONS.map((s) => <button key={s} type="button" onClick={() => ask(s)}>{s}</button>)}
                  </div>
                )}
              </Fragment>
            ))}
            {busy && <div className="chat-msg assistant typing" aria-label="Thinking"><span /><span /><span /></div>}
            <div ref={endRef} />
          </div>
          <form className="chat-input" onSubmit={(e) => { e.preventDefault(); ask(text) }}>
            <textarea ref={inputRef} rows={1} value={text} maxLength={2000} placeholder="Ask about an invoice, a case or today’s numbers"
              onChange={(e) => setText(e.target.value)} onKeyDown={onKey} aria-label="Your question" />
            <button type="submit" className="chat-send" disabled={busy || !text.trim()} aria-label="Send">
              <Icon name="send" />
            </button>
          </form>
        </section>
      )}
      <button type="button" className={`chat-fab${open ? ' open' : ''}`} onClick={() => setOpen((o) => !o)}
        aria-label={open ? 'Close assistant' : `Ask ${brand.product}`} aria-expanded={open}>
        <Icon name={open ? 'dismiss' : 'chat'} />
      </button>
    </>
  )
}
