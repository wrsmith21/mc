import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import type { TourStep } from '../walkthrough'

type Rect = { top: number; left: number; width: number; height: number; right: number; bottom: number }

function cardPosition(rect: Rect | null) {
  const width = 390
  const height = 300
  const margin = 16
  if (!rect) return { top: 96, left: Math.max(margin, window.innerWidth / 2 - width / 2) }
  const maxLeft = window.innerWidth - width - margin
  const maxTop = window.innerHeight - height - margin
  const center = Math.max(margin, Math.min(maxLeft, rect.left + rect.width / 2 - width / 2))
  const sideTop = Math.max(margin, Math.min(maxTop, rect.top))
  if (rect.right + width + margin < window.innerWidth) return { top: sideTop, left: rect.right + margin }
  if (rect.left - width - margin > margin) return { top: sideTop, left: rect.left - width - margin }
  if (rect.bottom + height + margin < window.innerHeight) return { top: rect.bottom + margin, left: center }
  if (rect.top - height - margin > margin) return { top: rect.top - height - margin, left: center }
  return { top: Math.max(margin, maxTop), left: center }
}

function holePath(r: Rect) {
  const { left: x1, top: y1, right: x2, bottom: y2 } = r
  return `polygon(evenodd, 0 0, 100% 0, 100% 100%, 0 100%, 0 0, ${x1}px ${y1}px, ${x2}px ${y1}px, ${x2}px ${y2}px, ${x1}px ${y2}px, ${x1}px ${y1}px)`
}

type Props = { steps: TourStep[]; active: boolean; onClose: () => void; resolvePath: (s: TourStep) => string }

export default function Walkthrough({ steps, active, onClose, resolvePath }: Props) {
  const [index, setIndex] = useState(0)
  const [rect, setRect] = useState<Rect | null>(null)
  const [ready, setReady] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const step = steps[index]
  const path = step ? resolvePath(step) : ''

  useEffect(() => {
    if (active) {
      setIndex(0)
      setRect(null)
      setReady(false)
    }
  }, [active])

  useEffect(() => {
    if (active && step && location.pathname !== path) navigate(path)
  }, [active, step, path, location.pathname, navigate])

  useEffect(() => {
    if (!active || !step || location.pathname !== path) return
    let cancelled = false
    let target: Element | null = null
    setRect(null)
    setReady(false)
    const clear = () => document.querySelectorAll('.tour-focus').forEach((n) => n.classList.remove('tour-focus'))
    const measure = () => {
      if (cancelled) return
      target = document.querySelector(`[data-tour="${step.target}"]`)
      if (!target) {
        setRect(null)
        return
      }
      const r = target.getBoundingClientRect()
      const pad = 8
      setRect({ top: r.top - pad, left: r.left - pad, width: r.width + pad * 2, height: r.height + pad * 2,
        right: r.right + pad, bottom: r.bottom + pad })
    }
    let tries = 0
    const locate = () => {
      if (cancelled) return
      clear()
      target = document.querySelector(`[data-tour="${step.target}"]`)
      if (!target && tries++ < 25) {
        window.setTimeout(locate, 200)
        return
      }
      if (target) {
        target.scrollIntoView({ behavior: 'smooth', block: 'center' })
        window.setTimeout(() => {
          target?.classList.add('tour-focus')
          measure()
          setReady(true)
        }, 360)
      } else {
        setReady(true)
      }
    }
    const timer = window.setTimeout(locate, 150)
    window.addEventListener('resize', measure)
    window.addEventListener('scroll', measure, true)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
      window.removeEventListener('resize', measure)
      window.removeEventListener('scroll', measure, true)
      clear()
    }
  }, [active, step, path, location.pathname])

  useEffect(() => {
    if (!active) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowRight') setIndex((i) => Math.min(steps.length - 1, i + 1))
      if (e.key === 'ArrowLeft') setIndex((i) => Math.max(0, i - 1))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [active, steps.length, onClose])

  const position = useMemo(() => cardPosition(rect), [rect])
  if (!active || !step) return null
  const last = index === steps.length - 1

  return (
    <div className="walkthrough-layer" role="dialog" aria-modal="true" aria-label="Guided walkthrough">
      <div className="walkthrough-dim" style={rect ? { clipPath: holePath(rect) } : undefined} />
      {rect && <div className="walkthrough-spotlight" style={{ top: rect.top, left: rect.left, width: rect.width, height: rect.height }} />}
      {ready && (
        <aside className="walkthrough-card" style={position}>
          <button className="walkthrough-close" type="button" onClick={onClose} aria-label="Close walkthrough">✕</button>
          <div className="meta">
            <span>{step.scene}</span>
            <b>{index + 1} / {steps.length}</b>
          </div>
          <h3>{step.title}</h3>
          <p>{step.body}</p>
          {step.talk && <p className="talk">{step.talk}</p>}
          <div className="walkthrough-progress" style={{ gridTemplateColumns: `repeat(${steps.length}, 1fr)` }}>
            {steps.map((s, i) => <span key={s.id} className={i <= index ? 'on' : ''} />)}
          </div>
          <footer>
            <button className="btn quiet small" type="button" onClick={onClose}>Skip</button>
            <div>
              <button className="btn quiet small" type="button" disabled={index === 0} onClick={() => setIndex(index - 1)}>Back</button>
              <button className="btn accent small" type="button" onClick={() => (last ? onClose() : setIndex(index + 1))}>
                {last ? 'Finish' : 'Next'}
              </button>
            </div>
          </footer>
        </aside>
      )}
    </div>
  )
}
