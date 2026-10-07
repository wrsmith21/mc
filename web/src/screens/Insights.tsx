import { useEffect, useState } from 'react'
import { api, type Json } from '../api'
import Plot from '../components/Plot'
import { compact, money, num, pct } from '../format'

// Validated with the dataviz palette checker (CVD ΔE 23.5, contrast ≥ 3:1 on white). Orange always means "needs attention".
const ALLOWED = '#1F64B0'
const ATTENTION = '#E85400'

export default function Insights() {
  const [p, setP] = useState<Json | null>(null)
  const [s, setS] = useState<Json | null>(null)

  useEffect(() => {
    api.procurement().then(setP)
    api.summary().then(setS)
  }, [])

  if (!p || !s) return <p className="muted">Loading 18 months of AP history…</p>
  const months = p.by_month.map((m: Json) => m.month)
  const nonPoTotal = p.by_month.reduce((a: number, m: Json) => a + m.non_po, 0)
  const breachTotal = p.by_category.reduce((a: number, c: Json) => a + c.breach, 0)
  const cats = [...p.by_category].slice(0, 12).reverse()

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Value, and shrinking the problem</h1>
          <p>
            Faster non-PO processing is half the value. The other half is moving repeat non-PO spend onto purchase orders
            and standing rules, so fewer invoices arrive without one.
          </p>
        </div>
        <a className="btn" href="/api/exports/procurement">Download today's PO-policy report</a>
      </div>

      <section className="kpis" data-tour="value-kpis">
        <div className="kpi"><b>{pct(p.non_po_share)}</b><span>Of AP spend arrived without a PO (18 months)</span></div>
        <div className="kpi"><b>{compact(nonPoTotal)}</b><span>Non-PO spend, Apr 2025 – Sep 2026</span></div>
        <div className="kpi"><b>{compact(breachTotal)}</b><span>Of it in categories that require a PO</span></div>
        <div className="kpi"><b>{pct(s.touchless_rate)}</b><span>Approved today without re-coding</span></div>
        <div className="kpi"><b>{s.avg_cycle_days ?? '—'} d</b><span>Receipt to approval (manual baseline {s.baseline_cycle_days} d, illustrative)</span></div>
        <div className="kpi"><b>{s.miscodings_prevented}</b><span>Vendor-default miscodings prevented today</span></div>
      </section>

      <div className="insight-grid">
        <div className="card" data-tour="spend-trend">
          <div className="card-head">
            <h3>AP spend by month: with and without a PO</h3>
            <span className="muted small">{num(s.history.invoices)} invoices</span>
          </div>
          <Plot
            data={[
              { type: 'bar', name: 'With a PO', x: months, y: p.by_month.map((m: Json) => m.po), marker: { color: ALLOWED, line: { color: '#fff', width: 2 } },
                hovertemplate: '%{x}<br>With a PO: $%{y:,.0f}<extra></extra>' },
              { type: 'bar', name: 'Without a PO', x: months, y: p.by_month.map((m: Json) => m.non_po), marker: { color: ATTENTION, line: { color: '#fff', width: 2 } },
                hovertemplate: '%{x}<br>Without a PO: $%{y:,.0f}<extra></extra>' },
            ]}
            layout={{ barmode: 'stack', bargap: 0.25, yaxis: { gridcolor: '#ebe6e2', tickprefix: '$', tickformat: '~s' } }}
          />
        </div>
        <div className="card" data-tour="category-breach">
          <div className="card-head"><h3>Non-PO spend by category</h3></div>
          <Plot
            height={380}
            data={[
              { type: 'bar', orientation: 'h', name: 'PO not required', y: cats.map((c: Json) => c.category), x: cats.map((c: Json) => c.non_po - c.breach),
                marker: { color: ALLOWED, line: { color: '#fff', width: 2 } }, hovertemplate: '%{y}<br>PO not required: $%{x:,.0f}<extra></extra>' },
              { type: 'bar', orientation: 'h', name: 'Should have been a PO', y: cats.map((c: Json) => c.category), x: cats.map((c: Json) => c.breach),
                marker: { color: ATTENTION, line: { color: '#fff', width: 2 } }, hovertemplate: '%{y}<br>Should have been a PO: $%{x:,.0f}<extra></extra>' },
            ]}
            layout={{ barmode: 'stack', margin: { l: 170, r: 16, t: 10, b: 44 }, xaxis: { gridcolor: '#ebe6e2', tickprefix: '$', tickformat: '~s' } }}
          />
        </div>
        <div className="card wide" data-tour="blanket-po">
          <div className="card-head">
            <h3>Recurring non-PO suppliers: candidates for a blanket PO or standing rule</h3>
            <span className="muted small">Billed in 9+ of the last 12 months, $150k+</span>
          </div>
          <table className="evidence">
            <thead><tr><th>Supplier</th><th>Category</th><th className="num">Invoices (12 months)</th><th className="num">Months billed</th><th className="num">Value (12 months)</th><th>Recommendation</th></tr></thead>
            <tbody>
              {p.blanket_po_candidates.map((c: Json) => (
                <tr key={c.vendor_id}>
                  <td><b>{c.vendor}</b></td><td>{c.category}</td><td className="num">{c.invoices_12m}</td>
                  <td className="num">{c.months_billed}</td><td className="num">{money(c.value_12m, 'USD', 0)}</td><td>{c.recommendation}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}
