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
    def resolve(doc):
        onboarded = state.get(f"onboarded:{(doc.get('vendor_name') or '').lower()}")
        if onboarded:
            return {"found": True, **onboarded}
        return checks.resolve_vendor(doc)

    reg.add(Tool("vendor.resolve", "supplier", "Match the supplier to the vendor master by name, corroborated by "
                 "tax ID.", resolve, {"doc": O},
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
    def verified_callback(vendor_id, risk):
        cb = state.get(f"callback:{vendor_id}")
        if not cb or cb.get("outcome") != "verified":
            return risk
        for f in risk["flags"]:
            if f["code"] == "RECENT_BANK_CHANGE":
                f["severity"] = "low"
                f["detail"] += f" Call-back completed by {cb['by_name']} on {cb['at'][:10]}: details verified."
        risk["flags"] = [f for f in risk["flags"] if f["code"] != "LOOKALIKE_DOMAIN" or not cb.get("domain_ok")]
        return risk

    reg.add(Tool("risk.payment_risk", "risk", "Fraud and error signals before payment: amount vs supplier norm, "
                 "recent bank change, remit-to mismatch, look-alike domain, shortened terms.",
                 lambda vendor_id, doc, total_usd, sender, as_of, account=None:
                 verified_callback(vendor_id, checks.payment_risk(vendor_id, doc, total_usd, sender, as_of, account)),
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

    # ---------- price (step 5) ----------
    def rate_card(vendor_id, doc):
        letter = s.letters.get(doc.get("engagement_letter")) or s.letters_by_vendor.get(vendor_id)
        if not letter:
            return {"letter": None, "lines": [], "variances": []}
        card = {r["role"]: r["hourly_rate_usd"] for r in letter["rates"]}
        lines, variances = [], []
        for l in doc["lines"]:
            role = l["description"].split(" – ")[0].strip()
            if role not in card:
                continue
            rate = card[role]
            row = {"role": role, "hours": l["qty"], "billed_rate": l["unit_price"], "card_rate": rate,
                   "amount": l["amount"], "excess": round(max(0, l["unit_price"] - rate) * l["qty"], 2)}
            lines.append(row)
            if l["unit_price"] > rate * (1 + s.policies["price"]["rate_tolerance"]):
                variances.append(row)
        return {"letter": letter["engagement_letter"], "kind": letter["kind"], "lines": lines,
                "variances": variances, "hours": round(sum(r["hours"] for r in lines), 2)}

    reg.add(Tool("price.rate_card", "price", "Compare billed hourly rates by role with the engagement letter or "
                 "master services agreement.", rate_card, {"vendor_id": S, "doc": O}, {"variances": A},
                 lambda r: ("No rate card on file" if not r["letter"] else
                            f"{len(r['lines'])} timekeeper line(s) vs {r['letter']}: {len(r['variances'])} over card"),
                 investigator=True))

    def matter_budget(matter, amount_usd):
        m = s.matter_budgets.get(matter)
        if not m:
            return None
        after = m["billed_to_date_usd"] + amount_usd
        return {**m, "after_invoice_usd": round(after, 2), "share_after": round(after / m["budget_usd"], 3)}

    reg.add(Tool("price.matter_budget", "price", "Check the legal matter's budget consumed including this invoice.",
                 matter_budget, {"matter": S, "amount_usd": N}, {"share_after": N},
                 lambda r: f"{r['matter']}: {r['share_after']:.0%} of ${r['budget_usd']:,.0f} budget after this "
                           f"invoice" if r else "No matter budget", kind="state", investigator=True))

    def sow(vendor_id, doc):
        text = " ".join(l["description"] for l in doc["lines"]).lower()
        for w_ in s.sows.values():
            if w_["vendor_id"] == vendor_id and (w_["description"].lower() in text or
                                                 abs(w_["fixed_fee_usd"] - doc["subtotal"]) < 0.01):
                return {**w_, "matches_fee": abs(w_["fixed_fee_usd"] - doc["subtotal"]) < 0.01}
        return None

    reg.add(Tool("price.sow", "price", "Match a fixed-fee invoice to its signed statement of work.", sow,
                 {"vendor_id": S, "doc": O}, {"sow": S, "matches_fee": B},
                 lambda r: f"{r['sow']} fixed fee ${r['fixed_fee_usd']:,.0f}: " +
                           ("matches" if r["matches_fee"] else "DIFFERS") if r else "No SOW", kind="state"))

    # ---------- treatment: splits, cut-off, tax ----------
    def split(lines, entity):
        import re as _re
        out = []
        for i, l in enumerate(lines):
            cc = _re.search(r"\((CC\d{4})\)", l["description"])
            ent = _re.search(r"\b(US01|EU01|IN01)\b", l["description"])
            out.append({"line": i, "cost_centre": cc.group(1) if cc and cc.group(1) in s.cost_centres else None,
                        "entity": ent.group(1) if ent else entity, "amount": l["amount"]})
        named = [o for o in out if o["cost_centre"] or o["entity"] != entity]
        return {"allocations": out if named else [], "entities": sorted({o["entity"] for o in out}),
                "cost_centres": sorted({o["cost_centre"] for o in out if o["cost_centre"]})}

    reg.add(Tool("coding.split", "coding", "Read cost-centre and entity allocations named on the invoice lines.",
                 split, {"lines": A, "entity": S}, {"allocations": A},
                 lambda r: (f"Split across {len(r['cost_centres']) or len(r['entities'])} "
                            f"{'cost centres' if r['cost_centres'] else 'entities'}") if r["allocations"]
                 else "Single allocation"))

    def cutoff(vendor_id, service_period, amount_usd):
        cal = {p_["period"]: p_ for p_ in s.reference["close_calendar"]["periods"]}
        if not service_period or not service_period.get("start"):
            return {"closed_share": 0}
        start, end = date.fromisoformat(service_period["start"]), date.fromisoformat(service_period["end"])
        days = (end - start).days + 1
        closed_days, periods = 0, []
        for p_ in cal.values():
            if p_["status"] != "CLOSED":
                continue
            ps, pe = date.fromisoformat(p_["start"]), date.fromisoformat(p_["end"])
            overlap = (min(end, pe) - max(start, ps)).days + 1
            if overlap > 0:
                closed_days += overlap
                periods.append(p_["period"])
        if not closed_days:
            return {"closed_share": 0}
        in_closed = round(amount_usd * closed_days / days, 2)
        accruals = [j for j in s.journals if j["reference"] == vendor_id and j["category"] == "Accrual"
                    and j["account"] == "2150"]
        accrued = round(sum(j["cr"] for j in accruals), 2)
        return {"closed_share": round(closed_days / days, 3), "periods": periods, "amount_in_closed_usd": in_closed,
                "accrued_usd": accrued, "accrual_je": accruals[0]["je_id"] if accruals else None,
                "variance_usd": round(in_closed - accrued, 2),
                "materiality_usd": s.policies["cutoff"]["materiality_usd"]}

    reg.add(Tool("cutoff.check", "coding", "For services consumed in a closed period, find the period-end accrual "
                 "and measure what was not accrued.", cutoff,
                 {"vendor_id": S, "service_period": opt(O), "amount_usd": N}, {"accrued_usd": N, "variance_usd": N},
                 lambda r: "Service in open period" if not r["closed_share"] else
                 (f"{', '.join(r['periods'])}: ${r['amount_in_closed_usd']:,.0f} consumed, "
                  f"${r['accrued_usd']:,.0f} accrued ({r['accrual_je'] or 'no accrual'})"), kind="history",
                 investigator=True))

    def use_tax(vendor_id, doc):
        v = s.vendors[vendor_id]
        pol = s.policies["tax"]
        if v["category"] not in pol["taxable_categories"] or doc.get("tax") or doc.get("entity") != "US01" \
                or v.get("region") == "MO" or v["currency"] != "USD":
            return {"due": False}
        amount = round(doc["subtotal"] * pol["use_tax_rate"], 2)
        return {"due": True, "taxable_usd": doc["subtotal"], "rate": pol["use_tax_rate"], "amount_usd": amount,
                "account": pol["use_tax_account"], "jurisdiction": pol["jurisdiction"],
                "seller_region": v.get("region")}

    reg.add(Tool("tax.use_tax", "coding", "Accrue use tax when an out-of-state seller charged no sales tax on "
                 "taxable goods shipped to Missouri.", use_tax, {"vendor_id": S, "doc": O}, {"due": B},
                 lambda r: f"Use tax ${r['amount_usd']:,.2f} due ({r['rate']:.2%})" if r["due"] else "No use tax due"))

    # ---------- payment ----------
    def terms(vendor_id, doc, today):
        v = s.vendors[vendor_id]
        pol = s.policies["payment"]["discount_terms"].get(v["payment_terms"])
        inv = date.fromisoformat(doc["invoice_date"])
        out = {"terms": v["payment_terms"], "due_date": doc.get("due_date"), "discount": None}
        if pol:
            by = inv + timedelta(days=pol["days"])
            amount = round(doc["total"] * pol["discount"], 2)
            out["discount"] = {"rate": pol["discount"], "pay_by": by.isoformat(), "amount": amount,
                               "currency": doc["currency"], "open": today <= by.isoformat() and
                               amount >= s.policies["payment"]["min_discount_usd"]}
        return out

    reg.add(Tool("payment.terms", "risk", "Due date from agreed terms and any early-payment discount still open.",
                 terms, {"vendor_id": S, "doc": O, "today": S}, {"due_date": S, "discount": O},
                 lambda r: f"{r['terms']}, due {r['due_date']}" + (
                     f"; discount {r['discount']['amount']:,.2f} by {r['discount']['pay_by']}"
                     f" ({'open' if r['discount']['open'] else 'missed'})" if r["discount"] else "")))

    # ---------- read-only lookups for the investigator ----------
    def vendor_profile(vendor_id):
        v = s.vendors.get(vendor_id)
        if not v:
            return {"error": f"No vendor {vendor_id}"}
        return {k: v.get(k) for k in ("vendor_id", "name", "category_label", "status", "entity", "currency",
                                      "city", "region", "payment_terms", "default_gl", "default_cc",
                                      "created_date", "remit_email", "typical_invoice")} | {
            "bank": {"type": v["bank"].get("type"), "account_last4": v["bank"].get("account_last4")}}

    reg.add(Tool("vendor.profile", "investigator", "Vendor master record: category, terms, defaults, typical invoice "
                 "range, remit email and masked bank account.", vendor_profile, {"vendor_id": S}, {"name": S},
                 lambda r: r.get("name") or r.get("error"), kind="state", investigator=True))
    reg.add(Tool("vendor.bank_change_log", "investigator", "Every change to the supplier's bank details, with "
                 "channel and call-back status.", lambda vendor_id: {"changes": s.vendors[vendor_id]["bank_change_log"]}
                 if vendor_id in s.vendors else {"changes": []}, {"vendor_id": S}, {"changes": A},
                 lambda r: f"{len(r['changes'])} change(s)", kind="state", investigator=True))

    def vendor_invoices(vendor_id, limit=10):
        invs = s.history_by_vendor.get(vendor_id, [])[-int(limit):]
        return {"invoices": [{"invoice_num": i["invoice_num"], "date": i["invoice_date"], "total_usd": i["total_usd"],
                              "accounts": sorted({l["corrected_gl"] or l["gl"] for l in i["lines"]
                                                  if l.get("line_type") != "TAX"}),
                              "requester": s.people.get(i["requester_id"], {}).get("name"),
                              "po_number": i["po_number"], "matter": i.get("matter"),
                              "service_period": i.get("service_period")} for i in invs],
                "count_18m": len(s.history_by_vendor.get(vendor_id, []))}

    reg.add(Tool("history.vendor_invoices", "investigator", "The supplier's most recent invoices: amounts, accounts, "
                 "requesters, POs and service periods.", vendor_invoices, {"vendor_id": S, "limit": opt(N)},
                 {"invoices": A}, lambda r: f"{len(r['invoices'])} of {r['count_18m']} invoices", kind="history",
                 investigator=True))

    def similar_lines(vendor_id, description, limit=6):
        out = []
        for li, sim, same, _k in rec.similar_lines(vendor_id, description)[:int(limit)]:
            l = s.lines[li]
            out.append({"vendor": l["vendor_name"], "same_supplier": same, "invoice_num": l["invoice_num"],
                        "date": l["invoice_date"], "description": l["description"], "account": l["gl"],
                        "cost_centre": l["cc"], "unit_price": l["unit_price"], "similarity": round(sim, 2)})
        return {"lines": out}

    reg.add(Tool("history.similar_lines", "investigator", "Past invoice lines most similar to a description, with "
                 "how each was coded.", similar_lines, {"vendor_id": S, "description": S, "limit": opt(N)},
                 {"lines": A}, lambda r: f"{len(r['lines'])} similar line(s)", kind="history", investigator=True))

    def find_invoice(invoice_num, vendor_id=None):
        num = str(invoice_num).lower().lstrip("inv-").lstrip("0")
        hits = []
        for q in s.intake:
            d = q["document"]
            if str(d.get("invoice_num", "")).lower().lstrip("inv-").lstrip("0") == num and \
                    (not vendor_id or q.get("vendor_hint") == vendor_id):
                hits.append({"source": "queue", "intake_id": q["intake_id"], "received_at": q["received_at"],
                             "invoice_num": d["invoice_num"], "invoice_date": d["invoice_date"], "total": d["total"],
                             "currency": d["currency"], "service_period": d.get("service_period"),
                             "lines": [l["description"] for l in d["lines"]]})
        for i in s.history_by_vendor.get(vendor_id, []) if vendor_id else []:
            if str(i["invoice_num"]).lower().lstrip("inv-").lstrip("0") == num:
                hits.append({"source": "history", "invoice_num": i["invoice_num"], "invoice_date": i["invoice_date"],
                             "total": i["total"], "paid_date": i.get("paid_date")})
        return {"matches": hits}

    reg.add(Tool("invoice.find", "investigator", "Find an invoice by number (format-insensitive) in today's queue "
                 "and the supplier's history, to compare with the one being worked.", find_invoice,
                 {"invoice_num": S, "vendor_id": opt(S)}, {"matches": A}, lambda r: f"{len(r['matches'])} match(es)",
                 kind="history", investigator=True))
    reg.add(Tool("po.open_for_vendor", "investigator", "Open purchase orders for the supplier.",
                 lambda vendor_id: {"pos": [{k: p_[k] for k in ("po_number", "description", "open_amount",
                                                               "created_date", "status")}
                                            for p_ in s.open_pos_by_vendor.get(vendor_id, [])][:10]},
                 {"vendor_id": S}, {"pos": A}, lambda r: f"{len(r['pos'])} open PO(s)", kind="state",
                 investigator=True))
    reg.add(Tool("policy.approval_matrix", "investigator", "The approval matrix: amount tiers, category rules and "
                 "limits by level.", lambda: {"matrix": s.policies["approval_matrix"],
                                             "limits": s.policies["approval_limits"]},
                 {}, {"matrix": O}, lambda r: f"{len(r['matrix']['tiers'])} tiers", investigator=True))

    def directory(query):
        from rapidfuzz import fuzz, process
        names = {pid: p_["name"] for pid, p_ in s.people.items()}
        hits = process.extract(query, names, scorer=fuzz.WRatio, limit=5, score_cutoff=70)
        by_cc = [pid for pid, p_ in s.people.items() if p_["cost_centre"] == query]
        ids = [h[2] for h in hits] + by_cc[:5]
        return {"people": [s.person_brief(pid) | {"email": s.people[pid]["email"]} for pid in dict.fromkeys(ids)]}

    reg.add(Tool("people.directory", "investigator", "Look up people by name or cost-centre code: title, cost "
                 "centre, approval limit.", directory, {"query": S}, {"people": A},
                 lambda r: f"{len(r['people'])} person(s)", kind="state", investigator=True))

    def search_vendors(name):
        from rapidfuzz import fuzz, process
        names = {vid: v["name"] for vid, v in s.vendors.items()}
        return {"candidates": [{"vendor_id": h[2], "name": h[0], "score": round(h[1], 1),
                                "category": s.vendors[h[2]]["category_label"]}
                               for h in process.extract(name, names, scorer=fuzz.token_sort_ratio, limit=5)]}

    reg.add(Tool("vendor.search", "investigator", "Search the vendor master for names close to a supplier name.",
                 search_vendors, {"name": S}, {"candidates": A},
                 lambda r: f"closest: {r['candidates'][0]['name']} ({r['candidates'][0]['score']:.0f}%)"
                 if r["candidates"] else "none", kind="state", investigator=True))

    # ---------- explanation ----------
    reg.add(Tool("llm.explain", "supervisor", "Claude writes the reviewer-facing reason from the findings; a "
                 "deterministic template is the fallback.",
                 lambda findings, fallback: dict(zip(("text", "meta"), llm.explain(findings, fallback))),
                 {"findings": O, "fallback": S}, {"text": S, "meta": O},
                 lambda r: f"{len(r['text'].split())} words ({r['meta'].get('source')})", kind="claude",
                 source=lambda r: r["meta"].get("source", "computed")))
    return reg
