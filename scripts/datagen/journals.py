"""SEP-26 close: the journal file the horizontal anomaly layer scans."""
import random
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta

from .catalog import CATEGORIES
from .reference import CAPITALISATION_POLICY, COST_CENTRES

PERIOD = "SEP-26"
ACCT_DATE = date(2026, 9, 30)
POST_START = date(2026, 10, 1)
ASSET_LIFE = {r["account"]: r["useful_life_months"] for r in CAPITALISATION_POLICY["rules"]}


class JournalBuilder:
    def __init__(self, rng: random.Random, invoices, pos, vendors, people_by_id, cost_centres):
        self.rng = rng
        self.invoices = invoices
        self.pos = pos
        self.vendors = {v["vendor_id"]: v for v in vendors}
        self.people = people_by_id
        self.ccs = {c["code"]: c for c in cost_centres}
        self.lines = []
        self.batch_seq = 0
        self.je_seq = 0
        gl_team = [pid for c in ("CC7150", "CC7170") for pid in self.ccs[c]["requester_ids"]
                   if self.people[pid]["level"] == "Staff"]
        self.preparers = gl_team
        self.approvers = ["E30233", self.ccs["CC7150"]["owner_id"]]

    def stamp(self, day_offset=None, hour=None):
        d = POST_START + timedelta(days=self.rng.randint(0, 3) if day_offset is None else day_offset)
        while d.weekday() >= 5 and day_offset is None:
            d += timedelta(days=1)
        return datetime.combine(d, time(hour if hour is not None else self.rng.randint(8, 18),
                                        self.rng.randint(0, 59)))

    def batch(self, name, source, category, entity="US01"):
        self.batch_seq += 1
        return {"batch": f"{PERIOD} {name}", "batch_id": f"B{202609}{self.batch_seq:04d}", "source": source,
                "category": category, "entity": entity}

    def entry(self, b, je_name, lines, preparer=None, approver=None, created=None, approved=None, ref=None,
              acct_date=ACCT_DATE):
        """lines: list of (account, cc, dr, cr, description). Balanced by construction."""
        self.je_seq += 1
        dr = round(sum(l[2] for l in lines), 2)
        cr = round(sum(l[3] for l in lines), 2)
        assert abs(dr - cr) < 0.02, (je_name, dr, cr)
        preparer = preparer or (self.rng.choice(self.preparers) if b["source"] in ("Manual", "Spreadsheet") else
                                "SYSTEM")
        created = created or self.stamp()
        if b["source"] in ("Manual", "Spreadsheet"):
            approver = approver or self.rng.choice(self.approvers)
            approved = approved or created + timedelta(hours=self.rng.randint(1, 20))
        je_id = f"JE-{b['entity']}-2609-{self.je_seq:05d}"
        for n, (acct, cc, d, c, desc) in enumerate(lines, 1):
            self.lines.append({
                "je_id": je_id, "je_name": je_name, "je_line": n, "batch": b["batch"], "batch_id": b["batch_id"],
                "source": b["source"], "category": b["category"], "period": PERIOD,
                "accounting_date": acct_date.isoformat(), "entity": b["entity"], "account": acct, "cost_centre": cc,
                "product": "000", "intercompany": "000", "dr": round(d, 2), "cr": round(c, 2),
                "currency": "USD" if b["entity"] == "US01" else ("EUR" if b["entity"] == "EU01" else "INR"),
                "description": desc, "reference": ref, "created_by": preparer,
                "created_at": created.isoformat(timespec="minutes"),
                "approved_by": approver if b["source"] in ("Manual", "Spreadsheet") else None,
                "approved_at": approved.isoformat(timespec="minutes") if approved else None,
            })
        return je_id

    # ---------- standard close activity ----------
    def accruals(self):
        """Services consumed in September where the invoice had not arrived by close."""
        by_vendor = defaultdict(list)
        for inv in self.invoices:
            if inv["po_number"] is None and inv["invoice_date"] >= "2026-03-01":
                by_vendor[inv["vendor_id"]].append(inv)
        candidates = [vid for vid, invs in by_vendor.items() if len(invs) >= 2]
        self.rng.shuffle(candidates)
        groups = defaultdict(list)
        for vid in candidates[:760]:
            groups[self.vendors[vid]["category"]].append(vid)
        for cat_key, vids in groups.items():
            for entity in ("US01", "EU01", "IN01"):
                ents = [vid for vid in vids if self.vendors[vid]["entity"] == entity]
                if not ents:
                    continue
                b = self.batch(f"Accruals – {CATEGORIES[cat_key]['label']} – {entity}", "Spreadsheet", "Accrual",
                               entity)
                rb = self.batch(f"Reversal of AUG-26 Accruals – {CATEGORIES[cat_key]['label']} – {entity}",
                                "Spreadsheet", "Reversal", entity)
                for vid in ents:
                    v = self.vendors[vid]
                    recent = by_vendor[vid][-6:]
                    avg = sum(i["subtotal"] for i in recent) / len(recent)
                    usual = defaultdict(Counter)  # the vendor's usual account per description, not one line's coding
                    for i in by_vendor[vid]:
                        for l in i["lines"]:
                            if l.get("line_type") != "TAX":
                                usual[l["description"].split(" – ")[0]][l["corrected_gl"] or l["gl"]] += 1
                    mix = {}
                    for i in recent:
                        for l in i["lines"]:
                            if l.get("line_type") == "TAX":
                                continue
                            gl = usual[l["description"].split(" – ")[0]].most_common(1)[0][0]
                            if gl in ("1310", "1320", "1410", "1540", "1545", "1530", "1550"):
                                continue
                            key = (gl, l["cc"], l["description"].split(" – ")[0])
                            mix[key] = mix.get(key, 0) + l["amount"]
                    if not mix:
                        continue
                    top = sorted(mix.items(), key=lambda kv: -kv[1])[:4]
                    share = sum(x[1] for x in top)
                    for month, book, factor, created in (("Sep-26", b, self.rng.uniform(0.85, 1.12), None),
                                                         ("Aug-26", rb, self.rng.uniform(0.85, 1.12),
                                                          self.stamp(0, 7))):
                        lines, total = [], 0.0
                        for (gl, cc, label), amt in top:
                            a = round(avg * factor * amt / share, 2)
                            total += a
                            desc = f"{month} accrual – {v['name']} – {label}"
                            lines.append((gl, cc, a, 0, desc))
                        total = round(total, 2)
                        if book is b:
                            lines.append(("2150", "CC7150", 0, total, f"Sep-26 accrual – {v['name']}"))
                            self.entry(b, f"Accrual {v['name']}", lines, ref=vid)
                        else:
                            rev = [(gl, cc, 0, d, f"Reversal of {desc}") for gl, cc, d, _c, desc in lines]
                            rev.insert(0, ("2150", "CC7150", total, 0, f"Reversal of Aug-26 accrual – {v['name']}"))
                            self.entry(rb, f"Reverse Aug accrual {v['name']}", rev, ref=vid, created=created,
                                       acct_date=date(2026, 9, 1))

    def receipt_accruals(self):
        b = self.batch("Receipt Accruals – Period End", "Purchasing", "Receipt Accrual")
        for po in self.pos:
            if po["status"] not in ("RECEIVED_NOT_BILLED", "PARTIALLY_RECEIVED") or po["entity"] != "US01":
                continue
            if po["created_date"] > "2026-09-30":
                continue
            lines = []
            for l in po["lines"]:
                q = l["qty_received"] or 0
                if not q:
                    continue
                amt = round(q * l["unit_price"], 2)
                desc = f"Receipt accrual PO {po['po_number']} line {l['line_no']} – {l['description']}"
                lines.append((l["gl"], l["cc"], amt, 0, desc))
                lines.append(("2130", "CC7150", 0, amt, desc))
            if lines:
                self.entry(b, f"PO {po['po_number']} receipt accrual", lines, ref=po["po_number"])

    def amortisation(self):
        b = self.batch("Prepaid Amortisation", "Spreadsheet", "Amortisation")
        for inv in self.invoices:
            sp = inv.get("service_period")
            if not sp or not (sp["start"] <= "2026-09-30" <= sp["end"]):
                continue
            for l in inv["lines"]:
                gl = l["corrected_gl"] or l["gl"]
                if gl not in ("1310", "1320") or not l.get("amortise_to"):
                    continue
                monthly = round(l["amount_usd"] / l["amortisation_months"], 2)
                desc = f"Sep-26 amortisation – {inv['vendor_name']} – {l['description']}"
                self.entry(b, f"Amortise {inv['vendor_name']}", [(l["amortise_to"], l["cc"], monthly, 0, desc),
                                                                 (gl, l["cc"], 0, monthly, desc)],
                           ref=inv["invoice_id"])

    def depreciation(self):
        b = self.batch("Depreciation – Fixed Assets", "Assets", "Depreciation")
        base = defaultdict(float)
        for inv in self.invoices:
            for l in inv["lines"]:
                gl = l["corrected_gl"] or l["gl"]
                if gl in ASSET_LIFE and inv["invoice_date"] <= "2026-09-30":
                    base[(gl, l["cc"])] += l["amount_usd"]
        for (gl, cc), cost in sorted(base.items()):
            # Opening asset base pre-dates the history window; scale up so depreciation is realistic.
            dep = round(cost * 2.6 / ASSET_LIFE[gl], 2)
            desc = f"Sep-26 depreciation – {gl} – {cc}"
            self.entry(b, f"Depreciation {gl} {cc}", [("7010", cc, dep, 0, desc), ("1590", cc, 0, dep, desc)])

    def payroll(self):
        b = self.batch("Payroll & Bonus Accrual", "Payroll", "Payroll")
        for code, name, entity, fn in COST_CENTRES:
            heads = self.rng.randint(8, 140)
            sal = round(heads * self.rng.uniform(9_400, 14_800), 2)
            bonus = round(sal * self.rng.uniform(0.08, 0.16), 2)
            self.entry(b, f"Payroll accrual {code}", [("6110", code, sal, 0, f"Sep-26 salary accrual – {name}"),
                                                       ("2160", code, 0, sal, f"Sep-26 salary accrual – {name}")])
            self.entry(b, f"Bonus accrual {code}", [("6120", code, bonus, 0, f"Sep-26 bonus accrual – {name}"),
                                                     ("2160", code, 0, bonus, f"Sep-26 bonus accrual – {name}")])

    def allocations(self):
        b = self.batch("IT Cost Allocations", "Spreadsheet", "Allocation")
        pools = [("6340", "CC4430", "Cloud hosting allocation", 1_480_000),
                 ("6310", "CC4420", "Network & telecoms allocation", 690_000),
                 ("6350", "CC4450", "Enterprise software allocation", 1_120_000)]
        receivers = [c for c in COST_CENTRES if c[2] == "US01" and c[3] not in ("IT",)]
        for acct, pool_cc, label, total in pools:
            weights = [self.rng.uniform(0.5, 3) for _ in receivers]
            s = sum(weights)
            lines, allocated = [], 0.0
            for (code, name, *_), w in zip(receivers, weights):
                amt = round(total * w / s, 2)
                allocated += amt
                lines.append((acct, code, amt, 0, f"Sep-26 {label} – {name}"))
            lines.append((acct, pool_cc, 0, round(allocated, 2), f"Sep-26 {label} – pool relief"))
            self.entry(b, f"{label}", lines)

    def intercompany(self):
        fee = 2_840_000.00
        b = self.batch("Intercompany – GBSC Service Charge", "Spreadsheet", "Intercompany", "US01")
        self.entry(b, "GBSC service charge from IN01", [
            ("7910", "CC7100", fee, 0, "Sep-26 GBSC Pune service charge (cost + 8%)"),
            ("2120", "CC7100", 0, fee, "Sep-26 GBSC Pune service charge (cost + 8%)")])
        b2 = self.batch("Intercompany – GBSC Service Charge", "Spreadsheet", "Intercompany", "IN01")
        inr = round(fee * 92.18, 2)
        self.entry(b2, "GBSC service charge to US01", [
            ("1220", "CC7170", inr, 0, "Sep-26 GBSC service charge to US01"),
            ("4910", "CC7170", 0, inr, "Sep-26 GBSC service charge to US01")])
        eu_fee = 410_000.00
        b3 = self.batch("Intercompany – Regional Recharge", "Spreadsheet", "Intercompany", "EU01")
        self.entry(b3, "Regional marketing recharge from US01", [
            ("7910", "CC6140", eu_fee, 0, "Sep-26 regional marketing recharge"),
            ("2120", "CC6140", 0, eu_fee, "Sep-26 regional marketing recharge")])

    def revenue(self):
        products = [("4010", "Transaction processing"), ("4020", "Cross-border"), ("4110", "Value-added services")]
        regions = ["North America", "Latin America", "Europe", "Middle East & Africa", "Asia Pacific"]
        b = self.batch("Revenue Accrual – Unbilled", "Spreadsheet", "Revenue")
        for acct, label in products:
            for reg in regions:
                amt = round(self.rng.uniform(4_000_000, 38_000_000), 2)
                desc = f"Sep-26 unbilled {label.lower()} revenue – {reg}"
                self.entry(b, f"Unbilled {label} {reg}", [("1210", "CC9120", amt, 0, desc),
                                                          (acct, "CC9120", 0, amt, desc)])

    def fx_reval(self):
        b = self.batch("FX Revaluation", "Revaluation", "Revaluation", "US01")
        for acct in ("1210", "1220", "2110", "2120", "1020", "2410"):
            for cur in ("EUR", "GBP", "INR", "BRL", "JPY"):
                amt = round(self.rng.uniform(3_000, 420_000), 2)
                gain = self.rng.random() < 0.5
                desc = f"Sep-26 revaluation {cur} – {acct}"
                lines = [(acct, "CC7120", amt, 0, desc), ("7210", "CC7120", 0, amt, desc)] if gain else \
                    [("7210", "CC7120", amt, 0, desc), (acct, "CC7120", 0, amt, desc)]
                self.entry(b, f"Reval {cur} {acct}", lines)

    def bank_charges(self):
        b = self.batch("Bank Charges", "Manual", "Bank")
        for bank in ["Operating – Bank A", "Operating – Bank B", "Settlement – Bank C", "Settlement – Bank D",
                     "Payroll – Bank A", "Lockbox – Bank B"]:
            for kind in ["Account maintenance", "Wire fees", "ACH fees", "Lockbox processing"]:
                amt = round(self.rng.uniform(180, 14_000), 2)
                desc = f"Sep-26 {kind.lower()} – {bank}"
                self.entry(b, f"Bank charges {bank}", [("7110", "CC7120", amt, 0, desc),
                                                       ("1010", "CC7120", 0, amt, desc)])

    def reclasses(self):
        b = self.batch("Reclassifications", "Manual", "Reclass")
        for inv in self.invoices:
            for l in inv["lines"]:
                if l["coding"] == "RECLASSIFIED" and l["reclass_date"] and "2026-10-01" <= l["reclass_date"] <= "2026-10-31":
                    desc = f"Reclass {inv['vendor_name']} inv {inv['invoice_num']} from {l['gl']} to {l['corrected_gl']}"
                    self.entry(b, desc, [(l["corrected_gl"], l["cc"], l["amount_usd"], 0, desc),
                                         (l["gl"], l["cc"], 0, l["amount_usd"], desc)], ref=inv["invoice_id"])
        moves = [("6510", "CC9110", "CC9130", "Consulting – data strategy recharge to Data & Analytics"),
                 ("6530", "CC4450", "CC4460", "Contractor costs – data platform squad"),
                 ("6810", "CC6100", "CC6130", "Co-marketing spend – partner programme"),
                 ("6910", "CC8120", "CC4440", "Security certification training – cyber team"),
                 ("6350", "CC4450", "CC9140", "Fraud analytics licences – business-owned"),
                 ("6430", "CC5200", "CC5250", "Workplace services – shared floors"),
                 ("6720", "CC5250", "CC6120", "Meeting catering – partner forum"),
                 ("6540", "CC4450", "CC9110", "Analyst advisory seats – product team")]
        for acct, frm, to, desc in moves:
            amt = round(self.rng.uniform(4_000, 85_000), 2)
            self.entry(b, desc, [(acct, to, amt, 0, f"CC reclass – {desc}"), (acct, frm, 0, amt, f"CC reclass – {desc}")])

    # ---------- planted anomalies ----------
    def planted(self):
        manual = self.batch("Manual Journals – GL Team", "Manual", "Accrual")
        preparer = self.preparers[0]
        self.entry(manual, "Laptop refresh – Q3", [
            ("6420", "CC4410", 36_900.00, 0, "Laptop refresh – Q3 – 20 x Latitude 7450 received, invoice pending"),
            ("2150", "CC7150", 0, 36_900.00, "Laptop refresh – Q3 – 20 x Latitude 7450 received, invoice pending")],
            preparer=preparer, approver="E30233", created=self.stamp(1, 16), ref="Email from IT End-User Services")
        self.planted_ids = {"laptop": self.lines[-1]["je_id"]}

        legal = "Sep-26 accrual – Hartwell & Pryce LLP – matter M-2207 contract review"
        b1 = self.batch("Accruals – Legal (Manual)", "Manual", "Accrual")
        self.entry(b1, "Legal accrual Hartwell & Pryce", [("6610", "CC5100", 64_000.00, 0, legal),
                                                          ("2150", "CC7150", 0, 64_000.00, legal)],
                   preparer=self.preparers[1], created=self.stamp(1, 10))
        b2 = self.batch("Accruals – Legal (Spreadsheet upload)", "Spreadsheet", "Accrual")
        self.entry(b2, "Legal accrual – HP LLP", [("6610", "CC5100", 64_000.00, 0, legal.replace("LLP", "LLP ")),
                                                  ("2150", "CC7150", 0, 64_000.00, legal)],
                   preparer=self.preparers[2], created=self.stamp(2, 11))
        self.planted_ids["duplicate"] = self.lines[-1]["je_id"]

        audit = "Sep-26 accrual – statutory audit fee – interim billing 2"
        self.entry(manual, "Audit fee accrual", [("6510", "CC7150", 85_000.00, 0, audit),
                                                 ("2150", "CC7150", 0, 85_000.00, audit)],
                   preparer=self.preparers[1], created=self.stamp(1, 14))
        self.planted_ids["audit"] = self.lines[-1]["je_id"]

        sod_user = self.preparers[3]
        sat = datetime(2026, 10, 3, 23, 41)
        retainer = "Sep-26 accrual – agency retainer – digital campaign"
        self.entry(manual, "Agency retainer accrual", [("6810", "CC6110", 12_400.00, 0, retainer),
                                                       ("2150", "CC7150", 0, 12_400.00, retainer)],
                   preparer=sod_user, approver=sod_user, created=sat, approved=sat + timedelta(minutes=3))
        self.planted_ids["self_approved"] = self.lines[-1]["je_id"]

    def build(self):
        self.accruals()
        self.receipt_accruals()
        self.amortisation()
        self.depreciation()
        self.payroll()
        self.allocations()
        self.intercompany()
        self.revenue()
        self.fx_reval()
        self.bank_charges()
        self.reclasses()
        self.planted()
        return self.lines, self.planted_ids
