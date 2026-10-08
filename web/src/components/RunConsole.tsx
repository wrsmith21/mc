import { useState } from 'react'
import type { Json } from '../api'

const AGENT: Record<string, string> = {
  intake: 'Intake & extraction', supplier: 'Supplier & validity', coding: 'Coding & treatment', price: 'Price',
  approval: 'Approval & receipt', risk: 'Payment risk', investigator: 'Investigator (Claude)', supervisor: 'Supervisor',
}
const SOURCE: Record<string, string> = {
  live: 'live', cache: 'replayed', computed: 'computed', 'pre-extracted': 'intake', template: 'template',
  error: 'failed', 'vendor master': 'master', unavailable: 'unavailable',
}

function ToolCall({ c, highlight }: { c: Json; highlight: boolean }) {
  const [open, setOpen] = useState(false)
  return (
    <li className={`tool-call${highlight ? ' cited' : ''}${c.error ? ' failed' : ''}`} id={`call-${c.id}`}>
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="tc-id">{c.id}</span>
        <code className="tc-name">{c.tool}</code>
        <span className="tc-sum">{c.error ?? c.summary}</span>
        <span className={`tc-src ${c.source}`}>{SOURCE[c.source] ?? c.source}</span>
        <span className="tc-ms">{c.ms < 1 ? '<1' : Math.round(c.ms)} ms</span>
      </button>
      {open && <pre className="tc-args">{JSON.stringify(c.args, null, 2)}</pre>}
    </li>
  )
}

export default function RunConsole({ steps, running, run, cited }: { steps: Json[]; running: string | null; run: Json | null; cited?: Set<string> }) {
  const calls = steps.reduce((n, s) => n + (s.tool_calls?.length ?? 0), 0)
  return (
    <div className="console" data-tour="console">
      <div className="console-head">
        <div>
          <b>{run ? run.run_id : 'Run in progress'}</b>
          <span className="muted small">
            {run ? ` · ${run.trigger} · ${run.started_at?.replace('T', ' ')} · ${Math.round(run.ms ?? 0)} ms · ` : ' · '}
            {calls} tool calls{run?.policy_version ? ` · policy v${run.policy_version}` : ''}
            {run?.tokens?.input ? ` · ${run.tokens.input + run.tokens.output} model tokens` : ''}
          </span>
        </div>
        <span className="muted small">Each call is the only way an agent touches data or policy. Click to see its inputs.</span>
      </div>
      <ol className="console-steps">
        {steps.map((s) => (
          <li key={s.key} className={`console-step ${s.status}`}>
            <div className="cs-head">
              <span className={`agent-badge ${s.agent}`}>{AGENT[s.agent] ?? s.agent}</span>
              <b>{s.label}</b>
              <span className="cs-detail">{s.detail}</span>
              <span className="tc-ms">{s.ms != null ? `${s.ms < 1 ? '<1' : Math.round(s.ms)} ms` : ''}</span>
            </div>
            {s.tool_calls?.length > 0 && (
              <ul className="tool-calls">
                {s.tool_calls.map((c: Json) => <ToolCall key={c.id} c={c} highlight={!!cited?.has(c.id)} />)}
              </ul>
            )}
          </li>
        ))}
        {running && <li className="console-step running"><div className="cs-head"><span className="agent-badge">…</span><b>{running}</b><span className="cs-detail">Working</span></div></li>}
      </ol>
    </div>
  )
}
