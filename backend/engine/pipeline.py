"""The non-PO invoice agent: eight-step process, traced step by step for the UI."""
import time
from datetime import date, timedelta

from .. import llm
from ..store import ROOT
from .checks import Checks
from .policy import Policy
from .recommend import Recommender

BASELINE_MINUTES = {"research_coding": 6, "find_approver": 4, "chase_receipt": 5, "key_invoice": 3}
AGENT_MINUTES = {"FAST_TRACK": 1.5, "RECOMMENDED": 4, "AWAITING_CONFIRMATION": 3, "NEEDS_CODING": 9, "HELD": 6,
                 "MATCH_TO_PO": 2, "VENDOR_ONBOARDING": 5}
STATUS_LABEL = {"FAST_TRACK": "Fast-track", "RECOMMENDED": "Recommended", "NEEDS_CODING": "Needs coding",
                "AWAITING_CONFIRMATION": "Awaiting confirmation", "HELD": "Held", "MATCH_TO_PO": "Match to PO",
                "VENDOR_ONBOARDING": "Held – unknown supplier", "APPROVED": "Approved", "REJECTED": "Rejected"}


class Step:
    def __init__(self, trace, key, label, process_step):
        self.trace, self.key, self.label, self.process_step = trace, key, label, process_step

    def __enter__(self):
        self.t = time.perf_counter()
        self.rec = {"key": self.key, "label": self.label, "process_step": self.process_step, "status": "ok",
                    "detail": "", "facts": []}
        return self.rec

    def __exit__(self, *exc):
        self.rec["ms"] = round((time.perf_counter() - self.t) * 1000, 1)
        self.trace.append(self.rec)
        return False


