"""Today's non-PO intake queue. Storyboard invoices are fully specified; the rest follow each vendor's pattern."""
import math
import random
from datetime import date, datetime, time, timedelta

from .catalog import CATEGORIES
from .history import PER_MONTH, TAXABLE, US_SALES_TAX, VAT, DEMO_VENDOR_IDS
from .reference import ENTITIES, DEMO_DATE

ENTITY_BY_CODE = {e["code"]: e for e in ENTITIES}
TOTAL_QUEUE = 142
TERMS_DAYS = {"NET30": 30, "NET45": 45, "NET60": 60, "2/10 NET30": 30}


def bill_to(entity):
    e = ENTITY_BY_CODE[entity]
    return {"name": f"Accounts Payable – {e['name']} ({entity})", "address": f"GBSC Finance, {e['city']}"}


def _ts(d: date, h: int, m: int) -> str:
    return datetime.combine(d, time(h, m)).isoformat(timespec="minutes")


def storyboard(vendors_by_id, pos):
    v = vendors_by_id
    open_po = next(p for p in pos if p.get("_tag") == "intake_open_po_match")
    po_vendor = v[open_po["vendor_id"]]
    summit_bank = v["V4120"]["bank"]
    wavre_wrong_vat = "BE0942360146"  # checksum-valid, confirmed not registered on VIES (7 Oct 2026)
    return [
        {"key": "telecoms", "scene": 1, "vendor_id": "V1102", "received_at": _ts(date(2026, 10, 6), 7, 42),
         "channel": "EMAIL", "sender": "billing@northlinecomms.example",
         "subject": "Northline Communications invoice INV-2026-0917 – September 2026",
         "document": {"invoice_num": "INV-2026-0917", "invoice_date": "2026-10-01", "due_date": "2026-10-31",
                      "currency": "USD", "entity": "US01", "account_number": "NL-0048817",
                      "service_period": {"start": "2026-09-01", "end": "2026-09-30"},
                      "lines": [("Monthly mobile service – Sep 2026 (1,212 lines)", 1, 26_840.20),
                                ("Mobile data pooled plan – Sep 2026", 1, 11_215.35),
                                ("International roaming charges – Sep 2026", 1, 4_255.00)],
                      "tax_label": "Taxes & surcharges included", "tax_rate": 0.0}},
        {"key": "dell", "scene": 2, "vendor_id": "V1043", "received_at": _ts(date(2026, 10, 8), 9, 15),
         "channel": "EMAIL", "sender": "us_invoices@dell-billing.example",
         "subject": "Invoice 7781452",
         "document": {"invoice_num": "7781452", "invoice_date": "2026-10-06", "due_date": "2026-11-20",
                      "currency": "USD", "entity": "US01", "customer_po": None,
                      "ordered_by": "Kevin Brandt, IT End-User Services", "order_number": "OR-9918274",
                      "ship_to": "IT End-User Services, Building 2 Dock B, O'Fallon, MO",
                      "lines": [("Latitude 7450 laptop, 16GB RAM, 512GB SSD, Intel Core Ultra 7", 10, 1_845.00)],
                      "tax_label": "Sales tax (MO 8.45%)", "tax_rate": US_SALES_TAX}},
        {"key": "legal", "scene": 3, "vendor_id": "V2007", "received_at": _ts(date(2026, 10, 5), 11, 3),
         "channel": "EMAIL", "sender": "accounts@hartwellpryce.example",
         "subject": "Hartwell & Pryce – Invoice 0098 – Matter M-2207",
         "document": {"invoice_num": "0098", "invoice_date": "2026-10-02", "due_date": "2026-11-01",
                      "currency": "USD", "entity": "US01", "matter": "M-2207",
                      "matter_desc": "Supplier contract review", "client_contact": "J. Ortiz",
                      "service_period": {"start": "2026-08-01", "end": "2026-09-30"},
                      "lines": [("Professional fees – contract review, Aug–Sep 2026 (118.5 hrs)", 1, 84_950.00),
                                ("Disbursements – courier and filing", 1, 1_550.00)],
                      "tax_label": None, "tax_rate": 0.0}},
        {"key": "saas", "scene": 3, "vendor_id": "V3015", "received_at": _ts(date(2026, 10, 9), 14, 26),
         "channel": "SUPPLIER_PORTAL", "sender": "Supplier portal – Cloudline Analytics",
         "subject": "Invoice CLA-2026-114 – annual renewal",
         "document": {"invoice_num": "CLA-2026-114", "invoice_date": "2026-09-28", "due_date": "2026-10-28",
                      "currency": "USD", "entity": "US01", "order_form": "OF-2026-114",
                      "service_period": {"start": "2026-10-01", "end": "2027-09-30"},
                      "lines": [("Annual platform subscription 1 Oct 2026 – 30 Sep 2027 (125 analyst seats)", 1,
                                 120_000.00)],
                      "tax_label": None, "tax_rate": 0.0}},
        {"key": "duplicate", "scene": 4, "vendor_id": "V2007", "received_at": _ts(date(2026, 10, 14), 8, 57),
         "channel": "EMAIL", "sender": "accounts@hartwellpryce.example",
         "subject": "REMINDER: Invoice INV-0098 – payment due",
         "document": {"invoice_num": "INV-0098", "invoice_date": "2026-10-02", "due_date": "2026-11-01",
                      "currency": "USD", "entity": "US01", "matter": "M-2207",
                      "matter_desc": "Supplier contract review", "client_contact": "J. Ortiz",
                      "banner": "COPY – PAYMENT REMINDER",
                      "service_period": {"start": "2026-08-01", "end": "2026-09-30"},
                      "lines": [("Legal services rendered – matter M-2207 – Aug–Sep 2026", 1, 86_500.00)],
                      "tax_label": None, "tax_rate": 0.0}},
        {"key": "bank_change", "scene": 4, "vendor_id": "V4120", "received_at": _ts(date(2026, 10, 14), 10, 12),
         "channel": "EMAIL", "sender": "accounts@summitfaci1ity.example",
         "subject": "URGENT – Invoice SFS-55120 emergency works – new bank details",
         "document": {"invoice_num": "SFS-55120", "invoice_date": "2026-10-10", "due_date": "2026-10-17",
                      "currency": "USD", "entity": "US01",
                      "remit_note": "Please note our new bank details effective immediately.",
                      "remit_bank": {"routing_number": summit_bank["routing_number"],
                                     "account_last4": summit_bank["account_last4"]},
                      "lines": [("Emergency HVAC compressor replacement – O'Fallon campus, Building 4", 1, 9_870.00)],
                      "tax_label": None, "tax_rate": 0.0}},
        {"key": "sod", "scene": 4, "vendor_id": "V5031", "received_at": _ts(date(2026, 10, 13), 16, 4),
         "channel": "EMAIL", "sender": "finance@brightpathadvisory.example",
         "subject": "Brightpath Advisory – BPA-3391",
         "document": {"invoice_num": "BPA-3391", "invoice_date": "2026-10-05", "due_date": "2026-11-04",
                      "currency": "USD", "entity": "US01",
                      "prepared_for": "Diana Moreno, Director, Finance GBSC",
                      "lines": [("Finance process-mapping workshop – Sep 2026 (2 days, 3 consultants)", 1, 14_200.00)],
                      "tax_label": None, "tax_rate": 0.0}},
        {"key": "eu_vat", "scene": None, "vendor_id": "V6208", "received_at": _ts(date(2026, 10, 7), 9, 48),
         "channel": "EMAIL", "sender": "facturation@wavreworkplace.example",
         "subject": "Facture WWS/2026/0412",
         "document": {"invoice_num": "WWS/2026/0412", "invoice_date": "2026-10-03", "due_date": "2026-11-02",
                      "currency": "EUR", "entity": "EU01", "supplier_vat_printed": wavre_wrong_vat,
                      "service_period": {"start": "2026-09-01", "end": "2026-09-30"},
                      "lines": [("Facilities management services – Sep 2026 – Waterloo office", 1, 15_980.00)],
                      "tax_label": "TVA / BTW 21%", "tax_rate": 0.21}},
        {"key": "open_po", "scene": None, "vendor_id": po_vendor["vendor_id"],
         "received_at": _ts(date(2026, 10, 12), 13, 30), "channel": "EMAIL",
         "sender": po_vendor["remit_email"], "subject": f"{po_vendor['name']} – invoice",
         "document": {"invoice_num": None, "invoice_date": "2026-10-09", "due_date": "2026-11-08",
                      "currency": "USD", "entity": "US01",
                      "lines": [("Controls design review – phase 2 (fixed fee)", 1, 48_000.00)],
                      "tax_label": None, "tax_rate": 0.0, "open_po_hint": open_po["po_number"]}},
    ]


