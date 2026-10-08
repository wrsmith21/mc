import { useEffect, useState } from 'react'
import { api, type Json } from '../api'
import { AGENTS, AS_BUILT, BEDROCK, FOUNDRY, MAPPING, type Diagram } from '../architecture'
import ContainerDiagram from '../components/ContainerDiagram'
import SequenceDiagram from '../components/SequenceDiagram'
import { WORKFLOWS } from '../workflows'

const SECTIONS = [
  { id: 'arch-repo', label: 'Built today' },
  { id: 'arch-agents', label: 'Agents' },
  { id: 'arch-aws', label: 'Amazon Bedrock' },
  { id: 'arch-azure', label: 'Azure AI Foundry' },
  { id: 'arch-map', label: 'Side by side' },
  { id: 'arch-workflows', label: 'Operational workflows' },
]

const TOPOLOGY: Diagram = {
  id: 'topology', title: 'Agent topology', summary: '', cols: 5, rows: 3,
  zones: [
    { label: 'Agent runtime (backend/agents)', col: 1, row: 0, w: 3, h: 3, kind: 'tenant' },
    { label: 'People', col: 0, row: 0, w: 1, h: 3, kind: 'corp' },
    { label: 'Model', col: 4, row: 0, w: 1, h: 1, kind: 'model' },
    { label: 'Data and registries', col: 4, row: 1, w: 1, h: 2, kind: 'public' },
  ],
  nodes: [
    { id: 'ap', label: 'AP specialist', sub: 'runs, accepts, overrides', col: 0, row: 0, kind: 'person' },
    { id: 'req', label: 'Requester · approvers', sub: 'confirm, approve in order', col: 0, row: 1, kind: 'person' },
    { id: 'ctl', label: 'Vendor master · controller', sub: 'call-backs, case approval', col: 0, row: 2, kind: 'person' },
    { id: 'sup', label: 'Supervisor', sub: 'fixed order · status precedence', col: 2, row: 1, kind: 'agent', ai: true },
    { id: 'intake', label: 'Intake & extraction', sub: 'step 0', col: 1, row: 0, kind: 'agent' },
    { id: 'supplier', label: 'Supplier & validity', sub: 'steps 1–2', col: 2, row: 0, kind: 'agent' },
    { id: 'coding', label: 'Coding & treatment', sub: 'step 4', col: 3, row: 0, kind: 'agent' },
    { id: 'price', label: 'Price', sub: 'step 5', col: 1, row: 2, kind: 'agent' },
    { id: 'approval', label: 'Approval & receipt', sub: 'steps 3 and 6', col: 2, row: 2, kind: 'agent' },
    { id: 'risk', label: 'Payment risk', sub: 'step 7', col: 3, row: 2, kind: 'agent' },
    { id: 'inv', label: 'Investigator', sub: 'exceptions · read-only', col: 3, row: 1, kind: 'agent', ai: true },
    { id: 'claude', label: 'Claude', sub: 'read, explain, investigate', col: 4, row: 0, kind: 'model', ai: true },
    { id: 'reg', label: 'Tool registry', sub: 'history, vendors, policies, VIES', col: 4, row: 1, kind: 'data' },
    { id: 'state', label: 'Run records · audit', sub: 'every call stored', col: 4, row: 2, kind: 'data' },
  ],
  flows: [
    { from: 'ap', to: 'sup', n: 1, label: 'Run (or mailbox batch)', data: 'Internal' },
    { from: 'sup', to: 'intake', n: 2, label: 'Read and cross-check', data: 'Confidential' },
    { from: 'sup', to: 'supplier', n: 3, label: 'Should it be here, is it valid', data: 'Confidential' },
    { from: 'sup', to: 'coding', n: 4, label: 'Code, split, treat', data: 'Confidential' },
    { from: 'sup', to: 'price', n: 5, label: 'Check the price', data: 'Confidential' },
    { from: 'sup', to: 'approval', n: 6, label: 'Receipt and route', data: 'Confidential' },
    { from: 'sup', to: 'risk', n: 7, label: 'Safe to pay', data: 'Confidential' },
    { from: 'sup', to: 'inv', n: 8, label: 'Exceptions only', data: 'Confidential' },
    { from: 'inv', to: 'claude', n: 9, label: 'Tool-use loop', data: 'Confidential' },
    { from: 'inv', to: 'reg', n: 10, label: 'Read-only tool calls', data: 'Confidential' },
    { from: 'sup', to: 'state', n: 11, label: 'Run record', data: 'Confidential' },
    { from: 'approval', to: 'req', n: 12, label: 'Receipt task, approval chain', data: 'Internal' },
    { from: 'sup', to: 'ctl', n: 13, label: 'Holds for call-back; cases for approval', data: 'Internal' },
  ],
  notes: [],
}

