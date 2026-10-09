"""SOX evidence pack: one printable page per invoice with everything an auditor asks for, generated from the record.

What the agent read, every control it ran (with the tool calls and their results), what it recommended and why,
who confirmed receipt, who decided, who approved in what order, and what was sent to the ledger.
"""
from html import escape as e

from . import brand, clock

STYLE = """
body{font:13px/1.45 'Helvetica Neue',Arial,sans-serif;color:#141413;margin:32px auto;max-width:1000px;padding:0 24px}
h1{font-size:22px;margin:0}h2{font-size:15px;margin:26px 0 8px;padding-bottom:4px;border-bottom:2px solid #141413}
.meta{color:#5f5a55;margin-top:4px}table{width:100%;border-collapse:collapse;margin-top:6px}
td,th{border-bottom:1px solid #dcd6d1;padding:5px 6px;text-align:left;vertical-align:top}th{font-size:11px;color:#5f5a55}
.ok{color:#1a7f4b}.warn{color:#8a4b00}.fail{color:#b5001a}.small{font-size:11px;color:#5f5a55}
.grid{display:grid;grid-template-columns:260px 1fr;gap:20px}.doc img{width:100%;border:1px solid #dcd6d1}
.banner{border:1px dashed #5f5a55;padding:6px 10px;font-size:11px;color:#5f5a55;margin:12px 0}
@media print{body{margin:12px}.noprint{display:none}}
"""


def _money(v, cur="USD"):
    return f"{cur} {v:,.2f}" if isinstance(v, (int, float)) else "—"


