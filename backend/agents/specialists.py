"""The specialist agents. Each owns one question in the non-PO process and acts only through registered tools.

The supervisor calls them in a fixed order on every invoice, so every control always runs. A specialist can stop the
run (unknown supplier, routed out of AP) by returning a terminal status.
"""
import re
from datetime import date

TIMEKEEPER = re.compile(r"^(Partner|Senior Associate|Associate|Paralegal|Principal|Senior Consultant|Consultant) – ")


class Work:
    """The invoice being worked: shared, mutable state the specialists read and extend."""

    def __init__(self, item, live, today=None):
        self.item = item
        self.live = live
        self.as_of = item["received_at"][:10]
        self.today = today or self.as_of
        self.flags = []
        self.result = {"intake_id": item["intake_id"], "received_at": item["received_at"], "channel": item["channel"],
                       "sender": item["sender"], "subject": item["subject"],
                       "storyboard_key": item.get("storyboard_key"), "scene": item.get("scene"),
                       "pdf": item.get("pdf")}
        self.doc = None
        self.vendor = None
        self.vrec = None
        self.line_recs = []
        self.band = None
        self.contrast = None
        self.receipt = None
        self.task = None

    def flag(self, code, severity, step, title, detail):
        self.flags.append({"code": code, "severity": severity, "step": step, "title": title, "detail": detail})

    def usd(self, ctx, amount):
        return ctx.call("fx.to_usd", amount=amount, currency=self.doc["currency"])["usd"]


class IntakeAgent:
    name, title = "intake", "Intake & extraction"

    def run(self, ctx, w):
        item = w.item
        with ctx.step(self.name, "intake", "Received", 0) as st:
            st["detail"] = f"{item['channel'].replace('_', ' ').title()} from {item['sender']}"
            st["facts"] = [f"Subject: {item['subject']}", f"Received {item['received_at'].replace('T', ' ')}"]
        with ctx.step(self.name, "read", "Read the invoice", 0) as st:
            r = ctx.call("invoice.read", item=item, show={"intake_id": item["intake_id"], "pdf": item.get("pdf")})
            w.doc, extraction = r["document"], r["extraction"]
            w.result.update(document=w.doc, extraction=extraction)
            w.result["total_usd"] = w.usd(ctx, w.doc["total"])
            w.subtotal_usd = w.usd(ctx, w.doc["subtotal"])
            src = extraction["source"]
            st["detail"] = {"live": f"Claude read the PDF in {extraction.get('latency_ms', 0) / 1000:.1f}s",
                            "cache": "Claude's reading of this PDF, replayed from cache",
                            "pre-extracted": "Fields captured at intake"}.get(src, "Fields from intake record")
            st["facts"] = [f"{w.doc.get('vendor_name')} · {w.doc.get('invoice_num')} · {w.doc.get('invoice_date')}",
                           f"{len(w.doc['lines'])} line(s) · {w.doc['currency']} {w.doc['total']:,.2f}"]
            if extraction.get("agreement"):
                agree = extraction["agreement"]
                ok = sum(1 for a in agree if a["match"])
                st["facts"].append(f"{ok}/{len(agree)} key fields cross-checked against the intake record")
                if ok < len(agree):
                    st["status"] = "warn"
                    diff = ", ".join(a["field"] for a in agree if not a["match"])
                    w.flag("EXTRACTION_MISMATCH", "warn", 0, "Printed and captured fields differ",
                           f"{diff} read from the PDF differ from the intake record. A person should check "
                           f"before approval.")


