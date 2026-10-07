"""One settlement day of cash application (14 Oct 2026) plus the open AR ledger it applies against."""
import random
from datetime import date, datetime, time, timedelta

CASH_DATE = date(2026, 10, 14)
TOTAL_RECEIPTS = 11_400

PREFIX = ["First", "Lakeshore", "Pacific", "Union", "Heritage", "Citizens", "Pioneer", "Northern", "Coastal",
          "Granite", "Liberty", "Prairie", "Harbor", "Evergreen", "Riverside", "Keystone", "Bayview", "Frontier",
          "Cardinal", "Sterling", "Meridian", "Golden State", "Silverlake", "Ironwood", "Blue Ridge", "Highland",
          "Westgate", "Eastbridge", "Southfield", "Oakridge", "Crescent", "Mariner", "Summit Ridge", "Valley",
          "Capitol", "Lakeside", "Redwood", "Beacon", "Horizon", "Trinity", "Atlantic", "Continental", "Metro",
          "Founders", "Commonwealth", "Ridgeview", "Canyon", "Glacier", "Delta", "Juniper"]
SUFFIX = [("Federal Credit Union", "Issuer"), ("Bank", "Issuer"), ("Bancorp", "Issuer"), ("Savings Bank", "Issuer"),
          ("Community Bank", "Issuer"), ("Trust Company", "Issuer"), ("National Bank", "Issuer"),
          ("Merchant Services", "Acquirer"), ("Acquiring Ltd", "Acquirer"), ("Payments Inc", "Processor"),
          ("Card Services", "Processor"), ("Pay", "Fintech"), ("Money", "Fintech"), ("Retail Group", "Merchant")]
PLACES = ["Ohio", "Texas", "Iowa", "Georgia", "Oregon", "Kentucky", "Nevada", "Vermont", "Arizona", "Maine",
          "Kansas", "Montana", "Idaho", "Utah", "Alabama", "Wisconsin", "Colorado", "Florida", "Virginia",
          "Michigan", "Ontario", "Quebec", "Alberta", "Mexico", "Chile", "Peru", "Ireland", "Poland", "Portugal",
          "Austria", "Kenya", "Ghana", "Singapore", "Malaysia", "Australia", "New Zealand", "the Midwest",
          "the Carolinas", "the Rockies", "the Gulf Coast"]
REGIONS = [("North America", "USD", 0.72), ("Europe", "EUR", 0.14), ("Latin America", "USD", 0.06),
           ("Asia Pacific", "USD", 0.05), ("Middle East & Africa", "USD", 0.03)]
BILLING_TYPES = ["Assessment fees", "Network access fees", "Cross-border fees", "Authorisation fees",
                 "Clearing fees", "Data & services subscription", "Fraud scoring services", "Brand fees"]
SETTLEMENT_ACCOUNTS = {"USD": "Settlement USD – Bank C ••4410", "EUR": "Settlement EUR – Bank D ••7735"}
EXCEPTIONS = [
    ("UNAPPLIED_NO_REMITTANCE", "No remittance advice received", 34),
    ("SHORT_PAY", "Payment less than invoice – likely interchange or fee adjustment deducted", 28),
    ("OVER_PAY", "Payment exceeds open items", 9),
    ("MULTIPLE_MATCH", "Amount matches several open invoices", 14),
    ("UNKNOWN_PAYER", "Payer name not recognised", 11),
    ("FX_DIFFERENCE", "Paid in different currency / rate difference", 9),
    ("INVALID_REFERENCE", "Remittance reference not found", 21),
]


def _payer_alias(name: str) -> str:
    words = name.upper().replace("FEDERAL CREDIT UNION", "FCU").replace("NATIONAL BANK", "NB") \
        .replace("COMMUNITY BANK", "CMNTY BK").replace("SAVINGS BANK", "SVGS BK").split()
    return " ".join(words)[:28]


