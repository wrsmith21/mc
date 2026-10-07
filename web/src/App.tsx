import { Suspense, lazy, useCallback, useEffect, useRef, useState } from 'react'
import { NavLink, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { api, type Json } from './api'
import { brand } from './brand'
import Walkthrough from './components/Walkthrough'
import { AppCtx } from './context'
import Anomalies from './screens/Anomalies'
import Login from './screens/Login'
import Queue from './screens/Queue'
import Requester from './screens/Requester'
import Review from './screens/Review'
import { TOUR, type TourStep } from './walkthrough'

const Insights = lazy(() => import('./screens/Insights'))

export default function App() {
  const [meta, setMeta] = useState<Json | null>(null)
  const [needLogin, setNeedLogin] = useState(false)
  const [persona, setPersona] = useState('E34120')
  const [toastMsg, setToastMsg] = useState<{ msg: string; kind: string } | null>(null)
  const [version, setVersion] = useState(0)
  const [tour, setTour] = useState(false)
  const [pending, setPending] = useState(0)
  const timer = useRef<number | undefined>(undefined)
  const location = useLocation()
  const navigate = useNavigate()

  const toast = useCallback((msg: string, kind: 'ok' | 'error' = 'ok') => {
    setToastMsg({ msg, kind })
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setToastMsg(null), 3600)
  }, [])
  const bump = useCallback(() => setVersion((v) => v + 1), [])

  useEffect(() => {
    const onAuth = () => setNeedLogin(true)
    window.addEventListener('mc-auth-required', onAuth)
    api.meta().then(setMeta).catch(() => {})
    return () => window.removeEventListener('mc-auth-required', onAuth)
  }, [needLogin])

  useEffect(() => {
    api.queue().then((q: Json[]) => setPending(q.filter((r) => !['APPROVED', 'REJECTED', 'IN_APPROVAL'].includes(r.status)).length)).catch(() => {})
  }, [version, meta])

  if (needLogin) return <Login onDone={() => setNeedLogin(false)} />
  if (location.pathname.startsWith('/requester')) {
    return (
      <AppCtx.Provider value={{ meta, persona, setPersona, toast, bump, version, pace: 1 }}>
        <Requester />
        {toastMsg && <div className={`toast ${toastMsg.kind}`} role="status">{toastMsg.msg}</div>}
      </AppCtx.Provider>
    )
  }

  const resolvePath = (s: TourStep) => (s.invoice ? `/invoice/${meta?.storyboard?.[s.invoice] ?? ''}` : s.path ?? '/')

  const reset = async () => {
    if (!window.confirm('Reset the demo to its starting state? Every decision made in this session is cleared.')) return
    await api.reset()
    bump()
    navigate('/')
    toast('Demo reset to the start of 15 October')
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

  return (
    <AppCtx.Provider value={{ meta, persona, setPersona, toast, bump, version, pace: 1 }}>
      <div className="app">
        <header className="topbar" data-tour="topbar">
          {brand.logo && <img className="logo" src={brand.logo} alt={brand.client} />}
          <div className="product">
            <b>{brand.product}</b>
            <span>{brand.unit}</span>
          </div>
          <div className="spacer" />
          <span className={`mode ${meta?.mode === 'live' ? '' : 'replay'}`} title={meta?.model}>
            {meta?.mode === 'live' ? 'Live · Claude connected' : 'Replay mode'}
          </span>
          <span className="disclaimer" data-tour="disclaimer">{brand.disclaimer}</span>
          <label className="persona" data-tour="persona">
            Acting as
            <select value={persona} onChange={(e) => setPersona(e.target.value)}>
              {(meta?.personas ?? []).map((p: Json) => (
                <option key={p.id} value={p.id}>{p.name} — {p.title}</option>
              ))}
            </select>
          </label>
        </header>
        <nav className="nav" aria-label="Main">
          <NavLink to="/" end>Invoice queue {pending > 0 && <span className="count">{pending}</span>}</NavLink>
          <NavLink to="/anomalies">Anomaly layer</NavLink>
          <NavLink to="/insights">Value & procurement</NavLink>
          <a href="/requester" target="_blank" rel="noreferrer">Requester phone view</a>
          <div className="sep" />
          <div className="tools">
            <button type="button" className="tour" onClick={() => setTour(true)}>Start walkthrough</button>
            {meta?.wildcard && (
              <label data-tour="wildcard">
                Process a new invoice…
                <input type="file" accept="application/pdf" onChange={(e) => upload(e.target.files?.[0])} />
              </label>
            )}
            <button type="button" onClick={reset}>Reset demo</button>
          </div>
        </nav>
        <main className="main">
          <Routes>
            <Route path="/" element={<Queue />} />
            <Route path="/invoice/:id" element={<Review />} />
            <Route path="/anomalies" element={<Anomalies />} />
            <Route path="/insights" element={<Suspense fallback={<p className="muted">Loading charts…</p>}><Insights /></Suspense>} />
          </Routes>
        </main>
      </div>
      <Walkthrough steps={TOUR} active={tour} onClose={() => setTour(false)} resolvePath={resolvePath} />
      {toastMsg && <div className={`toast ${toastMsg.kind}`} role="status">{toastMsg.msg}</div>}
    </AppCtx.Provider>
  )
}
