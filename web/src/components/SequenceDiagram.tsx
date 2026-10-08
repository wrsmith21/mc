import { useEffect, useMemo, useState } from 'react'
import type { Frame, Item, Msg, Workflow } from '../workflows'

const COL = 178
const fit = (t: string, px: number) => {
  const n = Math.max(10, Math.floor(px / 6.6))
  return t.length > n ? `${t.slice(0, n - 1)}…` : t
}
const HEAD = 56
const ROW = 46

type Row =
  | { kind: 'msg'; y: number; m: Msg; i: number }
  | { kind: 'timer'; y: number; label: string; on: string }
  | { kind: 'note'; y: number; label: string; over: string[] }
type Box = { y0: number; y1: number; label: string; kind: string; elseY?: number; elseLabel?: string; ids: Set<string>; depth: number }

function layout(items: Item[]) {
  const rows: Row[] = []
  const boxes: Box[] = []
  let y = HEAD + 26
  let i = 0
  const walk = (list: Item[], depth: number): Set<string> => {
    const ids = new Set<string>()
    for (const it of list) {
      if ('frame' in it) {
        const f = it as Frame
        const box: Box = { y0: y, y1: 0, label: f.label, kind: f.frame, ids: new Set(), depth }
        y += 38
        walk(f.items, depth + 1).forEach((x) => box.ids.add(x))
        if (f.elseItems) {
          box.elseY = y
          box.elseLabel = f.elseLabel
          y += 34
          walk(f.elseItems, depth + 1).forEach((x) => box.ids.add(x))
        }
        box.y1 = y + 4
        y += 14
        boxes.push(box)
        box.ids.forEach((x) => ids.add(x))
      } else if ('timer' in it) {
        rows.push({ kind: 'timer', y, label: it.timer, on: it.on })
        ids.add(it.on)
        y += 34
      } else if ('note' in it) {
        rows.push({ kind: 'note', y, label: it.note, over: it.over })
        it.over.forEach((x) => ids.add(x))
        y += 38
      } else {
        rows.push({ kind: 'msg', y, m: it, i: i++ })
        ids.add(it.from)
        ids.add(it.to)
        y += it.from === it.to ? ROW + 10 : ROW
      }
    }
    return ids
  }
  walk(items, 0)
  return { rows, boxes, height: y + 20, count: i }
}

