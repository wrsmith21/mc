import { useEffect, useMemo, useRef, useState } from 'react'
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
  // a card belongs to the step it was located for, so the next step never flashes the previous step's card
  const [shown, setShown] = useState<{ index: number; rect: Rect | null } | null>(null)
  const [pressing, setPressing] = useState(false)
  const pressingRef = useRef(false)
  const navigate = useNavigate()
  const location = useLocation()
  const step = steps[index]
  const path = step ? resolvePath(step) : ''
  const onPage = location.pathname === path.split('?')[0]
  const ready = shown?.index === index
  const rect = ready ? shown.rect : null

  useEffect(() => {
    if (active) {
      setIndex(0)
      setShown(null)
      pressingRef.current = false
      setPressing(false)
    }
  }, [active])

  // navigate once per step; the presenter can still click around the page without being pulled back
  useEffect(() => {
    if (active && step && location.pathname + location.search !== path) navigate(path)
  }, [active, index, path]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!active || !step || !onPage) return
    let cancelled = false
    let target: Element | null = null
    let frame = 0
    let last = ''
    const find = () => document.querySelector(`[data-tour="${step.target}"]`)
    const clear = () => document.querySelectorAll('.tour-focus').forEach((n) => n.classList.remove('tour-focus'))
    const measure = () => {
      if (cancelled || !target) return
      const r = target.getBoundingClientRect()
      const key = `${r.top}|${r.left}|${r.width}|${r.height}`
      if (key === last) return
      last = key
      const pad = 8
      setShown({ index, rect: { top: r.top - pad, left: r.left - pad, width: r.width + pad * 2, height: r.height + pad * 2,
        right: r.right + pad, bottom: r.bottom + pad } })
    }
    const focus = (el: Element) => {
      target = el
      clear()
      el.classList.add('tour-focus')
      const r = el.getBoundingClientRect()
      if (r.top >= 60 && r.bottom <= window.innerHeight - 16) {
        measure()
        return
      }
      el.scrollIntoView({ behavior: 'smooth', block: r.height > window.innerHeight - 140 ? 'start' : 'center' })
      let done = false
      const settled = () => {
        if (done) return
        done = true
        window.removeEventListener('scrollend', settled, true)
        measure()
      }
      window.addEventListener('scrollend', settled, true)
      window.setTimeout(settled, 450)
    }
    // the target appears when the page's data arrives; watch for it instead of polling, and follow re-renders
    const check = () => {
      frame = 0
      if (cancelled) return
      const el = find()
      // done when the button gives way to its finished state; an error toast means the press failed
      if (pressingRef.current) {
        const finished = !!el && el.tagName !== 'BUTTON'
        if (finished || document.querySelector('.toast.error')) {
          pressingRef.current = false
          setPressing(false)
          if (finished) setIndex((i) => Math.min(steps.length - 1, i + 1))
        }
      }
      if (el && el !== target) focus(el)
      else if (el) measure()
    }
    const observer = new MutationObserver(() => {
      if (!frame) frame = window.requestAnimationFrame(check)
    })
    observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['data-tour'] })
    const giveUp = window.setTimeout(() => {
      if (!target && !cancelled) setShown({ index, rect: null })
    }, 3000)
    check()
    window.addEventListener('resize', measure)
    window.addEventListener('scroll', measure, true)
    return () => {
      cancelled = true
      observer.disconnect()
      window.cancelAnimationFrame(frame)
      window.clearTimeout(giveUp)
      window.removeEventListener('resize', measure)
      window.removeEventListener('scroll', measure, true)
      clear()
    }
  }, [active, step, index, onPage, steps.length])

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
  const pressable = step.press && ready
    ? document.querySelector(`[data-tour="${step.target}"]`) : null
  const canPress = pressable instanceof HTMLButtonElement && !pressable.disabled
  const next = () => {
    if (canPress) {
      pressingRef.current = true
      setPressing(true)
      pressable.click()
      window.setTimeout(() => {
        pressingRef.current = false
        setPressing(false)
      }, 120000)
    } else if (last) onClose()
    else setIndex(index + 1)
  }

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
              <button className="btn quiet small" type="button" disabled={index === 0 || pressing} onClick={() => setIndex(index - 1)}>Back</button>
              <button className="btn accent small" type="button" onClick={next} disabled={pressing}>
                {pressing ? 'Working…' : canPress ? 'Run and continue' : last ? 'Finish' : 'Next'}
              </button>
            </div>
          </footer>
        </aside>
      )}
    </div>
  )
}