class SupplierAgent:
    name, title = "supplier", "Supplier & validity"

    def run(self, ctx, w):
        doc = w.doc
        with ctx.step(self.name, "supplier", "Should this be here?", 1) as st:
            route = ctx.call("intake.route_check", doc=doc, sender=w.item["sender"])
            if route["route"]:
                st["status"] = "warn"
                who = route.get("employee", {}).get("name") if route["route"] == "employee_reimbursement" \
                    else route["entity"]
                st["detail"] = f"Not a non-PO invoice: route to {route['to']}"
                st["facts"] = [f"{'Employee' if route['route'] == 'employee_reimbursement' else 'Internal entity'}: "
                               f"{who}", f"Owner: {route['owner']}"]
                code = "ROUTE_INTERCOMPANY" if route["route"] == "intercompany" else "ROUTE_CONCUR"
                w.flag(code, "hold", 1, f"Route to {route['to']}",
                       ("Intercompany recharge from " + route["entity"] + ": settle through intercompany, not AP.")
                       if route["route"] == "intercompany" else
                       f"{who} is an employee asking to be reimbursed: this is an expense claim for Concur.")
                w.result["routing"] = route
                return "ROUTED_OUT"
            vendor = ctx.call("vendor.resolve", doc=doc)
            sanctions = ctx.call("sanctions.screen", name=doc.get("vendor_name") or "")
            w.result["vendor"], w.result["sanctions"] = vendor, sanctions
            st["facts"].append(f"OFAC SDN screen ({sanctions.get('list_size', 0):,} entries, {sanctions['source']}): "
                               f"{sanctions['status'].replace('_', ' ')}")
            if not vendor["found"]:
                st["status"] = "fail"
                st["detail"] = f"\"{doc.get('vendor_name')}\" is not in the vendor master"
                w.flag("UNKNOWN_SUPPLIER", "hold", 1, "Supplier not in vendor master", vendor["detail"])
                return "VENDOR_ONBOARDING"
            st["detail"] = f"Matched {vendor['vendor_id']} {vendor['name']} ({vendor['match_score']:.0f}%) · " \
                           f"{vendor['category_label']}"
            st["facts"].append(f"Active supplier since {vendor['since'][:4]} · terms {vendor['terms']}")
            if sanctions["status"] == "potential_match":
                st["status"] = "fail"
                w.flag("SANCTIONS", "hold", 1, "Potential sanctions match",
                       f"Name is similar to SDN entry {sanctions['matches'][0]['name']}.")
        w.vendor = vendor
        w.vid = vendor["vendor_id"]
        w.vrec = ctx.registry.store.vendors[w.vid]

        with ctx.step(self.name, "validity", "Is the invoice valid?", 2) as st:
            validity = ctx.call("invoice.validity", doc=doc, vendor=vendor, live=w.live)
            w.result["validity"] = validity
            st["facts"] = [f"✓ {p}" for p in validity["passed"]]
            if validity["tax"].get("status") == "fail":
                st["status"] = "fail"
                st["detail"] = "VAT number check failed"
                vies = validity["tax"]["vies"]
                st["facts"].append(f"EU VIES ({vies.get('source')}): "
                                   f"{'not registered' if vies.get('valid') is False else 'registered'}")
                w.flag("VAT_INVALID", "hold", 2, "VAT number invalid", validity["tax"]["detail"])
            elif validity["issues"]:
                st["status"] = "warn"
                st["detail"] = "; ".join(validity["issues"])
            else:
                st["detail"] = "Required fields, entity and currency present and consistent"
                if validity["tax"].get("status") == "ok" and validity["tax"].get("vies"):
                    st["facts"].append(f"EU VIES ({validity['tax']['vies']['source']}): VAT number registered")
            dups = ctx.call("invoice.duplicates", vendor_id=w.vid, doc=doc, intake_id=w.item["intake_id"])
            w.result["duplicates"] = dups["matches"]
            if dups["matches"]:
                d = dups["matches"][0]
                st["status"] = "fail"
                st["facts"].append(f"Likely duplicate of {d['invoice_num']} ({d['source']} {d['ref']})")
                w.flag("DUPLICATE", "hold", 2, "Likely duplicate",
                       f"Matches invoice {d['invoice_num']} received {d['received']}: {', '.join(d['reasons'])}.")
            else:
                st["facts"].append(f"No duplicate across {dups['searched']:,} prior and queued invoices")

        with ctx.step(self.name, "po", "Should it have been a PO?", 1) as st:
            open_po = ctx.call("po.open_match", vendor_id=w.vid, subtotal=doc["subtotal"],
                               descriptions=[l["description"] for l in doc["lines"]])
            po_pol = ctx.call("po.policy", category=w.vrec["category"], amount_usd=w.subtotal_usd,
                              has_po_ref=bool(doc.get("customer_po")))
            w.result["po"] = {"policy": po_pol, "open_po": open_po}
            if open_po:
                st["status"] = "warn"
                st["detail"] = f"Matches open PO {open_po['po_number']} — should be matched, not coded"
                w.flag("OPEN_PO_MATCH", "hold", 1, f"Matches open PO {open_po['po_number']}",
                       f"Open PO {open_po['po_number']} for {open_po['description']} "
                       f"(${open_po['open_amount']:,.2f} open, raised {open_po['created_date']} by "
                       f"{open_po['requester']['name']}). Route to 3-way match instead of non-PO coding.")
            elif po_pol["breach"]:
                st["status"] = "warn"
                st["detail"] = "Should have been a PO"
                w.flag("PO_POLICY", "warn", 8, "Should have been a PO", po_pol["detail"])
            else:
                st["detail"] = po_pol["rule"]
            st["facts"].append(f"{w.vrec['category_label']}: {po_pol['rule']}")
            stats = ctx.call("vendor.stats", vendor_id=w.vid)
            st["facts"].append(f"{stats['po_backed']} of {stats['invoices']} past invoices from this supplier had a PO")


