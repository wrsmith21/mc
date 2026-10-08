import math
import random
from datetime import date, datetime, time, timedelta

from .catalog import (CATEGORIES, HARDWARE_ITEMS, NETWORK_ITEMS, FURNITURE_ITEMS, SITES, LEGAL_MATTERS, EVENTS,
                      COURSES, ROLES)
from .reference import HISTORY_START, HISTORY_END, PREPAID_POLICY, to_usd

PER_MONTH = {"telecoms": (2, 5), "cloud": (1, 3), "it_services": (2, 4), "facilities": (2, 4), "utilities": (2, 5),
             "security": (1, 3), "contract_labour": (2, 5), "office_supplies": (3, 6), "courier": (3, 5),
             "catering": (2, 5), "market_data": (1, 3), "saas": (1, 1)}
IRREGULAR = {"it_hardware": (26, 65), "network_hw": (6, 26), "consulting": (10, 52), "audit_tax": (5, 16),
             "legal": (8, 38), "marketing": (13, 58), "events": (5, 26), "training": (8, 45),
             "recruitment": (8, 38), "furniture": (4, 20), "printing": (10, 45), "translation": (6, 26)}
ITEMS = {"hardware": HARDWARE_ITEMS, "network": NETWORK_ITEMS, "furniture": FURNITURE_ITEMS}
TAXABLE = {"it_hardware", "network_hw", "furniture", "office_supplies", "printing"}
US_SALES_TAX = 0.0845  # ship-to O'Fallon, MO combined rate
VAT = {"EUR": ("BE-VAT21", 0.21), "INR": ("IN-GST18", 0.18)}
GOODS = {"it_hardware", "network_hw", "furniture", "office_supplies"}
MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

DEMO_MEDIANS = {"V1102": 42_500, "V2007": 58_000, "V4120": 3_520, "V5031": 13_800, "V6208": 15_900}
DEMO_VENDOR_IDS = {"V1043", "V1102", "V2007", "V3015", "V4120", "V5031", "V6208"}
NOISE_SEED = 20261016
VAGUE = ["Services – {mon}", "Professional services rendered – {mon}", "Invoice charges – ref {ref}",
         "Monthly charges – {mon}", "As per agreement – {mon}", "Services per quote Q{ref}",
         "Work completed – order {ref}", "Fees – {mon}"]
DEMO_COUNTS = {"V1043": 60, "V2007": 14, "V5031": 10}


def month_iter(start: date, end: date):
    y, m = start.year, start.month
    while date(y, m, 1) <= end:
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