class CashBuilder:
    def __init__(self, rng: random.Random, clerks):
        self.rng = rng
        self.clerks = clerks
        self.customers = []
        self.ar = []
        self.receipts = []
        self.ar_seq = 9_100_200_000
        self.planted = {}

    def build_customers(self):
        r = self.rng
        used = set()
        fixed = {30418: ("Lakeshore Federal Credit Union", "Issuer", "North America", "USD"),
                 30481: ("Lakeside Community Bank", "Issuer", "North America", "USD")}
        ids = set(fixed)
        while len(ids) < 2_400:
            ids.add(r.randint(10_000, 39_999))
        for cid in sorted(ids):
            if cid in fixed:
                name, ctype, region, cur = fixed[cid]
            else:
                while True:
                    suffix, ctype = r.choice(SUFFIX)
                    name = f"{r.choice(PREFIX)} {suffix}"
                    if name in used:
                        name = f"{name} of {r.choice(PLACES)}"
                    if name not in used and name not in {f[0] for f in fixed.values()}:
                        break
                region, cur, _ = r.choices(REGIONS, [x[2] for x in REGIONS])[0]
            used.add(name)
            self.customers.append({"customer_id": str(cid), "name": name, "type": ctype, "region": region,
                                   "currency": cur, "billing_entity": "EU01" if cur == "EUR" else "US01",
                                   "payer_aliases": [_payer_alias(name)],
                                   "terms": r.choice(["NET15", "NET30"]),
                                   "auto_apply_eligible": r.random() > 0.02})
        self.by_id = {c["customer_id"]: c for c in self.customers}

    def new_ar(self, cust, amount, inv_date, status="OPEN"):
        self.ar_seq += self.rng.randint(1, 9)
        rec = {"ar_invoice": str(self.ar_seq), "customer_id": cust["customer_id"], "customer_name": cust["name"],
               "invoice_date": inv_date.isoformat(), "due_date": (inv_date + timedelta(days=30)).isoformat(),
               "currency": cust["currency"], "amount": amount, "open_amount": amount if status == "OPEN" else 0.0,
               "billing_type": self.rng.choice(BILLING_TYPES), "status": status, "closed_by_receipt": None}
        self.ar.append(rec)
        return rec

    def receipt(self, n, cust, amount, remittance, status, applied_to, applied_by="AUTO", rule=None, reason=None,
                exception_code=None, payer_name=None, applied_customer=None):
        r = self.rng
        stamp = datetime.combine(CASH_DATE, time(r.randint(6, 19), r.randint(0, 59)))
        return {
            "receipt_id": f"RCPT-20261014-{n:06d}", "value_date": CASH_DATE.isoformat(),
            "bank_account": SETTLEMENT_ACCOUNTS[cust["currency"]], "currency": cust["currency"],
            "payer_name": payer_name or cust["payer_aliases"][0], "amount": amount, "remittance": remittance,
            "status": status, "match_rule": rule, "applied_customer": applied_customer or (
                cust["customer_id"] if status in ("AUTO_APPLIED", "MANUAL_APPLIED") else None),
            "applied_invoices": applied_to, "applied_by": applied_by,
            "applied_at": stamp.isoformat(timespec="minutes") if status != "UNAPPLIED" else None,
            "exception_code": exception_code, "exception_reason": reason,
        }

    def build(self):
        r = self.rng
        self.build_customers()
        cust_pool = [c for c in self.customers if c["customer_id"] not in ("30418", "30481")]
        weights = [r.paretovariate(1.3) for _ in cust_pool]

        # Background open AR not paid today.
        for c in self.customers:
            for _ in range(r.randint(2, 9)):
                d = CASH_DATE - timedelta(days=r.randint(1, 60))
                self.new_ar(c, round(r.lognormvariate(9.6, 1.25), 2), d)

        exceptions = [e for e in EXCEPTIONS for _ in range(e[2])]
        n_manual = 52
        n_auto = TOTAL_RECEIPTS - len(exceptions) - n_manual - 4
        seq = 0
        for _ in range(n_auto):
            seq += 1
            c = r.choices(cust_pool, weights)[0]
            k = r.choices([1, 2, 3, 4], [0.7, 0.18, 0.08, 0.04])[0]
            invs = [self.new_ar(c, round(r.lognormvariate(9.6, 1.25), 2),
                                CASH_DATE - timedelta(days=r.randint(15, 45)), status="CLOSED") for _ in range(k)]
            amount = round(sum(i["amount"] for i in invs), 2)
            remit = r.choice(["INV ", "INVOICE ", "", "REF "]) + " / ".join(i["ar_invoice"] for i in invs)
            rid = f"RCPT-20261014-{seq:06d}"
            for i in invs:
                i["closed_by_receipt"] = rid
            rule = "R1 – invoice reference exact" if remit else "R2 – customer + amount"
            self.receipts.append(self.receipt(seq, c, amount, remit, "AUTO_APPLIED",
                                              [{"ar_invoice": i["ar_invoice"], "amount": i["amount"]} for i in invs],
                                              rule=rule))
        for _ in range(n_manual):
            seq += 1
            c = r.choices(cust_pool, weights)[0]
            inv = self.new_ar(c, round(r.lognormvariate(9.4, 1.1), 2), CASH_DATE - timedelta(days=r.randint(20, 50)),
                              status="CLOSED")
            inv["closed_by_receipt"] = f"RCPT-20261014-{seq:06d}"
            clerk = r.choice(self.clerks)
            self.receipts.append(self.receipt(seq, c, inv["amount"], f"PMT {c['customer_id']}", "MANUAL_APPLIED",
                                              [{"ar_invoice": inv["ar_invoice"], "amount": inv["amount"]}],
                                              applied_by=clerk, rule="Manual"))
        for code, reason, _ in exceptions:
            seq += 1
            c = r.choices(cust_pool, weights)[0]
            inv = self.new_ar(c, round(r.lognormvariate(9.8, 1.2), 2), CASH_DATE - timedelta(days=r.randint(15, 45)))
            amount, remit, payer = inv["amount"], f"INV {inv['ar_invoice']}", None
            if code == "UNAPPLIED_NO_REMITTANCE":
                remit = ""
            elif code == "SHORT_PAY":
                amount = round(inv["amount"] * r.uniform(0.93, 0.995), 2)
                remit += " LESS ADJ"
            elif code == "OVER_PAY":
                amount = round(inv["amount"] * r.uniform(1.01, 1.08), 2)
            elif code == "MULTIPLE_MATCH":
                self.new_ar(c, inv["amount"], CASH_DATE - timedelta(days=r.randint(15, 45)))
                remit = f"PAYMENT {c['name'].split()[0].upper()} SEPT"
            elif code == "UNKNOWN_PAYER":
                payer = f"{r.choice(['INTL CLRG', 'CORRESP BK', 'PMT AGENT'])} {r.randint(100, 999)} OBO CLIENT"
                remit = f"INV {inv['ar_invoice']}"
            elif code == "FX_DIFFERENCE":
                amount = round(inv["amount"] * r.uniform(0.97, 1.03), 2)
            elif code == "INVALID_REFERENCE":
                ref = list(inv["ar_invoice"])
                i = r.randint(4, 9)
                ref[i] = str((int(ref[i]) + r.randint(1, 8)) % 10)
                remit = f"INV {''.join(ref)}"
            self.receipts.append(self.receipt(seq, c, amount, remit, "UNAPPLIED", [], applied_by=None,
                                              reason=reason, exception_code=code, payer_name=payer))

        # Planted 1: misapplied – 30418 paid, clerk keyed transposed customer 30481.
        lake, side = self.by_id["30418"], self.by_id["30481"]
        right = self.new_ar(lake, 48_220.00, date(2026, 9, 14))
        right["ar_invoice"] = "9100231877"
        right["open_amount"] = 48_220.00
        wrong = self.new_ar(side, 48_220.00, date(2026, 9, 21), status="CLOSED")
        wrong["ar_invoice"] = "9100229654"
        seq += 1
        wrong["closed_by_receipt"] = f"RCPT-20261014-{seq:06d}"
        self.receipts.append(self.receipt(seq, lake, 48_220.00, "INV 9100231877 SEPT ASSESSMENT", "MANUAL_APPLIED",
                                          [{"ar_invoice": "9100229654", "amount": 48_220.00}], applied_by=self.clerks[1],
                                          rule="Manual", payer_name="LAKESHORE FCU", applied_customer="30481"))
        self.planted["misapplied"] = wrong["closed_by_receipt"]

        # Planted 2: applied to an invoice already settled yesterday (creates a credit balance).
        c = r.choices(cust_pool, weights)[0]
        dup = self.new_ar(c, 17_640.00, date(2026, 9, 10), status="CLOSED")
        dup["closed_by_receipt"] = "RCPT-20261013-004512"
        seq += 1
        self.receipts.append(self.receipt(seq, c, 17_640.00, f"INV {dup['ar_invoice']}", "MANUAL_APPLIED",
                                          [{"ar_invoice": dup["ar_invoice"], "amount": 17_640.00}],
                                          applied_by=self.clerks[0], rule="Manual"))
        self.planted["double_applied"] = f"RCPT-20261014-{seq:06d}"

        # Planted 3: put on account although remittance (one digit OCR slip) points at an open invoice.
        c = r.choices(cust_pool, weights)[0]
        target = self.new_ar(c, 9_315.40, date(2026, 9, 18))
        slip = target["ar_invoice"][:-2] + "8" + target["ar_invoice"][-1]
        if slip == target["ar_invoice"]:
            slip = target["ar_invoice"][:-2] + "3" + target["ar_invoice"][-1]
        seq += 1
        self.receipts.append(self.receipt(seq, c, 9_315.40, f"INV {slip}", "ON_ACCOUNT", [],
                                          applied_by=self.clerks[0], rule="Manual – on account",
                                          applied_customer=c["customer_id"]))
        self.planted["missed_match"] = f"RCPT-20261014-{seq:06d}"

        # Planted 4: unknown payer that is a known alias of a customer with an exact open-item match.
        c = r.choices(cust_pool, weights)[0]
        open_inv = self.new_ar(c, 126_480.00, date(2026, 9, 12))
        seq += 1
        self.receipts.append(self.receipt(seq, c, 126_480.00, "", "UNAPPLIED", [], applied_by=None,
                                          reason="No remittance advice received",
                                          exception_code="UNAPPLIED_NO_REMITTANCE"))
        self.planted["amount_only_match"] = f"RCPT-20261014-{seq:06d}"

        r.shuffle(self.receipts)
        return self.customers, self.ar, self.receipts, self.planted
