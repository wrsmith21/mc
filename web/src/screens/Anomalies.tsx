import { useEffect, useState } from 'react'
import { api, type Json } from '../api'
import { money, num, pct } from '../format'

const TYPE_LABEL: Record<string, string> = {
  MISCODED: 'Posted to the wrong account', DUPLICATE_ENTRY: 'Accrued twice', SELF_APPROVED: 'Prepared and approved by the same person',
  AP_MISCODE: 'Miscoded invoice still in the ledger', MISAPPLIED: 'Cash applied to the wrong customer',
  DOUBLE_APPLICATION: 'Applied to an invoice that was already paid',
}

export default function Anomalies() {
  const [data, setData] = useState<Json | null>(null)
  const [source, setSource] = useState<'journals' | 'cash' | 'ap_ledger'>('journals')

  useEffect(() => {
    api.anomalies().then(setData)
  }, [])

  if (!data) return <p className="muted">Scanning journals, the AP subledger and today's cash application…</p>
  const j = data.journals
  const ap = data.ap_ledger
  const cash = data.cash

  return (
    <>
      <div className="page-head">
        <div>
          <h1>One engine, three processes</h1>
          <p>
            The same coding history and checks, pointed at the September close journals, the AP subledger and one day of
            cash application. It reads every line and surfaces the few that need a person.
          </p>
        </div>
      </div>

      <div className="sources" data-tour="anomaly-sources">
        <button type="button" className={`source ${source === 'journals' ? 'on' : ''}`} onClick={() => setSource('journals')}>
          <h3>Record to report · SEP-26 journals</h3>
          <div className="big">{j.flags.length}<span>to review</span></div>
          <div className="scan">{num(j.lines_total)} journal lines, {num(j.entries_total)} entries · {j.ms} ms</div>
        </button>
        <button type="button" className={`source ${source === 'cash' ? 'on' : ''}`} onClick={() => setSource('cash')} data-tour="cash-source">
          <h3>Cash application · 14 Oct</h3>
          <div className="big">{cash.flags.length}<span>misapplied · {cash.suggestions.length} matches proposed</span></div>
          <div className="scan">{num(cash.lines_scanned)} settlement receipts · {pct(cash.auto_rate, 1)} auto-applied · {cash.ms} ms</div>
        </button>
        <button type="button" className={`source ${source === 'ap_ledger' ? 'on' : ''}`} onClick={() => setSource('ap_ledger')}>
          <h3>Procure to pay · AP subledger</h3>
          <div className="big">{ap.flags.length}<span>{money(ap.value, 'USD', 0)}</span></div>
          <div className="scan">{num(ap.lines_scanned)} posted lines, Apr–Sep 2026 · {ap.ms} ms</div>
        </button>
      </div>

      {source === 'journals' && (
        <div className="card" style={{ padding: 0 }} data-tour="journal-findings">
          <div className="card-head" style={{ padding: '16px 18px 0' }}>
            <h3>Journal lines that need a person</h3>
            <a className="btn small" href="/api/exports/reclass">Download proposed reclasses (GL_INTERFACE)</a>
          </div>
          {j.flags.map((f: Json, i: number) => (
            <div key={`${f.je_id}-${i}`} className={`finding ${i === 0 ? 'top' : ''}`} data-tour={i === 0 ? 'laptop-journal' : undefined}>
              <div>
                <div className="what">{TYPE_LABEL[f.type]}</div>
                <div className="detail">“{f.description}”</div>
                {f.suggested_account && (
                  <div className="arrow-codes"><s>{f.account} {f.account_name}</s> → <b>{f.suggested_account} {f.suggested_name}</b></div>
                )}
                <p className="detail">{f.detail}</p>
                <div className="meta">{f.je_id} · {f.batch} · prepared by {f.created_by}{f.approved_by ? `, approved by ${f.approved_by}` : ''}</div>
              </div>
              <div className="amt">{money(f.amount, 'USD', 0)}</div>
            </div>
          ))}
        </div>
      )}

      {source === 'cash' && (
        <>
          <div className="card" style={{ padding: 0, marginBottom: 16 }} data-tour="cash-findings">
            <div className="card-head" style={{ padding: '16px 18px 0' }}><h3>Applied cash that is wrong</h3></div>
            {cash.flags.map((f: Json, i: number) => (
              <div key={f.receipt_id} className={`finding ${i === 0 ? 'top' : ''}`}>
                <div>
                  <div className="what">{TYPE_LABEL[f.type]}</div>
                  <p className="detail">{f.detail}</p>
                  {f.suggested_customer && (
                    <div className="arrow-codes"><s>Customer {f.applied_customer}</s> → <b>Customer {f.suggested_customer}</b></div>
                  )}
                  <div className="meta">{f.receipt_id} · payer “{f.payer}” · remittance “{f.remittance}” · applied by {f.applied_by}</div>
                </div>
                <div className="amt">{money(f.amount, f.currency)}</div>
              </div>
            ))}
          </div>
          <div className="card">
            <div className="card-head">
              <h3>Exceptions the agent can resolve</h3>
              <span className="muted small">{cash.suggestions.length} of {cash.exceptions} unapplied receipts have a proposed match</span>
            </div>
            <table className="evidence">
              <thead><tr><th>Receipt</th><th>Payer</th><th>Remittance</th><th className="num">Amount</th><th>Proposed match</th><th>Basis</th></tr></thead>
              <tbody>
                {[...cash.suggestions].sort((a: Json, b: Json) => Number(b.highlight) - Number(a.highlight)).slice(0, 14).map((s: Json) => (
                  <tr key={s.receipt_id} className={s.highlight ? 'same' : ''}>
                    <td className="small">{s.receipt_id}</td><td>{s.payer}</td><td className="small">{s.remittance || '—'}</td>
                    <td className="num">{money(s.amount, s.currency)}</td>
                    <td><b>{s.ar_invoice}</b><div className="small muted">{s.customer_id} {s.customer_name}</div></td>
                    <td className="small">{s.basis}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {source === 'ap_ledger' && (
        <div className="card" style={{ padding: 0 }}>
          <div className="card-head" style={{ padding: '16px 18px 0' }}>
            <h3>Past invoices coded differently from every similar line</h3>
            <span className="muted small">Largest first</span>
          </div>
          {ap.flags.slice(0, 15).map((f: Json) => (
            <div key={`${f.invoice_id}-${f.description}`} className="finding">
              <div>
                <div className="what">{f.vendor} · {f.invoice_num}</div>
                <div className="detail">“{f.description}”</div>
                <div className="arrow-codes"><s>{f.account} {f.account_name}</s> → <b>{f.suggested_account} {f.suggested_name}</b></div>
                <p className="detail small muted">{f.detail}</p>
              </div>
              <div className="amt">{money(f.amount, 'USD', 0)}</div>
            </div>
          ))}
        </div>
      )}
    </>
  )
}
