import { useState } from 'react'
import type { Diagram } from '../architecture'

const CW = 214
const RH = 118
const PAD = 16
const NW = 182
const NH = 74

export default function ContainerDiagram({ d }: { d: Diagram }) {
  const [focus, setFocus] = useState<number | null>(null)
  const pos = Object.fromEntries(d.nodes.map((n) => [n.id, { cx: PAD + n.col * CW + CW / 2, cy: PAD + 26 + n.row * RH + RH / 2 }]))
  const width = PAD * 2 + d.cols * CW
  const height = PAD * 2 + 26 + d.rows * RH
  const active = focus == null ? null : d.flows.find((f) => f.n === focus)

  return (
    <div className="container-diagram">
      <div className="cd-scroll">
        <svg width={width} height={height} role="img" aria-label={d.title} className="cd-svg">
          <defs>
            <marker id="cd-arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" className="arrow-head" /></marker>
            <marker id="cd-arr-on" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" className="arrow-head on" /></marker>
          </defs>
          {d.zones.map((z) => (
            <g key={z.label} className={`zone ${z.kind}`}>
              <rect x={PAD + z.col * CW + 4} y={PAD + z.row * RH + 4} width={z.w * CW - 8} height={z.h * RH + 18} rx={10} />
              <text x={PAD + z.col * CW + 16} y={PAD + z.row * RH + 22}>{z.label}</text>
            </g>
          ))}
          {d.flows.map((f) => {
            const a = pos[f.from], b = pos[f.to]
            if (!a || !b) return null
            const dx = b.cx - a.cx, dy = b.cy - a.cy
            const len = Math.hypot(dx, dy) || 1
            const ex = Math.abs(dx) / len > (NW / 2) / Math.hypot(NW / 2, NH / 2) ? NW / 2 / Math.abs(dx / len) : NH / 2 / Math.abs(dy / len)
            const x1 = a.cx + (dx / len) * ex, y1 = a.cy + (dy / len) * ex
            const x2 = b.cx - (dx / len) * (ex + 4), y2 = b.cy - (dy / len) * (ex + 4)
            const on = focus === f.n
            return (
              <g key={f.n} className={`flow ${f.data.toLowerCase()}${on ? ' on' : ''}${focus != null && !on ? ' dim' : ''}`}
                onMouseEnter={() => setFocus(f.n)} onMouseLeave={() => setFocus(null)}>
                <line x1={x1} y1={y1} x2={x2} y2={y2} markerEnd={`url(#${on ? 'cd-arr-on' : 'cd-arr'})`} />
                <circle cx={(x1 + x2) / 2} cy={(y1 + y2) / 2} r={10} />
                <text x={(x1 + x2) / 2} y={(y1 + y2) / 2 + 4} textAnchor="middle">{f.n}</text>
              </g>
            )
          })}
          {d.nodes.map((n) => {
            const { cx, cy } = pos[n.id]
            const lit = active && (active.from === n.id || active.to === n.id)
            return (
              <g key={n.id} className={`cd-node ${n.kind}${n.ai ? ' ai' : ''}${lit ? ' lit' : ''}`}>
                <rect x={cx - NW / 2} y={cy - NH / 2} width={NW} height={NH} rx={8} />
                <foreignObject x={cx - NW / 2 + 8} y={cy - NH / 2 + 6} width={NW - 16} height={NH - 12}>
                  <div className="cd-text"><b>{n.label}</b>{n.sub && <span>{n.sub}</span>}</div>
                </foreignObject>
              </g>
            )
          })}
        </svg>
      </div>
      <ol className="cd-flows">
        {d.flows.map((f) => (
          <li key={f.n} className={focus === f.n ? 'on' : ''} onMouseEnter={() => setFocus(f.n)} onMouseLeave={() => setFocus(null)}>
            <span className="n">{f.n}</span>
            <span>{d.nodes.find((x) => x.id === f.from)?.label} → {d.nodes.find((x) => x.id === f.to)?.label}: {f.label}</span>
            <span className={`data ${f.data.toLowerCase()}`}>{f.data}</span>
          </li>
        ))}
      </ol>
    </div>
  )
}