def render(svc, r, events):
    doc, run = r["document"], r.get("run") or {}
    c = r.get("coding") or {}
    rows = []
    a = rows.append
    a(f"<!doctype html><html><head><meta charset='utf-8'><title>Evidence {e(r['intake_id'])}</title>"
      f"<style>{STYLE}</style></head><body>")
    a(f"<h1>SOX evidence pack · {e(doc.get('vendor_name') or '')} · invoice {e(str(doc.get('invoice_num')))}</h1>")
    a(f"<div class='meta'>{e(r['intake_id'])} · received {e(r['received_at'])} via {e(r['channel'])} · "
      f"status <b>{e(r['status_label'])}</b> · generated {e(clock.now_iso())}</div>")
    a(f"<div class='banner'>{brand.PRODUCT} · demonstration on synthetic data · built by Ciklum. Generated from the run "
      "record and the event log; nothing on this page is typed by hand.</div>")
    a("<p class='noprint'><button onclick='window.print()'>Print or save as PDF</button></p>")

    a("<h2>1 · The document and what was read</h2><div class='grid'>")
    a(f"<div class='doc'>{'<img src=/api/pdf/' + e(r['intake_id']) + '/preview alt=Invoice>' if r.get('pdf') else '<p class=small>Received as structured data (portal / e-invoice).</p>'}</div><div>")
    a("<table><tr><th>Field</th><th>Value</th></tr>")
    for k in ("vendor_name", "invoice_num", "invoice_date", "due_date", "currency", "subtotal", "tax", "total"):
        a(f"<tr><td>{e(k.replace('_', ' '))}</td><td>{e(str(doc.get(k)))}</td></tr>")
    a("</table>")
    ex = r.get("extraction") or {}
    if ex.get("agreement"):
        a("<table><tr><th>Cross-check</th><th>Intake</th><th>Read from PDF</th><th></th></tr>")
        for g in ex["agreement"]:
            a(f"<tr><td>{e(g['field'])}</td><td>{e(str(g['intake']))}</td><td>{e(str(g['extracted']))}</td>"
              f"<td class='{'ok' if g['match'] else 'fail'}'>{'agrees' if g['match'] else 'differs'}</td></tr>")
        a("</table>")
    a(f"<p class='small'>Extraction source: {e(str(ex.get('source')))} {e(str(ex.get('model') or ''))}</p></div></div>")

    a(f"<h2>2 · Controls the agent ran</h2><p class='small'>Run {e(run.get('run_id', '—'))} · trigger "
      f"{e(run.get('trigger', '—'))} · started {e(run.get('started_at', '—'))} · {run.get('ms', 0)} ms · "
      f"{run.get('tool_calls', 0)} tool calls · policy version {run.get('policy_version', 1)} · model "
      f"{e(str(run.get('llm_model', '')))}</p>")
    a("<table><tr><th>Step</th><th>Result</th><th>Tool calls</th></tr>")
    for st in r.get("trace", []):
        calls = "<br>".join(f"{e(t['id'])} {e(t['tool'])} → {e(str(t.get('summary', '')))} "
                            f"<span class=small>({t.get('ms', 0)} ms, {e(str(t.get('source')))})</span>"
                            for t in st.get("tool_calls", []))
        a(f"<tr><td>{e(st['label'])}</td><td class='{e(st['status'])}'>{e(st.get('detail', ''))}</td>"
          f"<td class='small'>{calls}</td></tr>")
    a("</table>")

    a("<h2>3 · Recommendation and why</h2>")
    if c:
        a(f"<p><b>{e(c['account'])} {e(c.get('account_name') or '')} · {e(c['cost_centre'])}</b> at "
          f"{c['confidence']:.0%} calibrated confidence ({e(c['band'])}).</p>")
    a(f"<p>{e(r.get('explanation') or '')}</p>")
    ev = ((c.get("lines") or [{}])[0].get("rec") or {}).get("evidence") or []
    if ev:
        a("<table><tr><th>Similar past invoice</th><th>Date</th><th>Description</th><th>Coded</th></tr>")
        for x in ev:
            a(f"<tr><td>{e(x['vendor'])} {e(str(x.get('invoice_num', '')))}</td><td>{e(x['date'])}</td>"
              f"<td>{e(x['description'])}</td><td>{e(x['account'])}</td></tr>")
        a("</table>")
    if r.get("flags"):
        a("<table><tr><th>Finding</th><th>Severity</th><th>Detail</th></tr>")
        for f in r["flags"]:
            a(f"<tr><td>{e(f['title'])}</td><td>{e(f['severity'])}</td><td>{e(f['detail'])}</td></tr>")
        a("</table>")
    inv = r.get("investigation")
    if inv:
        a(f"<h2>4 · Exception investigation</h2><p>{e(inv['summary'])}</p><p><b>Recommended next action:</b> "
          f"{e(inv['next_action'])} ({e(inv['source'])})</p><ul>")
        for x in inv.get("evidence", []):
            a(f"<li>{e(x['text'])} <span class='small'>[{e(x['tool_call_id'])}]</span></li>")
        a("</ul>")

    a("<h2>5 · People: receipt, decision, approvals</h2><table><tr><th>When</th><th>Who</th><th>What</th><th>Detail</th></tr>")
    human = [x for x in events if x["actor"] not in ("AGENT", "system")]
    for x in human:
        p = x.get("payload") or {}
        detail = p.get("reason") or p.get("note") or p.get("by") or ", ".join(p.get("chain", []) or []) or ""
        a(f"<tr><td>{e(x['ts'])}</td><td>{e(x.get('actor_name', x['actor']))}<br><span class=small>"
          f"{e(x.get('actor_title', ''))}</span></td><td>{e(x['kind'])}</td><td>{e(str(detail))}</td></tr>")
    a("</table>")

    a("<h2>6 · Complete event log</h2><table><tr><th>When</th><th>Actor</th><th>Event</th></tr>")
    for x in events:
        a(f"<tr><td>{e(x['ts'])}</td><td>{e(x.get('actor_name', x['actor']))}</td><td>{e(x['kind'])}</td></tr>")
    a("</table>")
    exported = [x for x in events if x["kind"] == "EXPORTED"]
    a("<h2>7 · Posting</h2>")
    a(f"<p>{'Added to ' + e(exported[-1]['payload']['file']) + ', group ' + e(exported[-1]['payload']['group_id']) if exported else 'Not yet posted: approval incomplete.'}</p>")
    a("</body></html>")
    return "".join(rows)
