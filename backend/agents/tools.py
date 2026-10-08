"""Every check, policy lookup and model call the agents may use, registered as a typed tool.

The engines in backend/engine keep their logic; this module gives each capability a name, a contract and a one-line
summary so runs are auditable and the same definitions can be exposed as Bedrock action groups or Foundry tools.
"""
from datetime import date, timedelta

from .. import llm
from ..store import ROOT
from .base import Tool, ToolRegistry

S = {"type": "string"}
N = {"type": "number"}
O = {"type": "object"}
A = {"type": "array"}
B = {"type": "boolean"}


def opt(schema):
    return {**schema, "optional": True}


def _agreement(doc, f):
    checks = [("Supplier", doc.get("vendor_name"), f.get("vendor_name")),
              ("Invoice number", doc.get("invoice_num"), f.get("invoice_num")),
              ("Invoice date", doc.get("invoice_date"), f.get("invoice_date")),
              ("Currency", doc.get("currency"), f.get("currency")),
              ("Total", doc.get("total"), f.get("total")),
              ("Line count", len(doc.get("lines", [])), len(f.get("lines") or []))]
    out = []
    for label, a, b in checks:
        same = (abs(float(a) - float(b)) < 0.011) if isinstance(a, (int, float)) and isinstance(b, (int, float)) \
            else str(a).strip().lower() == str(b).strip().lower()
        out.append({"field": label, "intake": a, "extracted": b, "match": same})
    return out