class Agent:
    def __init__(self, store, state):
        self.s = store
        self.state = state
        self.rec = Recommender(store)
        self.policy = Policy(store)
        self.checks = Checks(store)
        self.queue_order = {q["intake_id"]: i for i, q in enumerate(sorted(store.intake, key=lambda q: q["received_at"]))}
        self.history_line_count = len(store.lines)

    # ---------- helpers ----------
    def _fx_to_usd(self, amount, currency):
        if currency == "USD":
            return amount
        eur, inr = self.s.reference["fx_monthly"]["2026-10"]
        return round(amount * eur, 2) if currency == "EUR" else round(amount / inr, 2)

    def _extraction(self, item):
        doc = dict(item["document"])
        if item.get("extraction_override"):
            return doc, item["extraction_override"]
        meta = {"source": "pre-extracted", "detail": "Read at intake by the overnight batch."}
        if item.get("pdf"):
            pdf_path = ROOT / "data" / item["pdf"]
            if pdf_path.exists():
                try:
                    fields, meta = llm.extract_pdf(pdf_path.read_bytes())
                except Exception as e:  # keep the demo running on any API failure
                    fields, meta = None, {"source": "error", "error": type(e).__name__}
                if fields:
                    meta["fields"] = fields
                    meta["agreement"] = self._agreement(doc, fields)
        return doc, meta

    @staticmethod
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
            out.append({"field": label, "printed": a, "extracted": b, "match": same})
        return out

    # ---------- main ----------
    def process(self, item, live=False):
        trace, flags = [], []
        as_of = item["received_at"][:10]
        doc, extraction = self._extraction(item)
        total_usd = self._fx_to_usd(doc["total"], doc["currency"])
        subtotal_usd = self._fx_to_usd(doc["subtotal"], doc["currency"])
        result = {"intake_id": item["intake_id"], "received_at": item["received_at"], "channel": item["channel"],
                  "sender": item["sender"], "subject": item["subject"], "storyboard_key": item.get("storyboard_key"),
                  "scene": item.get("scene"), "pdf": item.get("pdf"), "document": doc, "extraction": extraction,
                  "total_usd": total_usd}

        with Step(trace, "intake", "Received", 0) as st:
            st["detail"] = f"{item['channel'].replace('_', ' ').title()} from {item['sender']}"
            st["facts"] = [f"Subject: {item['subject']}", f"Received {item['received_at'].replace('T', ' ')}"]

        with Step(trace, "read", "Read the invoice", 0) as st:
            src = extraction["source"]
            st["detail"] = {"live": f"Claude read the PDF in {extraction.get('latency_ms', 0) / 1000:.1f}s",
                            "cache": "Claude extraction replayed from cache",
                            "pre-extracted": "Fields captured at intake"}.get(src, "Fields from intake record")
            st["facts"] = [f"{doc.get('vendor_name')} · {doc.get('invoice_num')} · {doc.get('invoice_date')}",
                           f"{len(doc['lines'])} line(s) · {doc['currency']} {doc['total']:,.2f}"]
            if extraction.get("agreement"):
                ok = sum(1 for a in extraction["agreement"] if a["match"])
                st["facts"].append(f"{ok}/{len(extraction['agreement'])} key fields cross-checked")

        # Step 1: should this be here?
        with Step(trace, "supplier", "Supplier check", 1) as st:
            vendor = self.checks.resolve_vendor(doc)
            sanctions = self.checks.sanctions(doc.get("vendor_name") or "")
            result["vendor"], result["sanctions"] = vendor, sanctions
            st["facts"].append(f"OFAC SDN screen ({sanctions.get('list_size', 0):,} entries, {sanctions['source']}): "
                               f"{sanctions['status'].replace('_', ' ')}")
            if not vendor["found"]:
                st["status"] = "fail"
                st["detail"] = f"\"{doc.get('vendor_name')}\" is not in the vendor master"
                flags.append({"code": "UNKNOWN_SUPPLIER", "severity": "hold", "step": 1,
                              "title": "Supplier not in vendor master", "detail": vendor["detail"]})
                return self._finish(item, result, trace, flags, status="VENDOR_ONBOARDING")
            st["detail"] = f"Matched {vendor['vendor_id']} {vendor['name']} ({vendor['match_score']:.0f}%) · " \
                           f"{vendor['category_label']}"
            st["facts"].append(f"Active supplier since {vendor['since'][:4]} · terms {vendor['terms']}")
            if sanctions["status"] == "potential_match":
                st["status"] = "fail"
                flags.append({"code": "SANCTIONS", "severity": "hold", "step": 1, "title": "Potential sanctions match",
                              "detail": f"Name is similar to SDN entry {sanctions['matches'][0]['name']}."})
        vid = vendor["vendor_id"]
        vrec = self.s.vendors[vid]

        # Step 2: is the invoice valid?
        with Step(trace, "validity", "Invoice validity", 2) as st:
            validity = self.checks.validity(doc, vendor, live=live)
            result["validity"] = validity
            st["facts"] = [f"✓ {p}" for p in validity["passed"]]
            if validity["tax"].get("status") == "fail":
                st["status"] = "fail"
                st["detail"] = "VAT number check failed"
                vies = validity["tax"]["vies"]
                st["facts"].append(f"EU VIES ({vies.get('source')}): "
                                   f"{'not registered' if vies.get('valid') is False else 'registered'}")
                flags.append({"code": "VAT_INVALID", "severity": "hold", "step": 2, "title": "VAT number invalid",
                              "detail": validity["tax"]["detail"]})
            elif validity["issues"]:
                st["status"] = "warn"
                st["detail"] = "; ".join(validity["issues"])
            else:
                st["detail"] = "Required fields, entity and currency present and consistent"
                if validity["tax"].get("status") == "ok" and validity["tax"].get("vies"):
                    st["facts"].append(f"EU VIES ({validity['tax']['vies']['source']}): VAT number registered")

            earlier = [q for q in self.s.intake if self.queue_order[q["intake_id"]] < self.queue_order[item["intake_id"]]]
            dups = self.checks.duplicates(vid, doc, earlier)
            result["duplicates"] = dups
            if dups:
                d = dups[0]
                st["status"] = "fail"
                st["facts"].append(f"Likely duplicate of {d['invoice_num']} ({d['source']} {d['ref']})")
                flags.append({"code": "DUPLICATE", "severity": "hold", "step": 2, "title": "Likely duplicate",
                              "detail": f"Matches invoice {d['invoice_num']} received {d['received']}: "
                                        f"{', '.join(d['reasons'])}."})
            else:
                st["facts"].append(f"No duplicate across {len(self.s.history_by_vendor[vid])} prior invoices "
                                   f"and today's queue")

        # PO check (steps 1 & 8)
        with Step(trace, "po", "PO check", 1) as st:
            open_po = self.policy.open_po_match(vid, doc["subtotal"], [l["description"] for l in doc["lines"]])
            po_pol = self.policy.po_policy(vrec["category"], subtotal_usd, bool(doc.get("customer_po")))
            result["po"] = {"policy": po_pol, "open_po": open_po}
            if open_po:
                st["status"] = "warn"
                st["detail"] = f"Matches open PO {open_po['po_number']} — should be matched, not coded"
                flags.append({"code": "OPEN_PO_MATCH", "severity": "hold", "step": 1,
                              "title": f"Matches open PO {open_po['po_number']}",
                              "detail": f"Open PO {open_po['po_number']} for {open_po['description']} "
                                        f"(${open_po['open_amount']:,.2f} open, raised {open_po['created_date']} by "
                                        f"{open_po['requester']['name']}). Route to 3-way match instead of non-PO "
                                        f"coding."})
            elif po_pol["breach"]:
                st["status"] = "warn"
                st["detail"] = "Should have been a PO"
                flags.append({"code": "PO_POLICY", "severity": "warn", "step": 8, "title": "Should have been a PO",
                              "detail": po_pol["detail"]})
            else:
                st["detail"] = po_pol["rule"]
            st["facts"].append(f"{vrec['category_label']}: {po_pol['rule']}")
            stats = self.s.vendor_stats(vid)
            st["facts"].append(f"{stats['po_backed']} of {stats['invoices']} past invoices from this supplier had a PO")

        # Step 4: what is it and where does it go?
        with Step(trace, "coding", "Coding recommendation", 4) as st:
            requester_guess = self.policy.identify_requester(vid, doc)
            req_cc = requester_guess["person"]["cost_centre"] if requester_guess.get("person") else None
            line_recs = []
            for l in doc["lines"]:
                amt_usd = self._fx_to_usd(l["amount"], doc["currency"])
                unit_usd = self._fx_to_usd(l["unit_price"], doc["currency"])
                r = self.rec.recommend_line(vid, l["description"], l["qty"], unit_usd, amt_usd,
                                            doc.get("service_period"), requester_cc=req_cc, as_of=as_of)
                line_recs.append({**l, "amount_usd": amt_usd, "rec": r})
            learned = self.state.prefix(f"learned:{vid}:")
            for lr in line_recs:
                for k, lesson in learned.items():
                    if lesson["description_key"] in lr["description"].lower():
                        old_cc = lr["rec"]["cost_centre"]
                        lr["rec"]["cost_centre"] = lesson["cost_centre"]
                        lr["rec"]["cost_centre_confidence"] = max(lr["rec"]["cost_centre_confidence"], 0.9)
                        lr["rec"]["account"] = lesson["account"]
                        lr["rec"]["confidence"] = round(min(0.95, lr["rec"]["confidence"] + 0.22), 3)
                        lr["rec"]["learned"] = {**lesson, "previous_cost_centre": old_cc}
            weights = sum(lr["amount_usd"] for lr in line_recs) or 1
            conf = round(sum(lr["rec"]["confidence"] * lr["amount_usd"] for lr in line_recs) / weights, 3)
            conf = min(conf, min(lr["rec"]["confidence"] for lr in line_recs) + 0.15)
            main = max(line_recs, key=lambda lr: lr["amount_usd"])["rec"]
            bands = self.s.policies["risk"]["confidence_bands"]
            band = "fast_track" if conf >= bands["fast_track"] else ("review" if conf >= bands["review"] else "manual")
            contrast = self.rec.vendor_default_contrast(vid, main["scored_account"], doc["lines"][0]["description"])
            result["coding"] = {"lines": line_recs, "confidence": round(conf, 3), "band": band,
                                "account": main["account"], "account_name": main["account_name"],
                                "cost_centre": main["cost_centre"], "entity": doc.get("entity"),
                                "default_contrast": contrast, "searched_lines": self.history_line_count}
            sim_total = sum(lr["rec"]["components"]["similar_same_vendor"] +
                            lr["rec"]["components"]["similar_same_category"] for lr in line_recs)
            st["detail"] = f"{main['account']} {main['account_name']} · {main['cost_centre']} · {conf:.0%} confidence"
            st["facts"] = [f"Searched {self.history_line_count:,} coded lines (18 months); {sim_total} close matches",
                           f"Signals: description match {main['components']['text_vote']:.0%}, supplier history "
                           f"{main['components']['vendor_freq']:.0%}, amount fit {main['components']['amount_fit']:.0%}"]
            if contrast:
                st["status"] = "warn"
                st["facts"].append(f"Overrides vendor default {contrast['vendor_default']} "
                                   f"{contrast['vendor_default_name']}")
                flags.append({"code": "DEFAULT_OVERRIDE", "severity": "info", "step": 4,
                              "title": f"Vendor default {contrast['vendor_default']} overridden",
                              "detail": f"{contrast['invoices_coded_to_recommended']} past invoices with these items "
                                        f"were coded to {main['scored_account']}; the default "
                                        f"{contrast['vendor_default']} is used for "
                                        f"{contrast['default_used_for'] or 'other items'} "
                                        f"({contrast['invoices_coded_to_default']} invoices)."
                                        + (f" {contrast['past_miscodes_reclassified']} past lines keyed to the default "
                                           f"were reclassified at close, on average {contrast['avg_days_to_reclass']} "
                                           f"days later." if contrast["past_miscodes_reclassified"] else "")})
            if any(lr["rec"].get("learned") for lr in line_recs):
                st["facts"].append("Applied a reviewer correction learned from an earlier invoice")

        with Step(trace, "treatment", "Capitalisation & prepaid", 4) as st:
            caps = [lr for lr in line_recs if lr["rec"]["capitalise"]]
            amort = next((lr["rec"]["amortisation"] for lr in line_recs if lr["rec"]["amortisation"]), None)
            result["capitalisation"] = None
            if caps:
                c = caps[0]["rec"]["capitalise"]
                tax_share = doc.get("tax", 0) * (sum(x["amount"] for x in caps) / max(doc["subtotal"], 1))
                cost = round(sum(x["amount_usd"] for x in caps) + self._fx_to_usd(tax_share, doc["currency"]), 2)
                result["capitalisation"] = {**c, "units": sum(x["qty"] for x in caps), "asset_cost_usd": cost,
                                            "monthly_depreciation": round(cost / c["useful_life_months"], 2)}
                st["status"] = "warn"
                st["detail"] = f"{c['asset_class']} meets the ${c['threshold_per_unit']:,}/unit threshold — route to " \
                               f"Fixed Asset Accounting"
                st["facts"] = [f"{result['capitalisation']['units']} units × ${c['unit_price']:,.2f}; asset cost incl. "
                               f"tax ${cost:,.2f}", f"Useful life {c['useful_life_months']} months · the agent routes, "
                                                    f"Fixed Asset Accounting decides"]
                flags.append({"code": "CAPITALISE", "severity": "info", "step": 4, "title": "Route to Fixed Assets",
                              "detail": st["facts"][0] + ". Capitalisation decision stays with Fixed Asset Accounting."})
            if amort:
                sched = []
                d0 = date.fromisoformat(amort["start"])
                for i in range(amort["months"]):
                    m = date(d0.year + (d0.month - 1 + i) // 12, (d0.month - 1 + i) % 12 + 1, 1)
                    sched.append({"period": m.strftime("%b-%y").upper(), "debit": amort["expense_account"],
                                  "credit": amort["prepaid_account"], "amount": amort["monthly_amount"]})
                result["amortisation"] = {**amort, "schedule": sched}
                st["status"] = "warn"
                st["detail"] = f"Prepaid {amort['prepaid_account']}; {amort['months']} × " \
                               f"${amort['monthly_amount']:,.2f} to {amort['expense_account']}"
                st["facts"] = [f"Service period {amort['start']} → {amort['end']}",
                               "Amortisation journal drafted for Record-to-Report (GL_INTERFACE)"]
                flags.append({"code": "PREPAID", "severity": "info", "step": 4, "title": "Prepaid with amortisation",
                              "detail": st["detail"] + "."})
            if not caps and not amort:
                st["detail"] = "Expense in period — no capitalisation or prepaid treatment"

        # Step 3: who asked for it and did we get it?
        with Step(trace, "receipt", "Requester & receipt", 3) as st:
            requester = self.policy.identify_requester(vid, doc, result["coding"]["cost_centre"])
            receipt = self.policy.receipt_requirement(vid, total_usd, as_of)
            task = self.state.get(f"receipt:{item['intake_id']}")
            receipt["task"] = task
            result["requester"], result["receipt"] = requester, receipt
            who = requester["person"]["name"] if requester.get("person") else "unknown"
            st["facts"] = [f"Requester: {who} — {requester['source']}", requester["evidence"]]
            if not receipt["required"]:
                st["detail"] = "Covered by standing receipt rule"
                st["facts"].append(receipt["detail"])
            elif task and task.get("status") == "confirmed":
                st["detail"] = f"Receipt confirmed by {task['confirmed_by_name']} at {task['confirmed_at'][11:16]}"
            else:
                st["status"] = "warn"
                st["detail"] = f"Confirm-receipt task {'sent' if task else 'to send'} to {who}"
                st["facts"].append(receipt["detail"])

        # Step 7: is it safe to pay?
        with Step(trace, "risk", "Payment risk", 7) as st:
            scored = max(line_recs, key=lambda lr: lr["amount_usd"])["rec"]["scored_account"]
            risk = self.checks.payment_risk(vid, doc, total_usd, item["sender"], as_of, scored)
            result["risk"] = risk
            st["facts"] = list(risk["notes"])
            high = [f for f in risk["flags"] if f["severity"] == "high"]
            amount = next((f for f in risk["flags"] if f["code"] == "AMOUNT_VS_NORM"), None)
            for f in risk["flags"]:
                st["facts"].append(f["detail"])
            if high or (amount and any(f["code"] == "RECENT_BANK_CHANGE" for f in risk["flags"])):
                st["status"] = "fail"
                st["detail"] = "Hold before payment — route to vendor master review"
                flags.append({"code": "PAYMENT_RISK", "severity": "hold", "step": 7,
                              "title": "Payment risk — vendor master review",
                              "detail": " ".join(f["detail"] for f in risk["flags"])})
            elif risk["flags"]:
                st["status"] = "warn"
                st["detail"] = risk["flags"][0]["detail"]
                flags.append({"code": risk["flags"][0]["code"], "severity": "warn", "step": 7,
                              "title": "Unusual amount" if amount else "Payment check",
                              "detail": risk["flags"][0]["detail"]})
            else:
                st["detail"] = "Bank details stable, amount within normal range"

        # Step 6: who can approve it?
        with Step(trace, "approval", "Approval routing", 6) as st:
            req_id = requester["person"]["id"] if requester.get("person") else None
            route = self.policy.route(total_usd, vrec["category"], result["coding"]["cost_centre"], req_id)
            result["approval"] = route
            names = " → ".join(f"{s['person']['name']} ({s['role_label']})" for s in route["steps"])
            st["detail"] = names
            st["facts"] = [route["tier"]] + route["category_rules"] + [route["limit_check"]]
            if route["sod_reroute"]:
                st["status"] = "warn"
                final = route["steps"][-1]["person"]
                st["facts"].insert(0, f"Rerouted: {route['sod_reroute']} Next eligible approver: {final['name']}.")
                flags.append({"code": "SOD_REROUTE", "severity": "warn", "step": 6, "title": "Rerouted for SoD",
                              "detail": f"{route['sod_reroute']} Routed to {final['name']} ({final['title']})."})

        def decide(receipt_ok):
            holds = [f for f in flags if f["severity"] == "hold"]
            if any(f["code"] == "OPEN_PO_MATCH" for f in holds):
                return "MATCH_TO_PO"
            if holds:
                return "HELD"
            if not receipt_ok:
                return "AWAITING_CONFIRMATION"
            if band == "manual":
                return "NEEDS_CODING"
            if band == "fast_track" and not [f for f in flags if f["severity"] == "warn"] and not contrast \
                    and not result["capitalisation"] and not result.get("amortisation"):
                return "FAST_TRACK"
            return "RECOMMENDED"

        confirmed = not receipt["required"] or bool(task and task.get("status") == "confirmed")
        result["status_after_receipt"] = decide(True)
        return self._finish(item, result, trace, flags, status=decide(confirmed))

    # ---------- wrap-up ----------
    def _finish(self, item, result, trace, flags, status):
        decision = self.state.get(f"decision:{item['intake_id']}")
        result["agent_status"] = status
        if decision:
            status = decision["status"]
        result["status"] = status
        result["status_label"] = STATUS_LABEL.get(status, status.title())
        result["flags"] = flags
        result["decision"] = decision
        result["trace"] = trace
        base = sum(BASELINE_MINUTES.values())
        result["minutes"] = {"baseline": base, "agent": AGENT_MINUTES.get(result["agent_status"], 5),
                             "note": "Illustrative handling-time model"}
        findings = self._findings(result)
        result["explanation"], result["explanation_meta"] = llm.explain(findings, self._template_reason(result))
        result["next_action"] = self._next_action(result)
        return result

    def _findings(self, r):
        c = r.get("coding") or {}
        return {"supplier": (r.get("vendor") or {}).get("name") or r["document"].get("vendor_name"),
                "status": r["agent_status"], "recommended_account": c.get("account"),
                "account_name": c.get("account_name"), "cost_centre": c.get("cost_centre"),
                "confidence": c.get("confidence"), "vendor_default_contrast": c.get("default_contrast"),
                "flags": [{"title": f["title"], "detail": f["detail"]} for f in r["flags"]],
                "approval_chain": [s["person"]["name"] + " (" + s["role_label"] + ")"
                                   for s in (r.get("approval") or {}).get("steps", [])],
                "evidence": [{k: e[k] for k in ("vendor", "date", "description", "account")}
                             for e in (c.get("lines") or [{}])[0].get("rec", {}).get("evidence", [])] if c else []}

    def _template_reason(self, r):
        c = r.get("coding")
        if not c:
            return r["flags"][0]["detail"] if r["flags"] else "No recommendation."
        parts = [f"Recommends {c['account']} {c['account_name']} / {c['cost_centre']} at {c['confidence']:.0%} "
                 f"confidence, based on {r['vendor']['name']}'s coding history and similar past invoices."]
        if c.get("default_contrast"):
            d = c["default_contrast"]
            parts.append(f"This overrides the vendor default {d['vendor_default']} {d['vendor_default_name']}: "
                         f"{d['invoices_coded_to_recommended']} past invoices for these items were coded to "
                         f"{c['lines'][0]['rec']['scored_account']}.")
        holds = [f for f in r["flags"] if f["severity"] in ("hold", "warn")]
        if holds:
            parts.append(holds[0]["title"] + ": " + holds[0]["detail"])
        return " ".join(parts)

    def _next_action(self, r):
        s = r["agent_status"]
        steps = (r.get("approval") or {}).get("steps") or []
        first = steps[0]["person"]["name"] if steps else None
        return {"VENDOR_ONBOARDING": "Send to vendor onboarding (KYC, sanctions, bank verification).",
                "HELD": "Hold. Resolve the flagged control before any approval or payment.",
                "MATCH_TO_PO": "Route to 3-way match against the open PO.",
                "AWAITING_CONFIRMATION": f"Waiting for {((r.get('requester') or {}).get('person') or {}).get('name', 'the requester')} to confirm receipt.",
                "NEEDS_CODING": "Ask an AP specialist to code; recommendation shown as a starting point.",
                "FAST_TRACK": f"Fast-tracked within policy to {first} for approval.",
                "RECOMMENDED": f"Review the recommendation, then send to {first} for approval."}.get(s, "")