function Section({ id, title, lede, children }: { id: string; title: string; lede?: string; children: React.ReactNode }) {
  return (
    <section id={id} className="arch-section">
      <header><h2>{title}</h2>{lede && <p>{lede}</p>}</header>
      {children}
    </section>
  )
}

export default function Architecture() {
  const [tools, setTools] = useState<Json[]>([])
  const [ops, setOps] = useState<Json | null>(null)
  const [wfId, setWfId] = useState(WORKFLOWS[0].id)
  const [agentId, setAgentId] = useState('supervisor')
  useEffect(() => {
    api.agents().then((a) => setTools(a.tools)).catch(() => {})
    api.operations().then(setOps).catch(() => {})
  }, [])
  const wf = WORKFLOWS.find((w) => w.id === wfId) ?? WORKFLOWS[0]
  const agent = AGENTS.find((a) => a.id === agentId) ?? AGENTS[0]
  const agentTools = tools.filter((t) => (agentId === 'investigator' ? t.investigator : t.agent === agentId))
  const latency = ops?.agents?.find((a: Json) => a.agent === agentId)
  const jump = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })

  return (
    <div className="arch">
      <div className="page-head">
        <div>
          <h1>Architecture and workflows</h1>
          <p>How the agent is built and runs today, what each agent decides and with which tools, how the same design deploys on Amazon Bedrock or Azure AI Foundry, and how each operational workflow moves between people, agents and systems. Tool lists come live from the running service.</p>
        </div>
      </div>
      <nav className="arch-index" aria-label="On this page" data-tour="arch-index">
        {SECTIONS.map((s) => <button type="button" key={s.id} onClick={() => jump(s.id)}>{s.label}</button>)}
      </nav>

      <Section id="arch-repo" title={AS_BUILT.title} lede={AS_BUILT.summary}>
        <div data-tour="arch-repo"><ContainerDiagram d={AS_BUILT} /></div>
        <ul className="arch-notes">{AS_BUILT.notes.map((n) => <li key={n}>{n}</li>)}</ul>
      </Section>

      <Section id="arch-agents" title="The agents, and what each one decides"
        lede="A supervisor runs six specialists in a fixed order on every invoice, so every control always runs; Claude is used where judgement on language helps (reading, explaining, investigating exceptions), never to pick the account or approve. Each specialist acts only through registered tools.">
        <div data-tour="arch-topology"><ContainerDiagram d={TOPOLOGY} /></div>
        <div className="agent-catalogue" data-tour="arch-catalogue">
          <div className="agent-tabs" role="tablist" aria-label="Agents">
            {AGENTS.map((a) => (
              <button key={a.id} type="button" role="tab" aria-selected={a.id === agentId} className={a.id === agentId ? 'on' : ''} onClick={() => setAgentId(a.id)}>
                <b>{a.name}</b><span>{a.step}</span>
              </button>
            ))}
          </div>
          <div className="card agent-detail">
            <div className="card-head">
              <div>
                <h3>{agent.name}</h3>
                <p className="muted">{agent.question}</p>
              </div>
              <span className={`kind-pill ${agent.kind}`}>{agent.kind === 'deterministic' ? 'Deterministic' : agent.kind === 'model' ? 'Claude' : 'Rules + model'}</span>
            </div>
            <div className="agent-grid2">
              <dl>
                <dt>Triggered when</dt><dd>{agent.trigger}</dd>
                <dt>Inputs</dt><dd>{agent.inputs}</dd>
                <dt>Outputs</dt><dd>{agent.outputs}</dd>
                <dt>If something fails</dt><dd>{agent.failure}</dd>
                {agent.human && <><dt>Where a person signs off</dt><dd>{agent.human}</dd></>}
                {latency && <><dt>Measured latency</dt><dd>typical {latency.p50 < 1 ? '<1' : Math.round(latency.p50)} ms · slowest 5% {Math.round(latency.p95)} ms · {latency.steps} steps on current runs</dd></>}
              </dl>
              <div>
                <h4>Decides</h4>
                <ul>{agent.decides.map((d) => <li key={d}>{d}</li>)}</ul>
                <h4>Guardrails</h4>
                <ul>{agent.guardrails.map((d) => <li key={d}>{d}</li>)}</ul>
              </div>
            </div>
            {agentTools.length > 0 && (
              <>
                <h4>Tools ({agentTools.length}, from the running service)</h4>
                <table className="evidence tool-table">
                  <thead><tr><th>Tool</th><th>What it does</th><th>Inputs</th><th>Kind</th></tr></thead>
                  <tbody>{agentTools.map((t) => (
                    <tr key={t.name}><td><code>{t.name}</code></td><td>{t.description}</td>
                      <td className="small">{Object.keys(t.input_schema.properties).join(', ') || '—'}</td><td className="small">{t.kind}</td></tr>
                  ))}</tbody>
                </table>
              </>
            )}
          </div>
        </div>
      </Section>

      {[BEDROCK, FOUNDRY].map((d) => (
        <Section key={d.id} id={`arch-${d.id}`} title={d.title} lede={d.summary}>
          <div data-tour={`arch-${d.id}`}><ContainerDiagram d={d} /></div>
          <ul className="arch-notes">{d.notes.map((n) => <li key={n}>{n}</li>)}</ul>
        </Section>
      ))}

      <Section id="arch-map" title="Side by side" lede="What each part of the demo becomes on each platform.">
        <div className="table-wrap" data-tour="arch-map">
          <table className="grid map">
            <thead><tr><th>Concern</th><th>This demo</th><th>Amazon Bedrock</th><th>Azure AI Foundry</th></tr></thead>
            <tbody>{MAPPING.map((m) => (
              <tr key={m.concern}><td><b>{m.concern}</b></td><td className="muted">{m.repo}</td><td>{m.aws}</td><td>{m.azure}</td></tr>
            ))}</tbody>
          </table>
        </div>
      </Section>

      <Section id="arch-workflows" title="Operational workflows"
        lede="Each workflow as a sequence: who calls whom, in order, with the endpoint or function behind each message, the alternative paths, and the timers the service enforces. Step through it, or press Play.">
        <div className="filters" role="tablist" aria-label="Workflow">
          {WORKFLOWS.map((w) => (
            <button type="button" role="tab" aria-selected={w.id === wfId} key={w.id} className={w.id === wfId ? 'on' : ''} onClick={() => setWfId(w.id)}>{w.name}</button>
          ))}
        </div>
        <div className="card wf-card" data-tour="arch-workflows">
          <p className="wf-purpose">{wf.purpose}</p>
          <SequenceDiagram wf={wf} />
          <div className="ops-panel">
            <div><h4>Trigger</h4><p>{wf.ops.trigger}</p></div>
            <div><h4>SLA</h4><p>{wf.ops.sla}</p></div>
            <div><h4>Who</h4><p>{wf.ops.raci.map(([w, r]) => `${w} (${r})`).join(' · ')}</p><p className="small muted">R responsible · A accountable · C consulted · I informed</p></div>
            <div><h4>Controls</h4><ul>{wf.ops.controls.map((c) => <li key={c}>{c}</li>)}</ul></div>
            <div><h4>Measures</h4><ul>{wf.ops.kpis.map((c) => <li key={c}>{c}</li>)}</ul></div>
            <div><h4>When it goes wrong</h4><ul>{wf.ops.exceptions.map((c) => <li key={c}>{c}</li>)}</ul></div>
            <div><h4>Systems</h4><p>{wf.ops.systems.join(' · ')}</p></div>
          </div>
        </div>
      </Section>
    </div>
  )
}