def build_registry(store, state, checks, policy, rec):
    s = store
    reg = ToolRegistry()

    # ---------- intake & extraction ----------
    def read_invoice(item):
        doc = dict(item["document"])
        if item.get("extraction_override"):
            return {"document": doc, "extraction": item["extraction_override"]}
        meta = {"source": "pre-extracted", "detail": "Captured by the intake channel (portal or e-invoice)."}
        if item.get("pdf"):
            pdf_path = ROOT / "data" / item["pdf"]
            if pdf_path.exists():
                try:
                    fields, meta = llm.extract_pdf(pdf_path.read_bytes())
                except Exception as e:  # the run continues on the intake record
                    fields, meta = None, {"source": "error", "error": type(e).__name__}
                if fields:
                    meta["fields"] = fields
                    meta["agreement"] = _agreement(doc, fields)
        return {"document": doc, "extraction": meta}

    def _read_summary(r):
        ex = r["extraction"]
        if ex.get("agreement"):
            ok = sum(1 for a in ex["agreement"] if a["match"])
            return f"{ex['source']}: {ok}/{len(ex['agreement'])} fields agree with the intake record"
        return f"{ex['source']}: fields from intake"

    reg.add(Tool("invoice.read", "intake", "Read the invoice PDF into a fixed schema with Claude and cross-check "
                 "every key field against the intake record.", read_invoice,
                 {"item": O}, {"document": O, "extraction": O}, _read_summary, kind="claude",
                 source=lambda r: r["extraction"].get("source", "computed")))

    def fx(amount, currency, month="2026-10"):
        if currency == "USD":
            return {"usd": round(amount, 2), "rate": 1.0}
        eur, inr = s.reference["fx_monthly"][month]
        rate = eur if currency == "EUR" else 1 / inr
        return {"usd": round(amount * rate, 2), "rate": round(rate, 6), "month": month}

    reg.add(Tool("fx.to_usd", "intake", "Translate an amount to USD at the month-end corporate rate.", fx,
                 {"amount": N, "currency": S, "month": opt(S)}, {"usd": N, "rate": N},
                 lambda r: f"${r['usd']:,.2f} at {r['rate']}"))

    # ---------- supplier & validity ----------
    reg.add(Tool("vendor.resolve", "supplier", "Match the supplier to the vendor master by name, corroborated by "
                 "tax ID.", lambda doc: checks.resolve_vendor(doc), {"doc": O},
                 {"found": B, "vendor_id": S, "match_score": N},
                 lambda r: f"{r['vendor_id']} {r['name']} ({r['match_score']:.0f}%)" if r["found"]
                 else f"Not in vendor master (closest: {r.get('closest')})", investigator=False))
    reg.add(Tool("sanctions.screen", "supplier", "Screen the supplier name against the OFAC SDN list.",
                 lambda name: checks.sanctions(name), {"name": S}, {"status": S, "matches": A},
                 lambda r: f"{r['status'].replace('_', ' ')} ({r.get('list_size', 0):,} entries, {r['source']})",
                 kind="external", source=lambda r: r.get("source", "computed")))

    def route_out(doc, sender):
        ic = doc.get("intercompany_entity")
        if not ic:
            names = {e["name"].lower(): code for code, e in s.entities.items()}
            ic = names.get((doc.get("vendor_name") or "").lower())
        if ic:
            r = s.policies["routing"]["intercompany"]
            return {"route": "intercompany", "entity": ic, "to": r["route"], "owner": r["owner"]}
        emp = doc.get("employee_id")
        if not emp:
            by_email = {p["email"].lower(): pid for pid, p in s.people.items()}
            emp = by_email.get((sender or "").lower())
        if emp and emp in s.people:
            r = s.policies["routing"]["employee_reimbursement"]
            return {"route": "employee_reimbursement", "employee": s.person_brief(emp), "to": r["route"],
                    "owner": r["owner"]}
        return {"route": None}

    reg.add(Tool("intake.route_check", "supplier", "Decide whether the document belongs in non-PO AP at all: "
                 "intercompany recharges and employee reimbursements leave this queue.", route_out,
                 {"doc": O, "sender": S}, {"route": S, "to": S},
                 lambda r: f"Route to {r['to']}" if r["route"] else "Belongs in non-PO AP"))
    reg.add(Tool("invoice.validity", "supplier", "Check mandatory fields, billed-to entity, currency and VAT "
                 "registration (EU VIES when the printed number differs from the master).",
                 lambda doc, vendor, live=False: checks.validity(doc, vendor, live=live),
                 {"doc": O, "vendor": O, "live": opt(B)}, {"passed": A, "issues": A, "tax": O},
                 lambda r: f"{len(r['passed'])} passed, {len(r['issues'])} issue(s), tax {r['tax'].get('status')}",
                 kind="external", source=lambda r: (r["tax"].get("vies") or {}).get("source", "computed")))

    def duplicates(vendor_id, doc, intake_id):
        order = {q["intake_id"]: q["received_at"] for q in s.intake}
        mine = order.get(intake_id, "9999")
        earlier = [q for q in s.intake if q["received_at"] < mine and q["intake_id"] != intake_id]
        return {"matches": checks.duplicates(vendor_id, doc, earlier),
                "searched": len(s.history_by_vendor.get(vendor_id, [])) + len(earlier)}

    reg.add(Tool("invoice.duplicates", "supplier", "Look for the same invoice in 18 months of history and the "
                 "open queue: fuzzy number match plus amount, date and service period.", duplicates,
                 {"vendor_id": S, "doc": O, "intake_id": S}, {"matches": A},
                 lambda r: f"{len(r['matches'])} likely duplicate(s) in {r['searched']:,} invoices",
                 kind="history", investigator=False))
    reg.add(Tool("po.open_match", "supplier", "Find an open purchase order this invoice should be matched to.",
                 lambda vendor_id, subtotal, descriptions: policy.open_po_match(vendor_id, subtotal, descriptions),
                 {"vendor_id": S, "subtotal": N, "descriptions": A}, {"po_number": S},
                 lambda r: f"Open PO {r['po_number']}" if r else "No open PO fits"))
    reg.add(Tool("po.policy", "supplier", "Apply the PO-required policy by category and amount.",
                 lambda category, amount_usd, has_po_ref: policy.po_policy(category, amount_usd, has_po_ref),
                 {"category": S, "amount_usd": N, "has_po_ref": B}, {"breach": B, "rule": S},
                 lambda r: ("Breach: " if r["breach"] else "") + r["rule"]))
    reg.add(Tool("vendor.stats", "supplier", "Supplier history: invoice count, median, account mix, PO share.",
                 lambda vendor_id: s.vendor_stats(vendor_id), {"vendor_id": S}, {"invoices": N, "median_usd": N},
                 lambda r: f"{r['invoices']} invoices, median ${r['median_usd'] or 0:,.0f}, "
                           f"{r['po_backed']} with a PO", kind="history"))

    # ---------- coding & treatment ----------
    reg.add(Tool("requester.identify", "approval", "Identify who asked for the spend: legal matter register, a "
                 "name on the invoice, or supplier history.",
                 lambda vendor_id, doc, cost_centre=None: policy.identify_requester(vendor_id, doc, cost_centre),
                 {"vendor_id": S, "doc": O, "cost_centre": opt(S)}, {"person": O, "source": S},
                 lambda r: f"{(r.get('person') or {}).get('name', 'unknown')} via {r['source']}", kind="history"))
    reg.add(Tool("coding.recommend_line", "coding", "Score GL accounts and cost centre for one line from similar "
                 "past lines, supplier history and amount fit; apply capitalisation and prepaid policy.",
                 lambda vendor_id, description, qty, unit_usd, amount_usd, service_period=None, requester_cc=None,
                 as_of=None: rec.recommend_line(vendor_id, description, qty, unit_usd, amount_usd, service_period,
                                                requester_cc=requester_cc, as_of=as_of),
                 {"vendor_id": S, "description": S, "qty": N, "unit_usd": N, "amount_usd": N,
                  "service_period": opt(O), "requester_cc": opt(S), "as_of": opt(S)},
                 {"account": S, "cost_centre": S, "confidence": N, "evidence": A},
                 lambda r: f"{r['account']} / {r['cost_centre']} at {r['confidence']:.0%} "
                           f"({r['components']['similar_same_vendor']} same-supplier matches)", kind="model"))
    reg.add(Tool("coding.learned_corrections", "coding", "Reviewer corrections learned for this supplier.",
                 lambda vendor_id: state.prefix(f"learned:{vendor_id}:"), {"vendor_id": S}, {"corrections": O},
                 lambda r: f"{len(r)} correction(s) on file", kind="state"))
    reg.add(Tool("coding.vendor_default_contrast", "coding", "Compare the recommendation with the vendor-master "
                 "default and count past reclasses caused by the default.",
                 lambda vendor_id, account, description: rec.vendor_default_contrast(vendor_id, account, description),
                 {"vendor_id": S, "account": S, "description": S}, {"vendor_default": S},
                 lambda r: f"Default {r['vendor_default']} would be wrong ({r['past_miscodes_reclassified']} past "
                           f"reclasses)" if r else "Agrees with vendor default", kind="history"))

    # ---------- receipt ----------
    reg.add(Tool("receipt.requirement", "approval", "Decide whether the requester must confirm receipt or a "
                 "standing rule covers it.",
                 lambda vendor_id, total_usd, as_of: policy.receipt_requirement(vendor_id, total_usd, as_of),
                 {"vendor_id": S, "total_usd": N, "as_of": S}, {"required": B, "rule": S},
                 lambda r: ("Confirmation needed" if r["required"] else "Standing rule") + f" ({r['rule']})"))

    def evidence(vendor_id, doc, as_of):
        window = s.policies["receipt"]["evidence_window_days"]
        start = (date.fromisoformat(as_of) - timedelta(days=window)).isoformat()
        refs = {str(doc.get(k)) for k in ("order_number", "order_form", "sow", "invoice_num") if doc.get(k)}
        text = " ".join(l["description"] for l in doc.get("lines", []))
        hits = []
        for e in s.receipt_evidence:
            if e["vendor_id"] != vendor_id or not (start <= e["date"] <= as_of):
                continue
            if e["reference"] in refs or e["reference"] in text or \
                    (e.get("amount") and abs(e["amount"] - doc.get("subtotal", 0)) <= 0.01 * e["amount"]):
                hits.append(e)
            elif not e.get("amount"):
                hits.append(e)
        return {"evidence": hits[:1], "searched": sum(1 for e in s.receipt_evidence if e["vendor_id"] == vendor_id)}

    reg.add(Tool("receipt.find_evidence", "approval", "Look for an existing record that the goods or service "
                 "arrived: asset-register scan, goods-in record, signed order form or SOW acceptance.", evidence,
                 {"vendor_id": S, "doc": O, "as_of": S}, {"evidence": A},
                 lambda r: (f"{r['evidence'][0]['kind'].replace('_', ' ')} {r['evidence'][0]['reference']}"
                            if r["evidence"] else f"No record among {r['searched']}"), kind="state", investigator=True))
    reg.add(Tool("receipt.task", "approval", "Current confirm-receipt task for the invoice, if one was sent.",
                 lambda intake_id: state.get(f"receipt:{intake_id}"), {"intake_id": S}, {"status": S},
                 lambda r: f"Task {r['status']} ({r['assignee_name']})" if r else "No task yet", kind="state"))

    # ---------- risk & approval ----------
    reg.add(Tool("risk.payment_risk", "risk", "Fraud and error signals before payment: amount vs supplier norm, "
                 "recent bank change, remit-to mismatch, look-alike domain, shortened terms.",
                 lambda vendor_id, doc, total_usd, sender, as_of, account=None:
                 checks.payment_risk(vendor_id, doc, total_usd, sender, as_of, account),
                 {"vendor_id": S, "doc": O, "total_usd": N, "sender": S, "as_of": S, "account": opt(S)},
                 {"flags": A, "notes": A},
                 lambda r: f"{len(r['flags'])} signal(s)" + (f"; {r['ratio_to_norm']}× norm" if r.get('ratio_to_norm')
                                                             else ""), kind="history"))
    reg.add(Tool("approval.route", "approval", "Apply the approval matrix: category rules, amount tier, approval "
                 "limits, separation of duties and delegates.",
                 lambda amount_usd, category, cost_centre, requester_id:
                 policy.route(amount_usd, category, cost_centre, requester_id),
                 {"amount_usd": N, "category": S, "cost_centre": S, "requester_id": opt(S)}, {"steps": A, "tier": S},
                 lambda r: " → ".join(st["person"]["name"] for st in r["steps"]) +
                           (" (SoD reroute)" if r["sod_reroute"] else "")))

    # ---------- explanation ----------
    reg.add(Tool("llm.explain", "supervisor", "Claude writes the reviewer-facing reason from the findings; a "
                 "deterministic template is the fallback.",
                 lambda findings, fallback: dict(zip(("text", "meta"), llm.explain(findings, fallback))),
                 {"findings": O, "fallback": S}, {"text": S, "meta": O},
                 lambda r: f"{len(r['text'].split())} words ({r['meta'].get('source')})", kind="claude",
                 source=lambda r: r["meta"].get("source", "computed")))
    return reg
