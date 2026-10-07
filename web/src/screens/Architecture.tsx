import { useState } from 'react'
import {
  ACTORS, AS_BUILT, AWS, AZURE, KIND_LABEL, MAPPING, OUTCOMES, REPO, SPECIALISTS, SUPERVISOR, WORKFLOWS, WRAP_UP,
  type Kind, type Platform,
} from '../architecture'

const SECTIONS = [
  { id: 'arch-repo', label: 'Built today' },
  { id: 'arch-agents', label: 'Agent flow' },
  { id: 'arch-aws', label: 'Amazon Bedrock' },
  { id: 'arch-azure', label: 'Azure AI Foundry' },
  { id: 'arch-map', label: 'Side by side' },
  { id: 'arch-workflows', label: 'Workflows' },
]

const KINDS: Kind[] = ['rules', 'history', 'claude', 'external']

function Stack({ p, tour }: { p: Platform; tour: string }) {
  return (
    <div className="stack" data-tour={tour}>
      {p.layers.map((l) => (
        <div className="stack-row" key={l.layer}>
          <div className="stack-layer">{l.layer}</div>
          <div className="stack-tiles">
            {l.tiles.map((t) => (
              <div className={`tile${t.ai ? ' ai' : ''}`} key={t.name}>
                <b>{t.name}</b>
                <p>{t.role}</p>
                {t.replaces && <span className="replaces">Replaces {t.replaces}</span>}
                {t.path && <code>{t.path}</code>}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function Notes({ items }: { items: string[] }) {
  return (
    <ul className="arch-notes">
      {items.map((n) => <li key={n}>{n}</li>)}
    </ul>
  )
}

export default function Architecture() {
  const [wf, setWf] = useState(WORKFLOWS[0].id)
  const flow = WORKFLOWS.find((w) => w.id === wf) ?? WORKFLOWS[0]
  const lanes = ACTORS.filter((a) => flow.steps.some((s) => s.actor === a))

  const jump = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })

  return (
    <div className="arch">
      <div className="page-head">
        <div>
          <h1>Architecture and workflows</h1>
          <p>
            How the demo is built, how the agent works an invoice, and how the same design would run on Amazon Bedrock or
            Azure AI Foundry inside Mastercard’s estate.
          </p>
        </div>
      </div>

      <nav className="arch-index" aria-label="On this page" data-tour="arch-index">
        {SECTIONS.map((s) => <button type="button" key={s.id} onClick={() => jump(s.id)}>{s.label}</button>)}
      </nav>

      <section id="arch-repo" className="arch-section">
        <header>
          <h2>{REPO.title}</h2>
          <p>{REPO.summary}</p>
        </header>
        <Stack p={REPO} tour="arch-repo" />
        <Notes items={REPO.notes} />
      </section>

      <section id="arch-agents" className="arch-section">
        <header>
          <h2>How the agent works an invoice</h2>
          <p>
            Today one orchestrator runs ten steps in the order a good non-PO process would. Each step is timed and logged,
            and the colour of its marker shows what does the work.
          </p>
        </header>
        <ul className="kind-legend" aria-label="Who does the work">
          {KINDS.map((k) => <li key={k}><span className={`dot ${k}`} aria-hidden="true" />{KIND_LABEL[k]}</li>)}
        </ul>
        <ol className="ladder" data-tour="arch-ladder">
          {AS_BUILT.map((s, i) => (
            <li key={s.key}>
              <span className="ladder-node" aria-hidden="true">
                <i className={s.kinds[0]} /><i className={s.kinds[1] ?? s.kinds[0]} />
              </span>
              <div className="ladder-body">
                <div className="ladder-q"><em>{i + 1}</em>{s.question}</div>
                <p>{s.does}</p>
                <div className="ladder-meta">
                  {s.kinds.map((k) => <span key={k} className={`kind ${k}`}>{KIND_LABEL[k]}</span>)}
                  {s.flags.map((f) => <span key={f.code} className={`flagdot ${f.severity}`}>{f.code}</span>)}
                  <code>{s.path}</code>
                </div>
              </div>
            </li>
          ))}
          <li className="wrap">
            <span className="ladder-node" aria-hidden="true"><i className="rules" /><i className="claude" /></span>
            <div className="ladder-body">
              <div className="ladder-q">{WRAP_UP.question}</div>
              <p>{WRAP_UP.does}</p>
              <div className="ladder-meta"><code>{WRAP_UP.path}</code></div>
            </div>
          </li>
        </ol>

        <div className="outcomes" data-tour="arch-outcomes">
          <h3>Status precedence</h3>
          <p className="muted small">Checked top to bottom; the first that applies wins.</p>
          <ol>
            {OUTCOMES.map((o) => (
              <li key={o.status}>
                <span className={`chip ${o.status}`}>{o.label}</span>
                <span>{o.when}</span>
              </li>
            ))}
          </ol>
        </div>

        <h3 className="arch-sub">Proposed: a supervisor and six specialist agents</h3>
        <p className="arch-lede">
          The same steps, regrouped so each agent owns one question and calls the existing checks as tools. The rules stay
          in code, not in prompts, and a person signs off wherever money or master data is at stake.
        </p>
        <div className="agents" data-tour="arch-target">
          <div className="agent supervisor">
            <b>{SUPERVISOR.name}</b>
            <p>{SUPERVISOR.job}</p>
            <div className="guard"><span>Guardrail</span>{SUPERVISOR.guardrail}</div>
          </div>
          <div className="agent-grid">
            {SPECIALISTS.map((a) => (
              <div className={`agent${a.scheduled ? ' scheduled' : ''}`} key={a.name}>
                <div className="agent-head">
                  <b>{a.name}</b>
                  {a.scheduled && <span className="tag">On a schedule</span>}
                </div>
                <p>{a.job}</p>
                <div className="tools">{a.tools.map((t) => <code key={t}>{t}</code>)}</div>
                {a.raises.length > 0 && (
                  <div className="flagdots">{a.raises.map((r) => <span key={r} className="flagdot">{r}</span>)}</div>
                )}
                <div className="guard"><span>Guardrail</span>{a.guardrail}</div>
                {a.human && <div className="human"><span className="tag person">Person</span>{a.human}</div>}
              </div>
            ))}
          </div>
        </div>
      </section>

      {[AWS, AZURE].map((p) => (
        <section id={`arch-${p.id}`} className="arch-section" key={p.id}>
          <header>
            <h2>{p.title}</h2>
            <p>{p.summary}</p>
          </header>
          <Stack p={p} tour={`arch-${p.id}`} />
          <Notes items={p.notes} />
        </section>
      ))}

      <section id="arch-map" className="arch-section">
        <header>
          <h2>Side by side</h2>
          <p>What each part of the demo becomes on each platform.</p>
        </header>
        <div className="table-wrap" data-tour="arch-map">
          <table className="grid map">
            <thead>
              <tr><th>Concern</th><th>This demo</th><th>Amazon Bedrock</th><th>Azure AI Foundry</th></tr>
            </thead>
            <tbody>
              {MAPPING.map((m) => (
                <tr key={m.concern}>
                  <td><b>{m.concern}</b></td><td className="muted">{m.repo}</td><td>{m.aws}</td><td>{m.azure}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section id="arch-workflows" className="arch-section">
        <header>
          <h2>Operational workflows</h2>
          <p>Who does what, in what order, for each thing the app does. Each step names the endpoint or file behind it.</p>
        </header>
        <div className="filters" role="tablist" aria-label="Workflow">
          {WORKFLOWS.map((w) => (
            <button type="button" role="tab" aria-selected={w.id === wf} key={w.id} className={w.id === wf ? 'on' : ''}
              onClick={() => setWf(w.id)}>{w.name}</button>
          ))}
        </div>
        <div className="card wf" data-tour="arch-workflows">
          <p className="wf-purpose">{flow.purpose}</p>
          <dl className="wf-ends">
            <div><dt>Starts when</dt><dd>{flow.trigger}</dd></div>
            <div><dt>Ends with</dt><dd>{flow.outcome}</dd></div>
          </dl>
          <div className="lanes" style={{ gridTemplateColumns: `140px repeat(${flow.steps.length}, minmax(0, 1fr))` }}>
            {lanes.map((a, r) => (
              <div key={a} className="lane-label" style={{ gridRow: r + 1, gridColumn: 1 }}>{a}</div>
            ))}
            {lanes.map((a, r) => (
              <div key={`bg-${a}`} className="lane-bg" style={{ gridRow: r + 1, gridColumn: `2 / span ${flow.steps.length}` }} />
            ))}
            {flow.steps.map((s, i) => (
              <div key={i} className={`wf-step${s.actor === 'Agent' ? ' agent-step' : ''}`}
                style={{ gridRow: lanes.indexOf(s.actor) + 1, gridColumn: i + 2 }}>
                <span className="n">{i + 1}</span>
                <span className="wf-actor">{s.actor}</span>
                <p>{s.text}</p>
                {s.api && <code>{s.api}</code>}
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  )
}