class CodingAgent:
    name, title = "coding", "Coding & treatment"

    def run(self, ctx, w):
        doc = w.doc
        with ctx.step(self.name, "coding", "What is it, where does it go?", 4) as st:
            guess = ctx.call("requester.identify", vendor_id=w.vid, doc=doc)
            req_cc = guess["person"]["cost_centre"] if guess.get("person") else None
            timed = [l for l in doc["lines"] if TIMEKEEPER.match(l["description"])]
            fees_usd = w.usd(ctx, sum(l["amount"] for l in timed)) if timed else 0
            label = "Legal services" if w.vrec["category"] == "legal" else "Professional services"
            for l in doc["lines"]:
                amt = w.usd(ctx, l["amount"])
                unit = w.usd(ctx, l["unit_price"])
                desc, qty = l["description"], l["qty"]
                if TIMEKEEPER.match(desc):
                    # Hourly lines are one professional-fees charge: score the service, at the fee total.
                    desc = f"{label} – " + TIMEKEEPER.sub("", desc).split(" (")[0]
                    qty, unit = 1, fees_usd
                r = ctx.call("coding.recommend_line", vendor_id=w.vid, description=desc, qty=qty,
                             unit_usd=unit, amount_usd=amt, service_period=doc.get("service_period"),
                             requester_cc=req_cc, as_of=w.as_of)
                if desc != l["description"]:
                    r["scored_description"] = desc
                w.line_recs.append({**l, "amount_usd": amt, "rec": r})
            split = ctx.call("coding.split", lines=doc["lines"], entity=doc.get("entity"))
            for alloc in split["allocations"]:
                lr = w.line_recs[alloc["line"]]
                lr["entity"] = alloc["entity"]
                if alloc["cost_centre"] and alloc["cost_centre"] != lr["rec"]["cost_centre"]:
                    lr["rec"]["history_cost_centre"] = lr["rec"]["cost_centre"]
                    lr["rec"]["cost_centre"] = alloc["cost_centre"]
                    lr["rec"]["cost_centre_source"] = "Named on the invoice line"
            learned = ctx.call("coding.learned_corrections", vendor_id=w.vid)
            for lr in w.line_recs:
                for lesson in learned.values():
                    if lesson["description_key"] in lr["description"].lower():
                        old_cc = lr["rec"]["cost_centre"]
                        lr["rec"]["cost_centre"] = lesson["cost_centre"]
                        lr["rec"]["cost_centre_confidence"] = max(lr["rec"]["cost_centre_confidence"], 0.9)
                        lr["rec"]["account"] = lesson["account"]
                        lr["rec"]["confidence"] = round(min(0.95, lr["rec"]["confidence"] + 0.22), 3)
                        lr["rec"]["learned"] = {**lesson, "previous_cost_centre": old_cc}
            lrs = w.line_recs
            weights = sum(lr["amount_usd"] for lr in lrs) or 1
            conf = round(sum(lr["rec"]["confidence"] * lr["amount_usd"] for lr in lrs) / weights, 3)
            conf = min(conf, min(lr["rec"]["confidence"] for lr in lrs) + 0.15)
            main = max(lrs, key=lambda lr: lr["amount_usd"])["rec"]
            bands = ctx.registry.store.policies["risk"]["confidence_bands"]
            w.band = "fast_track" if conf >= bands["fast_track"] else ("review" if conf >= bands["review"] else "manual")
            w.contrast = ctx.call("coding.vendor_default_contrast", vendor_id=w.vid, account=main["scored_account"],
                                  description=doc["lines"][0]["description"])
            hist = len(ctx.registry.store.lines)
            w.result["coding"] = {"lines": lrs, "confidence": round(conf, 3), "band": w.band,
                                  "account": main["account"], "account_name": main["account_name"],
                                  "cost_centre": main["cost_centre"], "entity": doc.get("entity"),
                                  "default_contrast": w.contrast, "searched_lines": hist}
            sim_total = sum(lr["rec"]["components"]["similar_same_vendor"] +
                            lr["rec"]["components"]["similar_same_category"] for lr in lrs)
            st["detail"] = f"{main['account']} {main['account_name']} · {main['cost_centre']} · {conf:.0%} confidence"
            st["facts"] = [f"Searched {hist:,} coded lines (18 months); {sim_total} close matches",
                           f"Signals: description match {main['components']['text_vote']:.0%}, supplier history "
                           f"{main['components']['vendor_freq']:.0%}, amount fit {main['components']['amount_fit']:.0%}"]
            c = w.contrast
            if c:
                st["status"] = "warn"
                st["facts"].append(f"Overrides vendor default {c['vendor_default']} {c['vendor_default_name']}")
                w.flag("DEFAULT_OVERRIDE", "info", 4, f"Vendor default {c['vendor_default']} overridden",
                       f"{c['invoices_coded_to_recommended']} past invoices with these items were coded to "
                       f"{main['scored_account']}; the default {c['vendor_default']} is used for "
                       f"{c['default_used_for'] or 'other items'} ({c['invoices_coded_to_default']} invoices)."
                       + (f" {c['past_miscodes_reclassified']} past lines keyed to the default were reclassified at "
                          f"close, on average {c['avg_days_to_reclass']} days later."
                          if c["past_miscodes_reclassified"] else ""))
            if any(lr["rec"].get("learned") for lr in lrs):
                st["facts"].append("Applied a reviewer correction learned from an earlier invoice")
            if split["allocations"]:
                parts = split["cost_centres"] or split["entities"]
                w.result["coding"]["splits"] = [{"line": a_["line"], "description": doc["lines"][a_["line"]]["description"],
                                                 "entity": a_["entity"], "cost_centre": w.line_recs[a_["line"]]["rec"]["cost_centre"],
                                                 "account": w.line_recs[a_["line"]]["rec"]["account"],
                                                 "amount": a_["amount"]} for a_ in split["allocations"]]
                cross_entity = len(split["entities"]) > 1
                st["facts"].append(f"Split across {', '.join(parts)} as named on the invoice lines")
                w.flag("SPLIT", "info", 4, "Coded across " + ("entities" if cross_entity else "cost centres"),
                       f"Lines are allocated to {', '.join(parts)}."
                       + (" Distribution lines carry the user entity; R12 generates the intercompany balancing "
                          "lines for the cross-entity share." if cross_entity else ""))

        with ctx.step(self.name, "treatment", "Capitalise, prepay, cut-off, tax?", 4) as st:
            caps = [lr for lr in w.line_recs if lr["rec"]["capitalise"]]
            amort = next((lr["rec"]["amortisation"] for lr in w.line_recs if lr["rec"]["amortisation"]), None)
            w.result["capitalisation"] = None
            if caps:
                c = caps[0]["rec"]["capitalise"]
                tax_share = doc.get("tax", 0) * (sum(x["amount"] for x in caps) / max(doc["subtotal"], 1))
                cost = round(sum(x["amount_usd"] for x in caps) + w.usd(ctx, tax_share), 2)
                w.result["capitalisation"] = {**c, "units": sum(x["qty"] for x in caps), "asset_cost_usd": cost,
                                              "monthly_depreciation": round(cost / c["useful_life_months"], 2)}
                st["status"] = "warn"
                st["detail"] = f"{c['asset_class']} meets the ${c['threshold_per_unit']:,}/unit threshold — route " \
                               f"to Fixed Asset Accounting"
                st["facts"] = [f"{w.result['capitalisation']['units']} units × ${c['unit_price']:,.2f}; asset cost "
                               f"incl. tax ${cost:,.2f}",
                               f"Useful life {c['useful_life_months']} months · the agent routes, Fixed Asset "
                               f"Accounting decides"]
                w.flag("CAPITALISE", "info", 4, "Route to Fixed Assets",
                       st["facts"][0] + ". Capitalisation decision stays with Fixed Asset Accounting.")
            if amort:
                sched = []
                d0 = date.fromisoformat(amort["start"])
                for i in range(amort["months"]):
                    m = date(d0.year + (d0.month - 1 + i) // 12, (d0.month - 1 + i) % 12 + 1, 1)
                    sched.append({"period": m.strftime("%b-%y").upper(), "debit": amort["expense_account"],
                                  "credit": amort["prepaid_account"], "amount": amort["monthly_amount"]})
                w.result["amortisation"] = {**amort, "schedule": sched}
                st["status"] = "warn"
                st["detail"] = f"Prepaid {amort['prepaid_account']}; {amort['months']} × " \
                               f"${amort['monthly_amount']:,.2f} to {amort['expense_account']}"
                st["facts"] = [f"Service period {amort['start']} → {amort['end']}",
                               "Amortisation journal drafted for Record-to-Report (GL_INTERFACE)"]
                w.flag("PREPAID", "info", 4, "Prepaid with amortisation", st["detail"] + ".")
            cut = ctx.call("cutoff.check", vendor_id=w.vid, service_period=doc.get("service_period"),
                           amount_usd=w.subtotal_usd)
            w.result["cutoff"] = cut if cut["closed_share"] else None
            if cut["closed_share"]:
                if cut["accrued_usd"]:
                    st["facts"].append(f"{', '.join(cut['periods'])} service: accrued ${cut['accrued_usd']:,.2f} in "
                                       f"{cut['accrual_je']}, reversed 1 Oct; this invoice books against the reversal")
                elif cut["amount_in_closed_usd"] >= cut["materiality_usd"]:
                    st["status"] = "warn"
                    w.flag("CUTOFF_UNACCRUED", "warn", 4, "Not accrued in a closed period",
                           f"${cut['amount_in_closed_usd']:,.2f} of service in {', '.join(cut['periods'])} was not "
                           f"accrued at close, so it lands in October. Above the ${cut['materiality_usd']:,} "
                           f"materiality threshold: reported to Record-to-Report as out-of-period expense.")
            tax = ctx.call("tax.use_tax", vendor_id=w.vid, doc=doc)
            w.result["use_tax"] = tax if tax["due"] else None
            if tax["due"]:
                st["status"] = "warn" if st["status"] == "ok" else st["status"]
                st["facts"].append(f"Use tax ${tax['amount_usd']:,.2f} accrued to {tax['account']} "
                                   f"({tax['jurisdiction']})")
                w.flag("USE_TAX", "info", 2, "Use tax accrued",
                       f"Seller in {tax['seller_region']} charged no sales tax on ${tax['taxable_usd']:,.2f} of "
                       f"taxable goods shipped to Missouri. Accrue ${tax['amount_usd']:,.2f} use tax "
                       f"({tax['rate']:.2%}) to {tax['account']} Use Tax Payable.")
            if not caps and not amort:
                st["detail"] = st["detail"] or "Expense in period — no capitalisation or prepaid treatment"
            if not st["detail"] and (w.result["cutoff"] or w.result["use_tax"]):
                st["detail"] = "Cut-off and tax treatment applied"


class PriceAgent:
    """Step 5: is the price right? Rate cards, statements of work, matter budgets."""
    name, title = "price", "Price"

    def run(self, ctx, w):
        doc = w.doc
        with ctx.step(self.name, "price", "Is the price right?", 5) as st:
            facts = []
            card = ctx.call("price.rate_card", vendor_id=w.vid, doc=doc)
            if card["lines"]:
                facts.append(f"{card['hours']:g} hours across {len(card['lines'])} roles checked against "
                             f"{card['letter']}")
                for v in card["variances"]:
                    st["status"] = "warn"
                    w.flag("RATE_VARIANCE", "warn", 5, f"{v['role']} billed above the agreed rate",
                           f"{v['role']} billed at ${v['billed_rate']:,.0f}/hr against ${v['card_rate']:,.0f}/hr in "
                           f"{card['letter']} ({v['hours']:g} hrs): ${v['excess']:,.2f} over. Ask the firm for a "
                           f"credit note or the written rate approval.")
            w.result["price"] = {"rate_card": card}
            if doc.get("matter"):
                budget = ctx.call("price.matter_budget", matter=doc["matter"], amount_usd=w.result["total_usd"])
                w.result["price"]["matter_budget"] = budget
                if budget:
                    facts.append(f"Matter {budget['matter']}: {budget['share_after']:.0%} of the "
                                 f"${budget['budget_usd']:,.0f} budget used after this invoice")
                    if budget["share_after"] >= ctx.registry.store.policies["price"]["matter_budget_warn_share"]:
                        st["status"] = "warn"
                        w.flag("MATTER_BUDGET", "warn", 5, "Matter budget nearly used",
                               f"{budget['share_after']:.0%} of the matter budget is used after this invoice.")
            sow = ctx.call("price.sow", vendor_id=w.vid, doc=doc)
            w.result["price"]["sow"] = sow
            if sow:
                facts.append(f"{sow['sow']} fixed fee ${sow['fixed_fee_usd']:,.2f}: "
                             f"{'invoice matches' if sow['matches_fee'] else 'invoice differs'}")
                if not sow["matches_fee"]:
                    st["status"] = "warn"
                    w.flag("SOW_MISMATCH", "warn", 5, "Differs from the statement of work",
                           f"Invoice subtotal ${doc['subtotal']:,.2f} vs fixed fee ${sow['fixed_fee_usd']:,.2f}.")
            stats = ctx.call("vendor.stats", vendor_id=w.vid)
            if stats["median_usd"]:
                facts.append(f"{w.result['total_usd'] / stats['median_usd']:.1f}× this supplier's median invoice "
                             f"(${stats['median_usd']:,.0f})")
            st["facts"] = facts
            if card["variances"]:
                st["detail"] = f"{len(card['variances'])} rate(s) above the engagement letter"
            elif card["lines"] or sow:
                st["detail"] = "Rates and fees agree with the contract"
            else:
                st["detail"] = "No contract rates apply; amount checked against supplier history"


class ApprovalAgent:
    """Requester, receipt and approval routing."""
    name, title = "approval", "Approval & receipt"

    def run_receipt(self, ctx, w):
        with ctx.step(self.name, "receipt", "Who asked, did we get it?", 3) as st:
            requester = ctx.call("requester.identify", vendor_id=w.vid, doc=w.doc,
                                 cost_centre=w.result["coding"]["cost_centre"])
            receipt = ctx.call("receipt.requirement", vendor_id=w.vid, total_usd=w.result["total_usd"], as_of=w.as_of)
            task = ctx.call("receipt.task", intake_id=w.item["intake_id"])
            if receipt["required"] and not (task and task.get("status") == "confirmed"):
                found = ctx.call("receipt.find_evidence", vendor_id=w.vid, doc=w.doc, as_of=w.as_of)
                if found["evidence"]:
                    e = found["evidence"][0]
                    receipt = {**receipt, "required": False, "rule": "evidence", "evidence": e,
                               "detail": f"{e['description']} ({e['reference']}, recorded by {e['recorded_by_name']} "
                                         f"on {e['date']}). Existing record accepted as evidence of receipt."}
            receipt["task"] = task
            w.receipt, w.task = receipt, task
            w.result["requester"], w.result["receipt"] = requester, receipt
            who = requester["person"]["name"] if requester.get("person") else "unknown"
            st["facts"] = [f"Requester: {who} — {requester['source']}", requester["evidence"]]
            if not receipt["required"]:
                st["detail"] = "Receipt evidenced by an existing record" if receipt["rule"] == "evidence" \
                    else "Covered by standing receipt rule"
                st["facts"].append(receipt["detail"])
            elif task and task.get("status") == "confirmed":
                st["detail"] = f"Receipt confirmed by {task['confirmed_by_name']} at {task['confirmed_at'][11:16]}"
            else:
                st["status"] = "warn"
                st["detail"] = f"Confirm-receipt task {'sent' if task else 'to send'} to {who}"
                st["facts"].append(receipt["detail"])

    def run_approval(self, ctx, w):
        with ctx.step(self.name, "approval", "Who can approve it?", 6) as st:
            requester = w.result["requester"]
            req_id = requester["person"]["id"] if requester.get("person") else None
            route = ctx.call("approval.route", amount_usd=w.result["total_usd"], category=w.vrec["category"],
                             cost_centre=w.result["coding"]["cost_centre"], requester_id=req_id)
            w.result["approval"] = route
            st["detail"] = " → ".join(f"{s['person']['name']} ({s['role_label']})" for s in route["steps"])
            st["facts"] = [route["tier"]] + route["category_rules"] + [route["limit_check"]]
            if route["sod_reroute"]:
                st["status"] = "warn"
                final = route["steps"][-1]["person"]
                st["facts"].insert(0, f"Rerouted: {route['sod_reroute']} Next eligible approver: {final['name']}.")
                w.flag("SOD_REROUTE", "warn", 6, "Rerouted for SoD",
                       f"{route['sod_reroute']} Routed to {final['name']} ({final['title']}).")


class RiskAgent:
    name, title = "risk", "Payment risk"

    def run(self, ctx, w):
        with ctx.step(self.name, "risk", "Is it safe to pay?", 7) as st:
            scored = max(w.line_recs, key=lambda lr: lr["amount_usd"])["rec"]["scored_account"]
            risk = ctx.call("risk.payment_risk", vendor_id=w.vid, doc=w.doc, total_usd=w.result["total_usd"],
                            sender=w.item["sender"], as_of=w.as_of, account=scored)
            w.result["risk"] = risk
            st["facts"] = list(risk["notes"])
            high = [f for f in risk["flags"] if f["severity"] == "high"]
            amount = next((f for f in risk["flags"] if f["code"] == "AMOUNT_VS_NORM"), None)
            for f in risk["flags"]:
                st["facts"].append(f["detail"])
            open_change = any(f["code"] == "RECENT_BANK_CHANGE" and f["severity"] != "low" for f in risk["flags"])
            terms = ctx.call("payment.terms", vendor_id=w.vid, doc=w.doc, today=w.today)
            w.result["payment"] = terms
            st["facts"].append(f"Terms {terms['terms']}, due {terms['due_date']}")
            if terms["discount"] and terms["discount"]["open"]:
                d = terms["discount"]
                w.flag("DISCOUNT", "info", 7, "Early-payment discount available",
                       f"Pay by {d['pay_by']} to take {d['rate']:.0%} ({d['currency']} {d['amount']:,.2f}).")
            if high or (amount and open_change):
                st["status"] = "fail"
                st["detail"] = "Hold before payment — route to vendor master review"
                w.flag("PAYMENT_RISK", "hold", 7, "Payment risk — vendor master review",
                       " ".join(f["detail"] for f in risk["flags"]))
            elif risk["flags"]:
                st["status"] = "warn"
                st["detail"] = risk["flags"][0]["detail"]
                w.flag(risk["flags"][0]["code"], "warn", 7, "Unusual amount" if amount else "Payment check",
                       risk["flags"][0]["detail"])
            else:
                st["detail"] = "Bank details stable, amount within normal range"


SPECIALISTS = [IntakeAgent, SupplierAgent, CodingAgent, PriceAgent, ApprovalAgent, RiskAgent]