def month_end(y, m):
    return (date(y + (m // 12), m % 12 + 1, 1) - timedelta(days=1))


def mkey(d: date):
    return f"{d.year}-{d.month:02d}"


def period_name(d: date):
    return f"{MONTH_ABBR[d.month - 1].upper()}-{str(d.year)[2:]}"


class HistoryBuilder:
    def __init__(self, rng: random.Random, vendors, people_by_id, cost_centres):
        # A separate stream for history noise, so adding it leaves every other generated record unchanged.
        self.noise = random.Random(NOISE_SEED)
        self.mixed = {v["vendor_id"]: round(self.noise.uniform(0.10, 0.30), 2) for v in vendors
                      if v["vendor_id"] not in DEMO_VENDOR_IDS and CATEGORIES[v["category"]].get("confusable")
                      and CATEGORIES[v["category"]]["confusable"] not in ("1540", "1310", "1320")
                      and self.noise.random() < 0.25}
        self.rng = rng
        self.vendors = vendors
        self.people = people_by_id
        self.ccs = {c["code"]: c for c in cost_centres}
        self.invoices = []
        self.pos = []
        self.inv_seq = 0
        self.reclass_seq = 0
        self.vendor_seq = {}
        self.specialists = {p["specialist_role"]: p["id"] for p in people_by_id.values() if p.get("specialist_role")}
        self.svp = "E10001"
        self.ap_clerks = [pid for c in ("CC7110", "CC7170") for pid in self.ccs[c]["requester_ids"]
                          if self.people[pid]["level"] == "Staff"]
        self.legal_requesters = [pid for pid in self.ccs["CC5100"]["requester_ids"]]
        self.matter_lawyer = {}
        for code, desc, area in LEGAL_MATTERS:
            self.matter_lawyer[code] = "E31188" if area in ("Commercial", "M&A") else rng.choice(self.legal_requesters)

    # ---------- helpers ----------
    def vendor_median(self, v):
        if v["vendor_id"] in DEMO_MEDIANS:
            return DEMO_MEDIANS[v["vendor_id"]]
        lo, hi = CATEGORIES[v["category"]]["median_range"]
        return round(math.exp(self.rng.uniform(math.log(lo), math.log(hi))), -1)

    def next_invoice_num(self, v, d: date):
        if v["vendor_id"] == "V2007":
            seq = self.vendor_seq.setdefault("V2007", 40)
            self.vendor_seq["V2007"] = seq + 4
            return f"{seq:04d}"
        seq = self.vendor_seq.setdefault(v["vendor_id"], self.rng.randint(120, 8800))
        self.vendor_seq[v["vendor_id"]] = seq + self.rng.randint(1, 3 if v["category"] in PER_MONTH else 40)
        fmt = v["invoice_format"]
        if fmt == "dell":
            return f"77{self.rng.randint(10000, 99999)}"
        if fmt == "northline":
            return f"INV-{d.year}-{(seq % 900) + 100:04d}"
        if fmt == "plain4":
            return f"{seq:04d}"
        if fmt == "cla":
            return f"CLA-{d.year}-{seq % 1000:03d}"
        if fmt == "sfs":
            return f"SFS-{50000 + seq % 9999}"
        if fmt == "bpa":
            return f"BPA-{3000 + seq % 999}"
        if fmt == "wws":
            return f"WWS/{d.year}/{seq % 10000:04d}"
        return fmt.format(yyyy=d.year, yy=str(d.year)[2:], seq=seq)

    def fill(self, template, d: date, period=None, matter=None):
        r = self.rng
        mon = f"{MONTH_ABBR[d.month - 1]} {d.year}"
        matter_desc = next((m[1] for m in LEGAL_MATTERS if m[0] == matter), "") if matter else ""
        wk = d - timedelta(days=(d.weekday() - 4) % 7)
        fy = d.year if d.month >= 1 else d.year - 1
        return template.format(mon=mon, site=r.choice(SITES), qty=r.choice([5, 8, 10, 12, 20, 25, 40, 60, 120]),
                               n=r.randint(1, 4), period=period or "", matter=matter or "", matter_desc=matter_desc,
                               ref=f"{r.choice('ABCDEFGH')}{r.randint(100, 999)}", event=r.choice(EVENTS),
                               course=r.choice(COURSES), role=r.choice(ROLES), wk=wk.strftime("%d %b"), fy=fy)

    def pick_cc(self, v):
        cat = CATEGORIES[v["category"]]
        if v["vendor_id"] in DEMO_VENDOR_IDS or self.rng.random() < 0.96:
            if v["vendor_id"] not in DEMO_VENDOR_IDS and self.noise.random() < 0.12:
                options = [c for c, _ in cat["ccs"] if self.ccs[c]["entity"] == v["entity"] and c != v["default_cc"]]
                if options:
                    return self.noise.choice(options), "legit_variation"
            return v["default_cc"], "normal"
        options = [c for c, _ in cat["ccs"] if self.ccs[c]["entity"] == v["entity"] and c != v["default_cc"]]
        if not options:
            return v["default_cc"], "normal"
        return self.rng.choice(options), "legit_variation"

    def requester_for(self, v, cc, matter=None):
        if matter:
            return self.matter_lawyer[matter]
        if v["vendor_id"] == "V5031":
            return "E20417"
        if v["vendor_id"] == "V1043":
            return "E33901" if self.rng.random() < 0.8 else self.rng.choice(self.ccs["CC4410"]["requester_ids"])
        staff, owner = self.ccs[cc]["requester_ids"][:-1], self.ccs[cc]["requester_ids"][-1]
        return owner if self.rng.random() < 0.08 else self.rng.choice(staff)

    def route(self, amount_usd, cat_key, cc, requester_id, d: date):
        cc_rec = self.ccs[cc]
        chain = []
        if cat_key == "legal":
            chain.append(("legal_ops", self.specialists["legal_ops"]))
        if cat_key == "it_hardware" and amount_usd >= 5_000:
            chain.append(("it_procurement", self.specialists["it_procurement"]))
            chain.append(("fixed_assets", self.specialists["fixed_assets"]))
        ladder = [("cost_centre_owner", cc_rec["owner_id"]), ("director", cc_rec["director_id"]),
                  ("vp", cc_rec["vp_id"]), ("svp", self.svp)]
        start = 0 if amount_usd < 10_000 else (1 if amount_usd < 100_000 else 2)
        for role, pid in ladder[start:]:
            limit = self.people[pid]["approval_limit"]
            if pid == requester_id or (limit is not None and limit < amount_usd):
                continue
            chain.append((role, pid))
            break
        out, t = [], datetime.combine(d, time(9, 0))
        for role, pid in chain:
            t = t + timedelta(days=self.rng.randint(0, 2), hours=self.rng.randint(1, 8),
                              minutes=self.rng.randint(0, 59))
            out.append({"role": role, "approver_id": pid, "approved_at": t.isoformat(timespec="minutes")})
        return out

    def code_line(self, v, base_gl, cc, d: date, noise=True):
        """Apply realistic noise: ~3-5% legitimate variation already chosen upstream, ~1% historic miscoding."""
        cat = CATEGORIES[v["category"]]
        line = {"gl": base_gl, "cc": cc, "coding": "ORIGINAL", "corrected_gl": None, "reclass_je": None,
                "reclass_date": None}
        if noise and self.rng.random() < 0.011 and cat.get("confusable") and base_gl not in ("1310", "1320"):
            line["gl"] = cat["confusable"]
            line["_label"] = "miscode"
            if self.rng.random() < 0.72:
                self.reclass_seq += 1
                rd = month_end(d.year, d.month) + timedelta(days=self.rng.randint(8, 40))
                if rd <= HISTORY_END:
                    line.update(coding="RECLASSIFIED", corrected_gl=base_gl, reclass_date=rd.isoformat(),
                                reclass_je=f"JE-RCL-{rd.year}{rd.month:02d}-{self.reclass_seq:04d}")
        return line

    # ---------- line builders ----------
    def item_lines(self, v, d, target, cc):
        cat = CATEGORIES[v["category"]]
        items = ITEMS[cat["items"]]
        lines, total = [], 0.0
        n = self.rng.randint(*cat["lines"])
        weights = [i[3] for i in items]
        for _ in range(n):
            desc, (lo, hi), acct, _w = self.rng.choices(items, weights)[0]
            unit = round(self.rng.uniform(lo, hi), 2)
            qty = max(1, round(target / n / unit)) if unit < target else 1
            qty = min(qty, 60)
            lines.append({"description": desc, "qty": qty, "unit_price": unit, "amount": round(qty * unit, 2),
                          "base_gl": acct})
            total += qty * unit
        return lines

    def dell_lines(self, d, service: bool):
        if service:
            qty = self.rng.choice([150, 200, 250, 300])
            unit = round(self.rng.uniform(26, 34), 2)
            return [{"description": f"ProSupport hardware service contract – {qty} devices – "
                                    f"{MONTH_ABBR[d.month - 1]} {d.year} quarter",
                     "qty": 1, "unit_price": round(qty * unit, 2), "amount": round(qty * unit, 2), "base_gl": "6420"}]
        hw = [i for i in HARDWARE_ITEMS if i[2] == "1540"]
        acc = [i for i in HARDWARE_ITEMS if i[2] == "6360"]
        lines = []
        main = self.rng.choices(hw, [i[3] for i in hw])[0]
        qty = self.rng.choice([4, 5, 6, 8, 10, 12, 15, 20, 25])
        unit = round(self.rng.uniform(*main[1]), 2)
        lines.append({"description": main[0], "qty": qty, "unit_price": unit, "amount": round(qty * unit, 2),
                      "base_gl": "1540"})
        for a in self.rng.sample(acc, k=self.rng.randint(0, 2)):
            q = qty if self.rng.random() < 0.6 else self.rng.randint(2, qty)
            u = round(self.rng.uniform(*a[1]), 2)
            lines.append({"description": a[0], "qty": q, "unit_price": u, "amount": round(q * u, 2), "base_gl": "6360"})
        return lines

    def text_lines(self, v, d, target, templates, matter=None, period=None):
        cat = CATEGORIES[v["category"]]
        n = self.rng.randint(*cat["lines"])
        picks = self.rng.sample(templates, k=min(n, len(templates)))
        weights = [self.rng.uniform(0.5, 3) for _ in picks]
        weights[0] += 3
        s = sum(weights)
        lines = []
        for t, w in zip(picks, weights):
            amt = round(target * w / s, 2)
            line = {"description": self.fill(t, d, period, matter), "qty": 1, "unit_price": amt, "amount": amt,
                    "base_gl": cat["gl"]}
            if v["vendor_id"] not in DEMO_VENDOR_IDS:
                # Real AP history is noisier than a catalogue: vague lines, and suppliers that teams code two ways.
                if self.noise.random() < 0.10:
                    mon = f"{MONTH_ABBR[d.month - 1]} {d.year}"
                    line["description"] = self.noise.choice(VAGUE).format(mon=mon, ref=self.noise.randint(1000, 9999))
                share = self.mixed.get(v["vendor_id"])
                if share and self.noise.random() < share:
                    line["base_gl"] = cat["confusable"]
                    line["_label"] = "legit_variation"
            lines.append(line)
        if cat["alt"] and self.rng.random() < 0.04:
            gl, t = self.rng.choice(cat["alt"])
            amt = round(target * self.rng.uniform(0.05, 0.25), 2)
            lines.append({"description": self.fill(t, d), "qty": 1, "unit_price": amt, "amount": amt, "base_gl": gl,
                          "_label": "legit_variation"})
        return lines

    # ---------- invoice ----------
    def make_invoice(self, v, d: date, raw_lines, period=None, matter=None, po_backed=None, source=None,
                     noise=True):
        r = self.rng
        cat_key = v["category"]
        cc, cc_label = self.pick_cc(v)
        if matter:
            cc = "CC5100" if v["entity"] == "US01" else v["default_cc"]
        received = d + timedelta(days=r.randint(1, 9))
        gl_date = received
        mk = mkey(d)
        subtotal = round(sum(l["amount"] for l in raw_lines), 2)
        if v["currency"] in VAT:
            tax_code, rate = VAT[v["currency"]]
        elif cat_key in TAXABLE:
            tax_code, rate = "US-MO-ST", US_SALES_TAX
        else:
            tax_code, rate = "US-EXEMPT-SVC", 0.0
        tax = round(subtotal * rate, 2)
        total = round(subtotal + tax, 2)
        total_usd = to_usd(total, v["currency"], mk)
        requester = self.requester_for(v, cc, matter)
        if po_backed is None:
            share = CATEGORIES[cat_key]["po_share"]
            if v["vendor_id"] == "V1043":
                share = 0.0 if any(l["base_gl"] == "6420" for l in raw_lines) else 0.87
            elif v["vendor_id"] in ("V1102", "V2007", "V3015", "V4120", "V5031", "V6208"):
                share = 0.0
            po_backed = r.random() < share
        self.inv_seq += 1
        lines = []
        for i, l in enumerate(raw_lines, 1):
            coded = self.code_line(v, l["base_gl"], cc, d, noise)
            line = {"line_no": i, "description": l["description"], "qty": l["qty"], "unit_price": l["unit_price"],
                    "amount": l["amount"], "amount_usd": to_usd(l["amount"], v["currency"], mk), **coded,
                    "entity": v["entity"], "coded_by": r.choice(self.ap_clerks)}
            if l.get("amortise_to"):
                line["amortise_to"] = l["amortise_to"]
                line["amortisation_months"] = l["amortisation_months"]
            label = coded.pop("_label", None) or l.get("_label") or cc_label
            line.pop("_label", None)
            line["_label"] = label
            lines.append(line)
        if tax and rate and v["currency"] in VAT:
            lines.append({"line_no": len(lines) + 1, "description": f"{tax_code} input tax", "qty": 1,
                          "unit_price": tax, "amount": tax, "amount_usd": to_usd(tax, v["currency"], mk),
                          "gl": "1410", "cc": cc, "coding": "ORIGINAL", "corrected_gl": None, "reclass_je": None,
                          "reclass_date": None, "entity": v["entity"], "coded_by": lines[0]["coded_by"],
                          "line_type": "TAX", "_label": "normal"})
        chain = self.route(total_usd, cat_key, cc, requester, received)
        last = chain[-1]["approved_at"] if chain else received.isoformat()
        terms_days = {"NET30": 30, "NET45": 45, "NET60": 60, "2/10 NET30": 10}[v["payment_terms"]]
        inv = {
            "invoice_id": f"APINV-{d.year}-{self.inv_seq:06d}",
            "vendor_id": v["vendor_id"], "vendor_name": v["name"], "category": cat_key,
            "invoice_num": self.next_invoice_num(v, d), "invoice_date": d.isoformat(),
            "received_date": received.isoformat(), "gl_date": gl_date.isoformat(), "period": period_name(gl_date),
            "entity": v["entity"], "currency": v["currency"], "subtotal": subtotal, "tax_code": tax_code,
            "tax_amount": tax, "total": total, "total_usd": total_usd, "po_number": None,
            "source": source or r.choices(["EMAIL", "SUPPLIER_PORTAL", "PAPER_SCAN"], [0.55, 0.35, 0.10])[0],
            "requester_id": requester, "approval_chain": chain,
            "paid_date": (d + timedelta(days=terms_days + r.randint(-2, 3))).isoformat(),
            "payment_terms": v["payment_terms"], "service_period": period, "matter": matter,
            "lines": lines,
        }
        if inv["paid_date"] > HISTORY_END.isoformat():
            inv["paid_date"] = None
        if po_backed:
            self.attach_po(inv, v, d)
        self.invoices.append(inv)
        return inv

    def attach_po(self, inv, v, d: date):
        r = self.rng
        created = d - timedelta(days=r.randint(7, 45))
        buyer = self.specialists["it_procurement"] if v["category"] in ("it_hardware", "network_hw") else \
            r.choice(self.ccs["CC7180"]["requester_ids"])
        po_lines = []
        for l in inv["lines"]:
            if l.get("line_type") == "TAX":
                continue
            po_lines.append({"line_no": l["line_no"], "description": l["description"], "qty": l["qty"],
                             "unit_price": l["unit_price"], "amount": l["amount"],
                             "gl": l["corrected_gl"] or l["gl"], "cc": l["cc"],
                             "qty_received": l["qty"] if v["category"] in GOODS else None,
                             "qty_billed": l["qty"], "need_by": (created + timedelta(days=21)).isoformat()})
            l["po_line"] = l["line_no"]
        receipts = []
        if v["category"] in GOODS:
            rd = d - timedelta(days=r.randint(0, 6))
            receipts.append({"receipt_num": None, "date": rd.isoformat(), "received_by": inv["requester_id"],
                             "lines": [{"po_line": pl["line_no"], "qty": pl["qty"]} for pl in po_lines]})
        po = {"po_number": None, "type": "STANDARD", "status": "CLOSED", "vendor_id": v["vendor_id"],
              "vendor_name": v["name"], "category": v["category"], "entity": v["entity"],
              "currency": v["currency"], "created_date": created.isoformat(),
              "approved_date": (created + timedelta(days=r.randint(0, 3))).isoformat(),
              "buyer_id": buyer, "requester_id": inv["requester_id"], "cc": po_lines[0]["cc"] if po_lines else None,
              "amount": round(sum(pl["amount"] for pl in po_lines), 2), "lines": po_lines, "receipts": receipts,
              "invoice_ids": [inv["invoice_id"]]}
        self.pos.append(po)
        inv["_po"] = po

    # ---------- vendor patterns ----------
    def build(self):
        for v in self.vendors:
            cat = CATEGORIES[v["category"]]
            median = self.vendor_median(v)
            v["_median"] = median
            if v["vendor_id"] == "V1043":
                self.build_dell(v)
            elif v["vendor_id"] == "V3015":
                self.build_cloudline(v)
            elif cat["freq"] == "monthly" or (cat["freq"] == "monthly_or_annual" and self.rng.random() < 0.6):
                self.build_monthly(v, cat, median)
            elif cat["freq"] in ("annual", "monthly_or_annual"):
                self.build_annual(v, cat, median)
            else:
                self.build_irregular(v, cat, median)
        self.build_open_pos()
        self.invoices.sort(key=lambda i: (i["received_date"], i["vendor_id"]))
        for n, inv in enumerate(self.invoices, 1):
            inv["invoice_id"] = f"APINV-{inv['received_date'][:4]}-{n:06d}"
        self.number_pos()
        return self.invoices, self.pos

    def build_monthly(self, v, cat, median):
        r = self.rng
        lo, hi = PER_MONTH.get(v["category"], (1, 1))
        if v["vendor_id"] in DEMO_MEDIANS:
            lo = hi = 1
        start = HISTORY_START if r.random() < 0.85 or v["vendor_id"] in DEMO_MEDIANS else \
            HISTORY_START + timedelta(days=r.randint(60, 360))
        per_vendor_count = r.randint(lo, hi)
        for y, m in month_iter(start, HISTORY_END):
            for k in range(per_vendor_count):
                d = date(y, m, 1) + timedelta(days=r.randint(0, 4) + k * 7)
                if d > HISTORY_END:
                    continue
                months_in = (y - HISTORY_START.year) * 12 + m - HISTORY_START.month
                target = median * (1 + 0.0025 * months_in) * math.exp(r.gauss(0, cat["spread"]))
                if v["vendor_id"] == "V1102":
                    target = r.uniform(40_100, 43_200)
                lines = self.text_lines(v, date(y, m, 1) - timedelta(days=1), target, cat["templates"])
                self.make_invoice(v, d, lines)
            if cat.get("adhoc_templates") and r.random() < 0.07:
                d = date(y, m, 1) + timedelta(days=r.randint(8, 25))
                if d <= HISTORY_END:
                    t = r.choice(cat["adhoc_templates"])
                    amt = round(median * r.uniform(0.5, 1.1), 2)
                    self.make_invoice(v, d, [{"description": self.fill(t, d), "qty": 1, "unit_price": amt,
                                              "amount": amt, "base_gl": "6420", "_label": "legit_variation"}])

    def build_annual(self, v, cat, median):
        r = self.rng
        anniversary = r.randint(1, 12)
        templates = cat.get("annual_templates") or cat["templates"]
        for y, m in month_iter(HISTORY_START, HISTORY_END):
            if m != anniversary:
                continue
            d = date(y, m, 1) + timedelta(days=r.randint(0, 6))
            start = date(y, m, 1)
            end = date(y + 1, m, 1) - timedelta(days=1)
            period = f"{start.strftime('%d %b %Y').lstrip('0')} – {end.strftime('%d %b %Y').lstrip('0')}"
            target = median * math.exp(r.gauss(0, cat["spread"]))
            lines = self.text_lines(v, d, target, templates, period=period)
            for l in lines:
                if to_usd(l["amount"], v["currency"], mkey(d)) >= PREPAID_POLICY["min_amount"] and l["base_gl"] == cat["gl"]:
                    l["amortise_to"] = cat["gl"]
                    l["amortisation_months"] = 12
                    l["base_gl"] = "1320" if v["category"] == "insurance" else "1310"
            self.make_invoice(v, d, lines, period={"start": start.isoformat(), "end": end.isoformat()})

    def build_irregular(self, v, cat, median):
        r = self.rng
        lo, hi = IRREGULAR[v["category"]]
        count = DEMO_COUNTS.get(v["vendor_id"]) or int(math.exp(r.uniform(math.log(lo), math.log(hi))))
        span = (HISTORY_END - HISTORY_START).days
        days = sorted(r.randint(0, span) for _ in range(count))
        matters = None
        if v["category"] == "legal":
            pool = [m[0] for m in LEGAL_MATTERS]
            matters = r.sample(pool, k=min(len(pool), max(2, count // 3)))
            if v["vendor_id"] == "V2007":
                matters = ["M-2207", "M-2179", "M-2195", "M-2249", "M-2174"]
        for idx, off in enumerate(days):
            d = HISTORY_START + timedelta(days=off)
            target = median * math.exp(r.gauss(0, cat["spread"]))
            if v["vendor_id"] == "V2007":
                target = min(max(target, 21_000), 148_000)
            if v["vendor_id"] == "V5031":
                target = r.uniform(8_200, 19_600)
            if cat.get("items"):
                lines = self.item_lines(v, d, target, None)
                self.make_invoice(v, d, lines)
                continue
            matter = None
            if matters:
                matter = matters[idx % len(matters)]
                if v["vendor_id"] == "V2007" and idx >= count - 3:
                    matter = "M-2207"
            templates = cat["templates"]
            if v["vendor_id"] == "V5031":
                templates = ["Finance process-mapping workshop – {mon}", "AP operating model review – {mon}",
                             "Close calendar optimisation – phase {n}", "Controls design review – {mon}"]
            lines = self.text_lines(v, d, target, templates, matter=matter)
            self.make_invoice(v, d, lines, matter=matter)

    def build_dell(self, v):
        r = self.rng
        span = (HISTORY_END - HISTORY_START).days
        offsets = sorted(r.sample(range(0, span), 60))
        service_idx = set(r.sample(range(60), 5))
        miscode_idx = set(r.sample([i for i in range(60) if i not in service_idx], 3))
        for i, off in enumerate(offsets):
            d = HISTORY_START + timedelta(days=off)
            lines = self.dell_lines(d, i in service_idx)
            inv = self.make_invoice(v, d, lines, po_backed=None if i not in miscode_idx else False, noise=False)
            if i in miscode_idx:
                hw = inv["lines"][0]
                self.reclass_seq += 1
                rd = month_end(d.year, d.month) + timedelta(days=r.randint(14, 31))
                hw.update(gl="6420", coding="RECLASSIFIED", corrected_gl="1540", reclass_date=rd.isoformat(),
                          reclass_je=f"JE-RCL-{rd.year}{rd.month:02d}-{self.reclass_seq:04d}", _label="miscode")
                inv["miscode_note"] = "Keyed to vendor default 6420; reclassified to 1540 at close."

    def build_cloudline(self, v):
        r = self.rng
        start, end = date(2025, 10, 1), date(2026, 9, 30)
        self.make_invoice(v, date(2025, 9, 24), [{
            "description": "Annual platform subscription 1 Oct 2025 – 30 Sep 2026", "qty": 1,
            "unit_price": 112_000.0, "amount": 112_000.0, "base_gl": "1310", "amortise_to": "6350",
            "amortisation_months": 12}], period={"start": start.isoformat(), "end": end.isoformat()})
        self.make_invoice(v, date(2026, 2, 26), [{
            "description": "Additional 25 analyst seats, co-termed 1 Mar 2026 – 30 Sep 2026", "qty": 25,
            "unit_price": 588.0, "amount": 14_700.0, "base_gl": "1310", "amortise_to": "6350",
            "amortisation_months": 7}], period={"start": "2026-03-01", "end": "2026-09-30"})
        for y, m in [(2025, 5), (2025, 8), (2025, 12), (2026, 1), (2026, 4), (2026, 6), (2026, 8)]:
            amt = round(r.uniform(1_150, 2_600), 2)
            self.make_invoice(v, date(y, m, r.randint(3, 9)), [{
                "description": f"API usage overage – {MONTH_ABBR[m - 2]} {y if m > 1 else y - 1}", "qty": 1,
                "unit_price": amt, "amount": amt, "base_gl": "6350"}])

    def build_open_pos(self):
        """POs raised Jul–Oct 2026 that are not yet (fully) invoiced."""
        r = self.rng
        po_cats = {"it_hardware", "network_hw", "furniture", "consulting", "contract_labour", "marketing", "events",
                   "it_services", "office_supplies", "training", "security", "printing"}
        pool = [v for v in self.vendors if v["category"] in po_cats and v["vendor_id"] not in DEMO_VENDOR_IDS]
        window_start, window_end = date(2026, 7, 1), date(2026, 10, 14)
        span = (window_end - window_start).days
        for _ in range(1_550):
            v = r.choice(pool)
            cat = CATEGORIES[v["category"]]
            created = window_start + timedelta(days=r.randint(0, span))
            target = v["_median"] * math.exp(r.gauss(0, cat["spread"]))
            raw = self.item_lines(v, created, target, None) if cat.get("items") else \
                self.text_lines(v, created, target, cat["templates"])
            cc, _ = self.pick_cc(v)
            requester = self.requester_for(v, cc)
            age = (window_end - created).days
            status = "APPROVED" if age < 12 else r.choices(
                ["APPROVED", "PARTIALLY_RECEIVED", "RECEIVED_NOT_BILLED", "PARTIALLY_BILLED"], [3, 2, 2, 2])[0]
            self.add_open_po(v, created, raw, requester, cc, status)
        consult = next(v for v in self.vendors if v["category"] == "consulting" and v["vendor_id"] not in DEMO_VENDOR_IDS
                       and v["entity"] == "US01")
        po = self.add_open_po(consult, date(2026, 8, 18), [
            {"description": "Controls design review – phase 2 (fixed fee)", "qty": 1, "unit_price": 48_000.0,
             "amount": 48_000.0, "base_gl": "6510"}], "E30233", "CC7150", "APPROVED")
        po["_tag"] = "intake_open_po_match"

    def add_open_po(self, v, created, raw, requester, cc, status):
        r = self.rng
        buyer = self.specialists["it_procurement"] if v["category"] in ("it_hardware", "network_hw") else \
            r.choice(self.ccs["CC7180"]["requester_ids"])
        lines = []
        for i, l in enumerate(raw, 1):
            q = l["qty"]
            received = {"APPROVED": 0, "PARTIALLY_RECEIVED": max(1, q // 2) if q > 1 else 0,
                        "RECEIVED_NOT_BILLED": q, "PARTIALLY_BILLED": q}[status]
            billed = {"PARTIALLY_BILLED": max(1, q // 2) if q > 1 else 0}.get(status, 0)
            lines.append({"line_no": i, "description": l["description"], "qty": q, "unit_price": l["unit_price"],
                          "amount": l["amount"], "gl": l["base_gl"], "cc": cc,
                          "qty_received": received if v["category"] in GOODS else None, "qty_billed": billed,
                          "need_by": (created + timedelta(days=r.randint(10, 45))).isoformat()})
        receipts = []
        if v["category"] in GOODS and any(l["qty_received"] for l in lines):
            receipts.append({"receipt_num": None,
                             "date": min(created + timedelta(days=r.randint(5, 20)), date(2026, 10, 14)).isoformat(),
                             "received_by": requester,
                             "lines": [{"po_line": l["line_no"], "qty": l["qty_received"]} for l in lines
                                       if l["qty_received"]]})
        po = {"po_number": None, "type": "STANDARD", "status": status, "vendor_id": v["vendor_id"],
              "vendor_name": v["name"], "category": v["category"], "entity": v["entity"], "currency": v["currency"],
              "created_date": created.isoformat(),
              "approved_date": (created + timedelta(days=r.randint(0, 3))).isoformat(),
              "buyer_id": buyer, "requester_id": requester, "cc": cc,
              "amount": round(sum(l["amount"] for l in lines), 2), "lines": lines, "receipts": receipts,
              "invoice_ids": []}
        self.pos.append(po)
        return po

    def number_pos(self):
        self.pos.sort(key=lambda p: p["created_date"])
        for n, po in enumerate(self.pos):
            po["po_number"] = f"45000{10001 + n * 3 + self.rng.randint(0, 2):05d}"
            for rc_i, rc in enumerate(po["receipts"]):
                rc["receipt_num"] = f"RCV-{po['po_number'][-6:]}-{rc_i + 1}"
        for inv in self.invoices:
            po = inv.pop("_po", None)
            if po:
                inv["po_number"] = po["po_number"]
                po["invoice_ids"] = [inv["invoice_id"]]
