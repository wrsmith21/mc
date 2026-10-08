import { useEffect, useState } from 'react'
import { api, type Json } from '../api'
import { useApp, useCan } from '../context'
import { dateTime } from '../format'

export default function Policies() {
  const { toast, bump } = useApp()
  const can = useCan()
  const [p, setP] = useState<Json | null>(null)
  const [edits, setEdits] = useState<Record<string, string>>({})
  const [reason, setReason] = useState('')
  const editable = can('policy_edit')

  const load = () => api.policies().then((x) => { setP(x); setEdits({}) })
  useEffect(() => { load() }, [])

  const save = async () => {
    const changes = Object.fromEntries(Object.entries(edits).filter(([, v]) => v !== '').map(([k, v]) => [k, Number(v)]))
    try {
      const v = await api.updatePolicies(changes, reason)
      toast(`Policy version ${v.version} saved; earlier runs are marked for re-run`)
      setReason('')
      load()
      bump()
    } catch (e) {
      toast((e as Error).message, 'error')
    }
  }

  if (!p) return <p className="muted">Loading policies…</p>
  const champ = p.proposed_bands?.champion
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Policies</h1>
          <p>The rules the agent applies: approval matrix, thresholds and confidence bands. They are data, not prompts, and the agent cannot change them. Every change is a new version with who, when and why; each run records the version it used.</p>
        </div>
        <span className="muted small">In force: version {p.version}</span>
      </div>
      <div className="insight-grid">
        <div className="card">
          <h3>Settings</h3>
          {!editable && <p className="muted small">Read-only for your role. Finance systems admins change policy.</p>}
          <table className="evidence policy-table">
            <tbody>
              {p.fields.map((f: Json) => (
                <tr key={f.path}>
                  <td>{f.label}<div className="small muted">{f.path}</div></td>
                  <td className="num">
                    {editable ? (
                      <input className="text-input num-input" type="number" step="any" min={f.min} max={f.max}
                        placeholder={String(f.value)} value={edits[f.path] ?? ''} onChange={(e) => setEdits({ ...edits, [f.path]: e.target.value })} />
                    ) : <b>{String(f.value)}</b>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {champ && (
            <p className="small" style={{ marginTop: 10 }}>Back-test proposal: fast-track at calibrated confidence ≥ {champ.fast_track}, where measured precision stays at 98%.
              {editable && <button type="button" className="btn small quiet" style={{ marginLeft: 8 }}
                onClick={() => setEdits({ ...edits, 'risk.confidence_bands.fast_track': String(champ.fast_track) })}>Use it</button>}</p>
          )}
          {editable && (
            <div className="policy-save">
              <label className="field">Why is this changing? (kept with the version)
                <textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
              </label>
              <button type="button" className="btn primary" disabled={!Object.values(edits).some((v) => v !== '') || reason.trim().length < 5} onClick={save}>Save as version {p.version + 1}</button>
            </div>
          )}
        </div>
        <div className="card">
          <h3>Version history</h3>
          <ol className="timeline">
            {[...p.versions].reverse().map((v: Json) => (
              <li key={v.version} className={v.by !== 'SEED' ? 'human' : ''}>
                <time>{dateTime(v.at)}</time>
                <div>
                  <div className="kind">Version {v.version}</div>
                  <div className="who">{v.by_name ?? 'Seed policy set'}</div>
                  <div className="payload">{v.reason}</div>
                  {v.changes.map((c: Json) => <div key={c.path} className="small">{c.label}: <s>{String(c.before)}</s> → <b>{String(c.after)}</b></div>)}
                </div>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </>
  )
}