export default function SequenceDiagram({ wf }: { wf: Workflow }) {
  const { rows, boxes, height, count } = useMemo(() => layout(wf.items), [wf])
  const [step, setStep] = useState(-1)
  const [playing, setPlaying] = useState(false)
  const idx = Object.fromEntries(wf.participants.map((p, k) => [p.id, k]))
  const x = (id: string) => 20 + COL * (idx[id] ?? 0) + COL / 2
  const width = 40 + COL * wf.participants.length

  useEffect(() => {
    setStep(-1)
    setPlaying(false)
  }, [wf.id])
  useEffect(() => {
    if (!playing) return
    const t = window.setInterval(() => setStep((s) => {
      if (s + 1 >= count) {
        setPlaying(false)
        return s
      }
      return s + 1
    }), 1500)
    return () => window.clearInterval(t)
  }, [playing, count])

  const current = rows.find((r) => r.kind === 'msg' && r.i === step) as Extract<Row, { kind: 'msg' }> | undefined

  return (
    <div className="seq">
      <div className="seq-controls">
        <button type="button" className="btn small" onClick={() => { if (step >= count - 1) setStep(-1); setPlaying(!playing) }}>
          {playing ? 'Pause' : step >= count - 1 ? 'Replay' : 'Play'}
        </button>
        <button type="button" className="btn small quiet" onClick={() => setStep((s) => Math.max(-1, s - 1))} disabled={step < 0}>Back</button>
        <button type="button" className="btn small quiet" onClick={() => setStep((s) => Math.min(count - 1, s + 1))} disabled={step >= count - 1}>Next</button>
        <span className="seq-step" aria-live="polite">
          {current ? <><b>{step + 1}/{count}</b> {current.m.label}{current.m.api && <code>{current.m.api}</code>}</> : <span className="muted">Step through the {count} messages, or press Play.</span>}
        </span>
      </div>
      <div className="seq-scroll">
        <svg width={width} height={height} role="img" aria-label={`Sequence diagram: ${wf.name}`} className="seq-svg">
          <defs>
            <marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" className="arrow-head" /></marker>
            <marker id="arr-on" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" className="arrow-head on" /></marker>
          </defs>
          {boxes.map((b, k) => {
            const xs = [...b.ids].map(x)
            const x0 = Math.min(...xs) - COL / 2 + 8 + b.depth * 6
            const x1 = Math.max(...xs) + COL / 2 - 8 - b.depth * 6
            return (
              <g key={k} className={`frame ${b.kind}`}>
                <rect x={x0} y={b.y0} width={x1 - x0} height={b.y1 - b.y0} rx={4} />
                <path d={`M${x0},${b.y0 + 18} h${b.kind.length * 9 + 14} l6,-6 v-12`} />
                <text x={x0 + 6} y={b.y0 + 13} className="frame-kind">{b.kind}</text>
                <text x={x0 + b.kind.length * 9 + 26} y={b.y0 + 13} className="frame-label">[{b.label}]</text>
                {b.elseY && (
                  <>
                    <line x1={x0} x2={x1} y1={b.elseY} y2={b.elseY} className="frame-else" />
                    <text x={x0 + 6} y={b.elseY + 14} className="frame-label">[{b.elseLabel}]</text>
                  </>
                )}
              </g>
            )
          })}
          {wf.participants.map((p) => (
            <g key={p.id} className={`part ${p.kind}`}>
              <line x1={x(p.id)} x2={x(p.id)} y1={HEAD} y2={height - 8} className="lifeline" />
              <rect x={x(p.id) - COL / 2 + 10} y={8} width={COL - 20} height={HEAD - 16} rx={6} />
              <text x={x(p.id)} y={8 + (HEAD - 16) / 2 + 5} textAnchor="middle" className="part-label">{p.label}</text>
            </g>
          ))}
          {rows.map((r, k) => {
            if (r.kind === 'timer') {
              return (
                <g key={k} className="timer">
                  <circle cx={x(r.on)} cy={r.y + 6} r={9} />
                  <path d={`M${x(r.on)},${r.y + 1} v5 h4`} />
                  <text x={x(r.on) + 16} y={r.y + 10}>{r.label}</text>
                </g>
              )
            }
            if (r.kind === 'note') {
              const xs = r.over.map(x)
              const x0 = Math.min(...xs) - 70
              return (
                <g key={k} className="note">
                  <rect x={x0} y={r.y - 4} width={Math.max(...xs) - x0 + 70} height={28} rx={3} />
                  <text x={x0 + 8} y={r.y + 14}>{r.label}</text>
                </g>
              )
            }
            const { m, i } = r
            const on = i === step
            const done = step >= 0 && i < step
            const cls = `msg${m.ret ? ' ret' : ''}${on ? ' on' : ''}${done ? ' done' : ''}`
            if (m.from === m.to) {
              const xx = x(m.from)
              return (
                <g key={k} className={cls} onClick={() => setStep(i)}>
                  <path d={`M${xx},${r.y + 4} h34 v18 h-30`} markerEnd={`url(#${on ? 'arr-on' : 'arr'})`} />
                  <text x={xx + 40} y={r.y + 16} className="msg-label">{fit(`${i + 1}. ${m.label}`, COL * 1.6)}<title>{m.label}</title></text>
                </g>
              )
            }
            const x1 = x(m.from), x2 = x(m.to)
            const mid = (x1 + x2) / 2
            return (
              <g key={k} className={cls} onClick={() => setStep(i)}>
                <rect x={Math.min(x1, x2)} y={r.y - 18} width={Math.abs(x2 - x1)} height={26} className="hit" />
                <line x1={x1} x2={x2 + (x2 > x1 ? -3 : 3)} y1={r.y} y2={r.y} markerEnd={`url(#${on ? 'arr-on' : 'arr'})`} />
                <text x={mid} y={r.y - 7} textAnchor="middle" className="msg-label">{fit(`${i + 1}. ${m.label}`, Math.abs(x2 - x1))}<title>{m.label}{m.api ? ` · ${m.api}` : ''}</title></text>
              </g>
            )
          })}
        </svg>
      </div>
    </div>
  )
}