class IntakeBuilder:
    def __init__(self, rng: random.Random, hb, vendors, pos):
        self.rng = rng
        self.hb = hb
        self.vendors = vendors
        self.by_id = {v["vendor_id"]: v for v in vendors}
        self.pos = pos

    def _doc_totals(self, doc):
        lines = [{"description": d, "qty": q, "unit_price": u, "amount": round(q * u, 2)} for d, q, u in doc["lines"]]
        subtotal = round(sum(l["amount"] for l in lines), 2)
        tax = round(subtotal * (doc.get("tax_rate") or 0), 2)
        doc["lines"] = lines
        doc["subtotal"] = subtotal
        doc["tax"] = tax
        doc["total"] = round(subtotal + tax, 2)
        return doc

    def record(self, n, v, spec):
        doc = self._doc_totals(dict(spec["document"]))
        if not doc.get("invoice_num"):
            doc["invoice_num"] = self.hb.next_invoice_num(v, date.fromisoformat(doc["invoice_date"]))
        doc.update(vendor_name=v["name"], vendor_city=f"{v['city']}, {v['region']}",
                   vendor_tax_id=doc.get("supplier_vat_printed") or v["tax_id"], bill_to=bill_to(doc["entity"]),
                   remit_to=doc.get("remit_bank") or {k: v["bank"][k] for k in v["bank"] if k != "iban"},
                   payment_terms=v["payment_terms"])
        return {"intake_id": f"IN-2026-{n:05d}", "received_at": spec["received_at"], "channel": spec["channel"],
                "sender": spec["sender"], "subject": spec["subject"], "storyboard_key": spec.get("key"),
                "scene": spec.get("scene"), "vendor_hint": v["vendor_id"], "document": doc,
                "pdf": None}

    def background_spec(self, v, received: date, override=None):
        r = self.rng
        cat = CATEGORIES[v["category"]]
        inv_date = received - timedelta(days=r.randint(1, 6))
        target = v["_median"] * math.exp(r.gauss(0, cat["spread"] * 0.7))
        if cat.get("items"):
            raw = self.hb.item_lines(v, inv_date, target, None)
        else:
            templates = cat.get("annual_templates") if cat["freq"] == "annual" else cat["templates"]
            raw = self.hb.text_lines(v, date(2026, 9, 30), target, templates,
                                     period="1 Oct 2026 – 30 Sep 2027")
        lines = override or [(l["description"], l["qty"], l["unit_price"]) for l in raw]
        if v["currency"] in VAT:
            tax_label, rate = VAT[v["currency"]][0], VAT[v["currency"]][1]
        elif v["category"] in TAXABLE:
            tax_label, rate = "Sales tax (MO 8.45%)", US_SALES_TAX
        else:
            tax_label, rate = None, 0.0
        h, m = r.randint(6, 19), r.randint(0, 59)
        channel = r.choices(["EMAIL", "SUPPLIER_PORTAL", "PAPER_SCAN"], [0.6, 0.32, 0.08])[0]
        doc = {"invoice_num": None, "invoice_date": inv_date.isoformat(),
               "due_date": (inv_date + timedelta(days=TERMS_DAYS[v["payment_terms"]])).isoformat(),
               "currency": v["currency"],
               "entity": v["entity"], "lines": lines, "tax_label": tax_label, "tax_rate": rate}
        if cat["freq"] in ("monthly", "monthly_or_annual") and v["category"] in PER_MONTH:
            doc["service_period"] = {"start": "2026-09-01", "end": "2026-09-30"}
        return {"received_at": _ts(received, h, m), "channel": channel,
                "sender": v["remit_email"] if channel == "EMAIL" else (
                    f"Supplier portal – {v['name']}" if channel == "SUPPLIER_PORTAL" else "Mailroom scan – O'Fallon"),
                "subject": f"Invoice from {v['name']}", "document": doc}

    def build(self):
        r = self.rng
        queue = []
        n = 0
        for spec in storyboard(self.by_id, self.pos):
            n += 1
            queue.append(self.record(n, self.by_id[spec["vendor_id"]], spec))

        # Learning-loop pair: same vendor, a line type it has rarely billed before.
        office = next(v for v in self.vendors if v["category"] == "office_supplies" and v["entity"] == "US01")
        for i, (qty, day, hour) in enumerate([(40, 13, 10), (25, 14, 15)]):
            spec = self.background_spec(office, date(2026, 10, day),
                                        override=[(f"USB-C 65W laptop chargers ({qty})", qty, 38.50)])
            spec["key"] = f"learning_{i + 1}"
            n += 1
            queue.append(self.record(n, office, spec))

        # Unregistered supplier (stops at step 1).
        n += 1
        queue.append({"intake_id": f"IN-2026-{n:05d}", "received_at": _ts(date(2026, 10, 12), 15, 2),
                      "channel": "EMAIL", "sender": "office@quickfixplumbing.example",
                      "subject": "Invoice 2214 – plumbing works", "storyboard_key": "unknown_vendor", "scene": None,
                      "vendor_hint": None, "pdf": None,
                      "document": self._doc_totals({
                          "invoice_num": "2214", "invoice_date": "2026-10-09", "due_date": "2026-10-23",
                          "currency": "USD", "entity": "US01", "vendor_name": "Quickfix Plumbing LLC",
                          "vendor_city": "Wentzville, MO", "vendor_tax_id": None, "bill_to": bill_to("US01"),
                          "remit_to": {"type": "Check", "address": "PO Box 118, Wentzville, MO"},
                          "payment_terms": "Due on receipt",
                          "lines": [("Replace water heater – Building 2 kitchen", 1, 3_480.00)],
                          "tax_label": None, "tax_rate": 0.0})})

        # PO-policy breach from a marketing agency (over $50k without a PO).
        agency = next(v for v in self.vendors if v["category"] == "marketing" and v["entity"] == "US01"
                      and v["_median"] > 20_000)
        n += 1
        spec = self.background_spec(agency, date(2026, 10, 9),
                                    override=[("Creative production – Q4 brand campaign", 1, 61_750.00),
                                              ("Media buying – Oct 2026", 1, 6_400.00)])
        spec["key"] = "po_breach_marketing"
        queue.append(self.record(n, agency, spec))

        # Amount spike on a utility, no bank change: review, not hold.
        util = next(v for v in self.vendors if v["category"] == "utilities" and v["entity"] == "US01")
        n += 1
        spec = self.background_spec(util, date(2026, 10, 11), override=[
            (f"Electricity supply – O'Fallon campus – Sep 2026 (incl. meter back-billing Jun–Aug)", 1,
             round(util["_median"] * 2.7, 2))])
        spec["key"] = "utility_spike"
        queue.append(self.record(n, util, spec))

        # Other legal and consulting invoices that need a requester to confirm receipt.
        legal_firms = [v for v in self.vendors if v["category"] == "legal" and v["vendor_id"] not in DEMO_VENDOR_IDS
                       and v["entity"] == "US01"][:3]
        for i, lf in enumerate(legal_firms):
            n += 1
            spec = self.background_spec(lf, date(2026, 10, 6 + i * 2))
            queue.append(self.record(n, lf, spec))

        allowed = set(PER_MONTH) | {"training", "printing"}
        eligible = [v for v in self.vendors if v["vendor_id"] not in DEMO_VENDOR_IDS
                    and not v["po_required_category"] and v["category"] in allowed]
        r.shuffle(eligible)
        idx = 0
        while len(queue) < TOTAL_QUEUE:
            v = eligible[idx % len(eligible)]
            idx += 1
            received = DEMO_DATE - timedelta(days=r.choices(range(0, 10), [9, 8, 7, 6, 5, 4, 3, 2, 2, 1])[0])
            if received.weekday() >= 5:
                received -= timedelta(days=received.weekday() - 4)
            n += 1
            queue.append(self.record(n, v, self.background_spec(v, received)))

        queue.sort(key=lambda q: q["received_at"])
        for i, q in enumerate(queue, 1):
            q["intake_id"] = f"IN-2026-{i:05d}"
        return queue
