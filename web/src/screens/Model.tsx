import { useEffect, useState } from 'react'
import { api, type Json } from '../api'
import Plot from '../components/Plot'
import { num, pct } from '../format'

const BLUE = '#1F64B0'
const NAME: Record<string, string> = { champion: 'Champion · explainable similarity engine', challenger: 'Challenger · logistic regression', blend: 'Blend of both' }

export default function Model() {
  const [m, setM] = useState<Json | null>(null)
  useEffect(() => { api.model().then(setM) }, [])
  if (!m) return <p className="muted">Loading the model record…</p>
  if (!m.metrics) return <p className="muted">No trained model yet. Run <code>uv run python -m scripts.train</code>.</p>
  const x = m.metrics
  const prodName = x.production_model
  const prod = x.models[prodName]
  const card = m.card
  const cats = [...prod.by_category].filter((c: Json) => c.lines >= 25).sort((a: Json, b: Json) => a.accuracy - b.accuracy).slice(0, 14).reverse()

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Model and data</h1>
          <p>What the coding recommendation learns from, how it was tested, and how far to trust its confidence. Every figure below is measured, on synthetic data, by <code>scripts/train.py</code>; none is a product accuracy claim. On a client's history the same harness runs before anything goes live.</p>
        </div>
        <span className="muted small">Model v{x.version} · trained {x.trained_at}</span>
      </div>

      <section className="kpis" data-tour="model-kpis">
        <div className="kpi"><b>{num(x.lines.train)}</b><span>Coded lines it learned from (Apr 2025 – Apr 2026)</span></div>
        <div className="kpi"><b>{num(x.lines.test)}</b><span>Held-out lines it was tested on (Jul – Sep 2026)</span></div>
        <div className="kpi"><b>{pct(prod.first_time_right, 1)}</b><span>First-time-right on the hold-out</span></div>
        <div className="kpi"><b>{pct(prod.top3, 1)}</b><span>Right answer in its top three</span></div>
        <div className="kpi"><b>{prod.ece_raw.toFixed(3)} → {prod.ece_calibrated.toFixed(3)}</b><span>Calibration error, raw → calibrated</span></div>
        <div className="kpi"><b>{prod.reclasses_avoided.model_predicts_corrected_account}/{prod.reclasses_avoided.historic_miscodes_in_test}</b><span>Historic miscodes it would have coded right</span></div>
      </section>

      <div className="insight-grid">
        <div className="card" data-tour="model-compare">
          <h3>Champion against challenger</h3>
          <p className="muted small">Same time split, same hold-out. Production is chosen by measured first-time-right, then calibration.</p>
          <table className="evidence">
            <thead><tr><th>Model</th><th className="num">First-time-right</th><th className="num">Top 3</th><th className="num">Macro F1</th><th className="num">Cost centre</th><th className="num">Calibration error</th></tr></thead>
            <tbody>
              {Object.entries(x.models).map(([k, v]: [string, Json]) => (
                <tr key={k} className={k === prodName ? 'same' : ''}>
                  <td><b>{NAME[k]}</b>{k === prodName && <span className="tag person">In production</span>}</td>
                  <td className="num">{pct(v.first_time_right, 1)}</td><td className="num">{pct(v.top3, 1)}</td>
                  <td className="num">{v.macro_f1.toFixed(3)}</td><td className="num">{v.cost_centre_accuracy != null ? pct(v.cost_centre_accuracy, 1) : '—'}</td>
                  <td className="num">{v.ece_calibrated.toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="small" style={{ marginTop: 10 }}>The explainable engine stays in production: it matches the trained model on accuracy, and every recommendation points to the past invoices behind it. The challenger runs alongside as a recorded second opinion.</p>
        </div>

        <div className="card" data-tour="calibration">
          <h3>When it says 95%, is it right 95% of the time?</h3>
          <Plot height={300} data={[
            { x: [0, 1], y: [0, 1], mode: 'lines', line: { color: '#9c8f84', width: 1, dash: 'dot' }, hoverinfo: 'skip', showlegend: false },
            { x: prod.reliability.map((b: Json) => b.confidence), y: prod.reliability.map((b: Json) => b.accuracy), mode: 'lines+markers',
              line: { color: BLUE, width: 2 }, marker: { size: 9, color: BLUE, line: { color: '#fff', width: 2 } }, showlegend: false,
              customdata: prod.reliability.map((b: Json) => b.n), hovertemplate: 'Says %{x:.0%}<br>Right %{y:.1%}<br>%{customdata} lines<extra></extra>' },
          ]} layout={{ xaxis: { title: { text: 'Calibrated confidence' }, tickformat: '.0%', range: [0, 1.02] },
            yaxis: { title: { text: 'Measured accuracy' }, tickformat: '.0%', range: [0, 1.02] },
            annotations: [{ x: 0.3, y: 0.36, text: 'perfect calibration', showarrow: false, font: { size: 12, color: '#5f5a55' } }] }} />
          <p className="muted small">Isotonic calibration fitted on May – Jun 2026, checked on Jul – Sep. Each dot is a confidence band of hold-out lines.</p>
        </div>

        <div className="card">
          <h3>Confidence bands, measured</h3>
          <table className="evidence">
            <thead><tr><th>Band</th><th className="num">Share of lines</th><th className="num">Accuracy</th></tr></thead>
            <tbody>
              {(['fast_track', 'review', 'manual'] as const).map((b) => (
                <tr key={b}><td>{b === 'fast_track' ? 'Fast-track' : b === 'review' ? 'Review' : 'Needs a person'}</td>
                  <td className="num">{pct(prod.bands[b].share, 1)}</td><td className="num">{prod.bands[b].accuracy != null ? pct(prod.bands[b].accuracy, 1) : '—'}</td></tr>
              ))}
            </tbody>
          </table>
          <p className="small" style={{ marginTop: 10 }}>Proposed from the back-test: fast-track at {pct(prod.proposed_bands.fast_track, 1)} calibrated confidence, the lowest level at which measured precision stays at 98%. An admin adopts it in Policies; the change is versioned.</p>
        </div>

        <div className="card">
          <h3>Most common confusions</h3>
          <table className="evidence">
            <thead><tr><th>Booked as</th><th>Model said</th><th className="num">Lines</th></tr></thead>
            <tbody>{prod.confusions.slice(0, 7).map((c: Json) => (
              <tr key={c.actual + c.predicted}><td>{c.actual}</td><td>{c.predicted}</td><td className="num">{c.lines}</td></tr>
            ))}</tbody>
          </table>
          <p className="muted small" style={{ marginTop: 8 }}>Mostly neighbouring accounts suppliers are legitimately coded to both ways (repairs vs facilities services). These land in the review band, where a person decides.</p>
        </div>

        <div className="card wide" data-tour="by-category">
          <h3>Where it is weakest: first-time-right by spend category</h3>
          <Plot height={360} data={[{ type: 'bar', orientation: 'h', y: cats.map((c: Json) => c.category), x: cats.map((c: Json) => c.accuracy),
            marker: { color: BLUE, line: { color: '#fff', width: 2 } }, customdata: cats.map((c: Json) => c.lines),
            hovertemplate: '%{y}<br>%{x:.1%} on %{customdata} lines<extra></extra>' }]}
            layout={{ margin: { l: 150, r: 16, t: 10, b: 40 }, xaxis: { tickformat: '.0%', range: [Math.min(...cats.map((c: Json) => c.accuracy)) - 0.05, 1] } }} />
        </div>

        <div className="card">
          <h3>The learning loop, measured</h3>
          <table className="evidence">
            <thead><tr><th>Month</th><th className="num">Frozen at training</th><th className="num">With confirmed coding added</th></tr></thead>
            <tbody>{x.learning_loop.map((l: Json) => (
              <tr key={l.month}><td>{l.month}</td><td className="num">{pct(l.frozen, 1)}</td><td className="num"><b>{pct(l.with_corrections, 1)}</b></td></tr>
            ))}</tbody>
          </table>
          <p className="muted small" style={{ marginTop: 8 }}>Each month the history grows with what reviewers confirmed or corrected. Small, steady gains are what a well-run loop looks like.</p>
        </div>

        <div className="card">
          <h3>The anomaly sweep, against known answers</h3>
          <table className="evidence"><tbody>
            <tr><td>AP subledger precision</td><td className="num"><b>{pct(x.anomaly.ap_ledger.precision)}</b></td></tr>
            <tr><td>AP subledger recall (open miscodes since April)</td><td className="num">{pct(x.anomaly.ap_ledger.recall)}</td></tr>
            <tr><td>Planted journal anomalies found</td><td className="num">{x.anomaly.journals.planted_found} of {x.anomaly.journals.planted}</td></tr>
            <tr><td>Journal lines scanned · flagged</td><td className="num">{num(x.anomaly.journals.lines_scanned)} · {x.anomaly.journals.flags}</td></tr>
            <tr><td>Cash receipts scanned</td><td className="num">{num(x.anomaly.cash.receipts_scanned)}</td></tr>
          </tbody></table>
          <p className="muted small" style={{ marginTop: 8 }}>Suppliers legitimately coded to two accounts are not flagged; that is what keeps precision high.</p>
        </div>

        <div className="card wide" data-tour="datasets">
          <h3>What it learns from</h3>
          <table className="evidence">
            <thead><tr><th>Dataset</th><th className="num">Rows</th><th>From</th><th>To</th><th>Used by</th></tr></thead>
            <tbody>{m.manifest.map((d: Json) => (
              <tr key={d.dataset}><td><b>{d.dataset}</b></td><td className="num">{num(d.rows)}</td><td>{d.from ?? '—'}</td><td>{d.to ?? '—'}</td><td className="small">{d.used_by}</td></tr>
            ))}</tbody>
          </table>
          <p className="muted small" style={{ marginTop: 8 }}>Challenger features: {num(x.features.challenger)} ({num(x.features.word_ngrams)} word and {num(x.features.char_ngrams)} character patterns, {x.features.suppliers} suppliers, category, entity, amount). The label is the final coding after any reclass.</p>
        </div>

        {card && (
          <div className="card wide model-card" data-tour="model-card">
            <h3>Model card</h3>
            <dl>
              <dt>Intended use</dt><dd>{card.intended_use}</dd>
              <dt>Out of scope</dt><dd>{card.out_of_scope.join(' · ')}</dd>
              <dt>Training data</dt><dd>{card.training_data}</dd>
              <dt>Evaluation</dt><dd>{card.evaluation}</dd>
              <dt>Limitations</dt><dd>{card.limitations.join(' · ')}</dd>
              <dt>Monitoring</dt><dd>Override rate alert at {pct(card.monitoring.override_rate_alert)}; confidence drift (PSI) alert at {card.monitoring.psi_alert}. {card.monitoring.retrain_trigger}.</dd>
              <dt>Owner</dt><dd>{card.owner}</dd>
              <dt>Approval</dt><dd>{card.approval}</dd>
              <dt>Data use</dt><dd>{card.data_use}</dd>
            </dl>
          </div>
        )}
      </div>
    </>
  )
}
