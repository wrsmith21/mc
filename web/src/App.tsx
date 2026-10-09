import { Suspense, lazy, useCallback, useEffect, useRef, useState } from 'react'
import { NavLink, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { api, ApiError, type Json } from './api'
import { brand } from './brand'
import Icon from './components/Icon'
import Walkthrough from './components/Walkthrough'
import { AppCtx, type Session } from './context'
import Audit from './screens/Audit'
import Close from './screens/Close'
import Inbox from './screens/Inbox'
import Login from './screens/Login'
import Operations from './screens/Operations'
import Policies from './screens/Policies'
import Queue from './screens/Queue'
import Requester from './screens/Requester'
import Review from './screens/Review'
import SignIn from './screens/SignIn'
import { TOUR, type TourStep } from './walkthrough'

const Insights = lazy(() => import('./screens/Insights'))
const Architecture = lazy(() => import('./screens/Architecture'))
const Model = lazy(() => import('./screens/Model'))

const loadingLine = <p className="muted">Loading…</p>

export default function App() {
  const [meta, setMeta] = useState<Json | null>(null)
  const [needLogin, setNeedLogin] = useState(false)
  const [session, setSession] = useState<Session | null | undefined>(undefined)
  const [choosing, setChoosing] = useState(false)
  const [toastMsg, setToastMsg] = useState<{ msg: string; kind: string } | null>(null)
  const [version, setVersion] = useState(0)
  const [tour, setTour] = useState(false)
  const [counts, setCounts] = useState({ fresh: 0, mine: 0 })
  const [slow, setSlow] = useState(() => {
    try {
      return localStorage.getItem('mc-slow') === '1'
    } catch {
      return false
    }
  })
  const timer = useRef<number | undefined>(undefined)
  const location = useLocation()
  const navigate = useNavigate()

  const toast = useCallback((msg: string, kind: 'ok' | 'error' = 'ok') => {
    setToastMsg({ msg, kind })
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setToastMsg(null), 4200)
  }, [])
  const bump = useCallback(() => setVersion((v) => v + 1), [])

  useEffect(() => {
    const onAuth = () => setNeedLogin(true)
    const onSignIn = () => setChoosing(true)
    const onUnhandled = (e: PromiseRejectionEvent) => {
      if (!(e.reason instanceof ApiError) || e.reason.status === 401) return
      e.preventDefault()
      toast(e.reason.message, 'error')
    }
    window.addEventListener('mc-auth-required', onAuth)
    window.addEventListener('mc-signin-required', onSignIn)
    window.addEventListener('unhandledrejection', onUnhandled)
    api.meta().then(setMeta).catch(() => {})
    api.session().then((s) => setSession(s.person ? s : null)).catch(() => setSession(null))
    return () => {
      window.removeEventListener('mc-auth-required', onAuth)
      window.removeEventListener('mc-signin-required', onSignIn)
      window.removeEventListener('unhandledrejection', onUnhandled)
    }
  }, [needLogin, toast])

  useEffect(() => {
    if (!session) return
    api.queue().then((q: Json[]) => setCounts({
      fresh: q.filter((r) => r.status === 'NEW').length,
      mine: q.filter((r) => r.next_approver === session.person.id).length,
    })).catch(() => {})
  }, [version, session])

  const toggleSlow = () => {
    setSlow((v) => {
      try {
        localStorage.setItem('mc-slow', v ? '0' : '1')
      } catch {
        /* storage unavailable: setting lasts for this visit */
      }
      return !v
    })
  }

  if (needLogin) return <Login onDone={() => setNeedLogin(false)} />
  if (location.pathname.startsWith('/requester')) {
    return (
      <AppCtx.Provider value={{ meta, session: session ?? null, switchUser: () => {}, toast, bump, version, slow: false }}>
        <Requester />
        {toastMsg && <div className={`toast ${toastMsg.kind}`} role="status">{toastMsg.msg}</div>}
      </AppCtx.Provider>
    )
  }
  if (session === undefined) return <div className="center-page"><p className="muted">Loading…</p></div>
  if (!session || choosing) {
    return <SignIn current={session?.person?.id} onDone={(s) => {
      setSession(s)
      setChoosing(false)
      bump()
      navigate('/')
    }} />
  }

  const roles = session.roles
  const has = (...r: string[]) => r.some((x) => roles.includes(x))
  const resolvePath = (s: TourStep) =>
    s.invoice ? `/invoice/${meta?.storyboard?.[s.invoice] ?? ''}?tab=${s.tab ?? 'decision'}` : s.path ?? '/'

  const reset = async () => {
    if (!window.confirm('Reset the demo to its starting state? Every decision, run and policy change made in this session is cleared.')) return
    try {
      await api.reset()
      bump()
      navigate('/')
      toast('Demo reset to the morning of 15 October')
    } catch (e) {
      toast((e as Error).message, 'error')
    }
  }

  const upload = async (file?: File) => {
    if (!file) return
    toast(`Reading ${file.name} with Claude…`)
    try {
      const r = await api.wildcard(file)
      bump()
      navigate(`/invoice/${r.intake_id}?run=1`)
    } catch (e) {
      toast((e as Error).message, 'error')
    }
  }

  const advance = async () => {
    try {
      const r = await api.advanceClock(24)
      toast(`Clock moved to ${r.now.replace('T', ' ').slice(0, 16)} · ${r.sla_events.length} SLA action(s)`)
      bump()
      api.meta().then(setMeta)
    } catch (e) {
      toast((e as Error).message, 'error')
    }
  }

  return (
    <AppCtx.Provider value={{ meta, session, switchUser: () => setChoosing(true), toast, bump, version, slow }}>
      <div className="app">
        <header className="topbar" data-tour="topbar">
          {brand.logo && <img className="logo" src={brand.logo} alt={brand.client} />}
          <div className="product">
            <b title={brand.expansion}>{brand.product}</b>
            <span>{brand.unit}</span>
          </div>
          <div className="spacer" />
          <span className="clock" title="Demo clock">{meta?.now ? `${meta.now.slice(0, 10)} ${meta.now.slice(11, 16)}` : ''}</span>
          {meta?.mode && (
            <span className={`mode ${meta.mode === 'live' ? '' : 'replay'}`} title={meta.model}>
              {meta.mode === 'live' ? 'Claude connected' : 'Replay mode'}
            </span>
          )}
          <label className="pace" title="Spaces out agent events on screen for presenting. The agent itself never waits.">
            <input type="checkbox" checked={slow} onChange={toggleSlow} /> Presentation pace
          </label>
          <span className="divider" />
          <button type="button" className="user" onClick={() => setChoosing(true)} data-tour="persona" title="Switch user (logged)">
            <span className="avatar">{session.person.name.split(' ').map((w: string) => w[0]).join('').slice(0, 2)}</span>
            <span className="who">
              <b>{session.person.name}</b>
              <span>{session.role_labels.filter((l) => l !== 'Requester').join(', ') || 'Requester'}</span>
            </span>
          </button>
        </header>
        <nav className="nav" aria-label="Main">
          <div className="nav-group">Work</div>
          <NavLink to="/" end><Icon name="inbox" /><span className="label">My work</span>{(counts.mine > 0 || (has('ap_specialist') && counts.fresh > 0)) && <span className="count">{has('ap_specialist') ? counts.fresh : counts.mine}</span>}</NavLink>
          <NavLink to="/queue"><Icon name="queue" /><span className="label">Invoice queue</span></NavLink>
          <NavLink to="/close"><Icon name="close" /><span className="label">Close and anomalies</span></NavLink>
          <div className="nav-group">Insight</div>
          <NavLink to="/insights"><Icon name="value" /><span className="label">Value and procurement</span></NavLink>
          <NavLink to="/model"><Icon name="model" /><span className="label">Model and data</span></NavLink>
          <NavLink to="/architecture"><Icon name="arch" /><span className="label">Architecture</span></NavLink>
          <div className="nav-group">Governance</div>
          <NavLink to="/policies"><Icon name="policy" /><span className="label">Policies</span></NavLink>
          <NavLink to="/audit"><Icon name="audit" /><span className="label">Audit log</span></NavLink>
          <NavLink to="/operations"><Icon name="ops" /><span className="label">Operations</span></NavLink>
          <a href="/requester" target="_blank" rel="noreferrer"><Icon name="phone" /><span className="label">Requester phone view</span></a>
          <div className="sep" />
          <div className="tools">
            <button type="button" className="tour" onClick={() => setTour(true)}><Icon name="play" />Start walkthrough</button>
            {meta?.wildcard && has('ap_specialist', 'admin') && (
              <label data-tour="wildcard">
                <Icon name="upload" />Process a new invoice…
                <input type="file" accept="application/pdf" onChange={(e) => upload(e.target.files?.[0])} />
              </label>
            )}
            {has('admin') && <button type="button" onClick={advance}><Icon name="clock" />Advance clock 24h</button>}
            {has('admin', 'ap_specialist') && <button type="button" onClick={reset}><Icon name="reset" />Reset demo</button>}
          </div>
          <p className="disclaimer" data-tour="disclaimer">{brand.disclaimer}</p>
        </nav>
        <main className="main">
          <Routes>
            <Route path="/" element={<Inbox />} />
            <Route path="/queue" element={<Queue />} />
            <Route path="/invoice/:id" element={<Review />} />
            <Route path="/close" element={<Close />} />
            <Route path="/anomalies" element={<Navigate to="/close" replace />} />
            <Route path="/insights" element={<Suspense fallback={loadingLine}><Insights /></Suspense>} />
            <Route path="/model" element={<Suspense fallback={loadingLine}><Model /></Suspense>} />
            <Route path="/architecture" element={<Suspense fallback={loadingLine}><Architecture /></Suspense>} />
            <Route path="/policies" element={<Policies />} />
            <Route path="/audit" element={<Audit />} />
            <Route path="/operations" element={<Operations />} />
          </Routes>
        </main>
      </div>
      <Walkthrough steps={TOUR} active={tour} onClose={() => setTour(false)} resolvePath={resolvePath} />
      {toastMsg && <div className={`toast ${toastMsg.kind}`} role="status">{toastMsg.msg}</div>}
    </AppCtx.Provider>
  )
}
