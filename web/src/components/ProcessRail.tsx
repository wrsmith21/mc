import type { Json } from '../api'

// The agent's checks mapped onto the eight steps of a good non-PO process (brief, section 2).
export const STEP_ORDER = ['intake', 'read', 'supplier', 'validity', 'po', 'coding', 'treatment', 'receipt', 'risk', 'approval']
const PROCESS_LABEL: Record<number, string> = {
  0: 'Intake', 1: 'Step 1', 2: 'Step 2', 3: 'Step 3', 4: 'Step 4', 5: 'Step 5', 6: 'Step 6', 7: 'Step 7', 8: 'Step 8',
}
const LABELS: Record<string, string> = {
  intake: 'Received', read: 'Read the invoice', supplier: 'Should this be here?', validity: 'Is the invoice valid?',
  po: 'Should it have been a PO?', coding: 'What is it, where does it go?', treatment: 'Capitalise or prepay?',
  receipt: 'Who asked, did we get it?', risk: 'Is it safe to pay?', approval: 'Who can approve it?',
}

type Props = { steps: Record<string, Json>; running?: string | null; compact?: boolean }

export default function ProcessRail({ steps, running, compact }: Props) {
  return (
    <ol className="rail" data-tour="process-rail">
      {STEP_ORDER.map((key) => {
        const s = steps[key]
        const state = s ? s.status : running === key ? 'running' : 'pending'
        return (
          <li key={key} className={state}>
            <span className="node" aria-hidden="true"><i /><i /></span>
            <div>
              <div className="step-label">
                {s && <em>{PROCESS_LABEL[s.process_step]}</em>}
                {LABELS[key]}
              </div>
              {s ? <div className="detail">{s.detail}</div> : <div className="detail muted">{state === 'running' ? 'Working…' : ''}</div>}
              {s && !compact && s.facts?.length > 0 && (
                <ul className="facts">
                  {s.facts.map((f: string, i: number) => <li key={i}>{f}</li>)}
                </ul>
              )}
            </div>
            <span className="ms">{s ? `${s.ms < 1 ? '<1' : Math.round(s.ms)} ms` : ''}</span>
          </li>
        )
      })}
    </ol>
  )
}
