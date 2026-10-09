import { useEffect, useState } from 'react'
import { api, type Json } from '../api'
import { brand } from '../brand'

const ORDER = ['ap_specialist', 'approver', 'requester', 'gl_accountant', 'controller', 'cash_preparer', 'cash_lead',
  'vendor_master', 'procurement', 'fixed_assets', 'legal_ops', 'admin']
const GROUP: Record<string, string> = {
  ap_specialist: 'Accounts payable', gl_accountant: 'Record to report', controller: 'Record to report',
  cash_preparer: 'Cash application', cash_lead: 'Cash application', vendor_master: 'Controls and master data',
  procurement: 'Procurement', fixed_assets: 'Record to report', legal_ops: 'Approvers', approver: 'Approvers',
  requester: 'Requesters', admin: 'Administration',
}

function primary(p: Json) {
  return [...p.roles].sort((a: string, b: string) => ORDER.indexOf(a) - ORDER.indexOf(b))[0]
}

export default function SignIn({ onDone, current }: { onDone: (s: Json) => void; current?: string }) {
  const [people, setPeople] = useState<Json[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.people().then(setPeople).catch((e) => setError(e.message))
    fetch('/api/warm').catch(() => {})
  }, [])

  const groups: Record<string, Json[]> = {}
  for (const p of people) (groups[GROUP[primary(p)]] ??= []).push(p)

  const pick = async (id: string) => {
    setBusy(id)
    setError('')
    try {
      onDone(await api.signIn(id))
    } catch (e) {
      setError((e as Error).message)
      setBusy(null)
    }
  }

  return (
    <div className="center-page">
      <div className="signin">
        <header>
          {brand.logo && <img src={brand.logo} alt={brand.client} />}
          <div>
            <h1>Sign in to {brand.product}</h1>
            <p className="muted">Each person sees their own work and can only do what their role allows. The server checks every action and logs refusals.</p>
          </div>
        </header>
        {error && <p className="error-line" role="alert">{error}</p>}
        <div className="signin-groups">
          {Object.entries(groups).map(([g, ps]) => (
            <section key={g}>
              <h2>{g}</h2>
              <div className="signin-people">
                {ps.map((p) => (
                  <button key={p.id} type="button" className={`person-card${p.id === current ? ' on' : ''}`}
                    onClick={() => pick(p.id)} disabled={!!busy}>
                    <b>{p.name}</b>
                    <span>{p.title}</span>
                    <small>{p.role_labels.filter((r: string) => r !== 'Requester').join(' · ') || 'Requester'}</small>
                    {busy === p.id && <em>Signing in…</em>}
                  </button>
                ))}
              </div>
            </section>
          ))}
        </div>
        <p className="small muted">{brand.disclaimer}. In production these roles come from Entra ID or Cognito groups.</p>
      </div>
    </div>
  )
}
