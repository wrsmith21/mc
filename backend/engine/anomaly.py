"""Horizontal anomaly layer: the same coding engine pointed at journals, the AP subledger and cash application."""
import re
import time
from collections import Counter, defaultdict
from datetime import datetime

from rapidfuzz.distance import Levenshtein

from .text import tokens

JOURNAL_SOURCES = {"Manual", "Spreadsheet"}
JOURNAL_CATEGORIES = {"Accrual", "Reclass"}
AR_REF = re.compile(r"\b9\d{9}\b")


def _strip_prefix(desc):
    return re.sub(r"^(sep|aug)-26 accrual\s*–\s*", "", desc, flags=re.I)


class AnomalyLayer:
    def __init__(self, store, recommender):
        self.s = store
        self.rec = recommender
        self.cap_rules = {r["account"]: r for r in store.policies["capitalisation"]["rules"]}

    # ---------------- journals ----------------
    def predict_account(self, description):
        sims = self.rec.similar_lines(None, _strip_prefix(description))
        if not sims:
            return None
        votes, best = defaultdict(float), sims[0][1]
        per_key = Counter()
        for li, sim, _same, key in sims:
            per_key[key] += 1
            if per_key[key] > 10:
                continue
            l = self.s.lines[li]
            gl = l["amortise_to"] if l["gl"] in ("1310", "1320") and l["amortise_to"] else l["gl"]
            votes[gl] += sim
        total = sum(votes.values())
        ranked = sorted(((g, v / total) for g, v in votes.items()), key=lambda kv: -kv[1])
        ev = next(self.s.lines[li] for li, *_ in sims)
        return {"account": ranked[0][0], "share": round(ranked[0][1], 3), "best_similarity": round(best, 3),
                "shares": dict(ranked[:4]), "example": {"vendor": ev["vendor_name"], "description": ev["description"],
                                                        "account": ev["gl"], "date": ev["invoice_date"]}}

    def scan_journals(self):
        t = time.perf_counter()
        lines = self.s.journals
        flags = []
        scanned = 0
        for j in lines:
            if j["source"] not in JOURNAL_SOURCES or j["category"] not in JOURNAL_CATEGORIES or j["dr"] <= 0:
                continue
            if not (j["account"].startswith("6") or j["account"].startswith("15")):
                continue
            scanned += 1
            p = self.predict_account(j["description"])
            if not p or p["best_similarity"] < 0.30 or p["share"] < 0.6:
                continue
            if p["shares"].get(j["account"], 0) >= 0.15 or p["account"] == j["account"]:
                continue
            posted, predicted = self.s.coa[j["account"]]["name"], self.s.coa[p["account"]]["name"]
            detail = (f"Description reads as {predicted} ({p['share']:.0%} of similar history coded {p['account']}); "
                      f"posted to {j['account']} {posted}.")
            m = re.search(r"(\d+)\s*x\s", j["description"])
            if m and p["account"] in self.cap_rules:
                units = int(m.group(1))
                unit = j["dr"] / units
                rule = self.cap_rules[p["account"]]
                detail += (f" {units} units at ${unit:,.0f} each meet the ${rule['threshold_per_unit']:,} per-unit "
                           f"capitalisation threshold.")
            flags.append({"type": "MISCODED", "severity": "high" if j["dr"] >= 25_000 else "medium",
                          "je_id": j["je_id"], "line": j["je_line"], "batch": j["batch"], "entity": j["entity"],
                          "account": j["account"], "account_name": posted, "suggested_account": p["account"],
                          "suggested_name": predicted, "cost_centre": j["cost_centre"], "amount": j["dr"],
                          "description": j["description"], "created_by": self._name(j["created_by"]),
                          "approved_by": self._name(j["approved_by"]), "confidence": p["share"],
                          "evidence": p["example"], "detail": detail,
                          "capex_opex": p["account"] in self.cap_rules,
                          # capex booked as opex misstates both the P&L and the balance sheet: rank it first
                          "score": round(p["share"] * min(1, j["dr"] / 20_000) + 0.5
                                         + (0.5 if p["account"] in self.cap_rules else 0), 3)})

        # duplicate accruals posted from two sources
        groups = defaultdict(list)
        for j in lines:
            if j["source"] in JOURNAL_SOURCES and j["category"] == "Accrual" and j["dr"] > 0:
                groups[(j["account"], j["cost_centre"], round(j["dr"], 2))].append(j)
        for (acct, cc, amt), js in groups.items():
            ids = {x["je_id"] for x in js}
            if len(ids) < 2 or amt < 5_000:
                continue
            a, b = js[0], js[1]
            ta, tb = set(tokens(a["description"])), set(tokens(b["description"]))
            overlap = len(ta & tb) / max(1, len(ta | tb))
            if overlap >= 0.5:
                flags.append({"type": "DUPLICATE_ENTRY", "severity": "high", "je_id": b["je_id"], "line": b["je_line"],
                              "duplicate_of": a["je_id"], "batch": b["batch"], "entity": b["entity"], "account": acct,
                              "account_name": self.s.coa[acct]["name"], "cost_centre": cc, "amount": amt,
                              "description": b["description"], "created_by": self._name(b["created_by"]),
                              "approved_by": self._name(b["approved_by"]),
                              "detail": f"Same account, cost centre and amount (${amt:,.2f}) as {a['je_id']} in "
                                        f"\"{a['batch']}\" posted by {self._name(a['created_by'])}; descriptions "
                                        f"{overlap:.0%} identical. Accrued twice from two sources.",
                              "score": 0.95})

        # separation of duties and unusual posting time on manual journals
        seen = set()
        for j in lines:
            if j["source"] != "Manual" or j["je_id"] in seen or not j["approved_by"]:
                continue
            seen.add(j["je_id"])
            created = datetime.fromisoformat(j["created_at"])
            weekend, late = created.weekday() >= 5, created.hour >= 22 or created.hour < 5
            if j["created_by"] == j["approved_by"]:
                when = created.strftime("%a %d %b %H:%M")
                amt = sum(x["dr"] for x in lines if x["je_id"] == j["je_id"])
                flags.append({"type": "SELF_APPROVED", "severity": "high", "je_id": j["je_id"], "line": None,
                              "batch": j["batch"], "entity": j["entity"], "account": j["account"],
                              "account_name": self.s.coa[j["account"]]["name"], "cost_centre": j["cost_centre"],
                              "amount": amt, "description": j["description"],
                              "created_by": self._name(j["created_by"]), "approved_by": self._name(j["approved_by"]),
                              "detail": f"Prepared and approved by the same person ({self._name(j['created_by'])})"
                                        f"{', posted ' + when if weekend or late else ''}"
                                        f"{' (weekend, after hours)' if weekend and late else ''}.",
                              "score": 0.9})
        flags.sort(key=lambda f: -f["score"])
        return {"source": "SEP-26 close journals", "lines_total": len(lines), "lines_scanned": scanned,
                "entries_total": len({j['je_id'] for j in lines}), "flags": flags,
                "ms": round((time.perf_counter() - t) * 1000)}

    # ---------------- AP subledger ----------------
    def scan_ap_ledger(self, since="2026-04-01"):
        t = time.perf_counter()
        groups = defaultdict(list)
        for i, l in enumerate(self.s.lines):
            key = " ".join(w for w in tokens(l["description"]) if "_" not in w)
            groups[(l["vendor_id"], key)].append(i)
        flags, scanned = [], 0
        for (vid, key), idxs in groups.items():
            if len(idxs) < 4:
                continue
            final = Counter(self.s.lines[i]["gl"] for i in idxs)
            norm, n = final.most_common(1)[0]
            if n / len(idxs) < 0.75:
                continue
            for i in idxs:
                l = self.s.lines[i]
                if l["invoice_date"] < since:
                    continue
                scanned += 1
                if l["posted_gl"] != norm and not l["reclassified"]:
                    flags.append({"type": "AP_MISCODE", "severity": "medium" if l["amount_usd"] < 25_000 else "high",
                                  "invoice_id": l["invoice_id"], "invoice_num": l["invoice_num"],
                                  "vendor": l["vendor_name"], "date": l["invoice_date"],
                                  "description": l["description"], "amount": l["amount_usd"],
                                  "account": l["posted_gl"], "account_name": self.s.coa[l["posted_gl"]]["name"],
                                  "suggested_account": norm, "suggested_name": self.s.coa[norm]["name"],
                                  "cost_centre": l["cc"],
                                  "detail": f"{n} of {len(idxs)} lines with this description from {l['vendor_name']} "
                                            f"are coded {norm}; this one is in {l['posted_gl']} and was never "
                                            f"reclassified.",
                                  "score": round(0.6 + min(0.35, l["amount_usd"] / 100_000), 3)})
        flags.sort(key=lambda f: (-f["amount"]))
        return {"source": "AP subledger (Apr–Sep 2026)", "lines_scanned": scanned, "flags": flags,
                "value": round(sum(f["amount"] for f in flags), 2), "ms": round((time.perf_counter() - t) * 1000)}

    # ---------------- cash application ----------------
    def scan_cash(self):
        t = time.perf_counter()
        ar = {a["ar_invoice"]: a for a in self.s.ar_items}
        open_by_amount = defaultdict(list)
        open_by_customer = defaultdict(list)
        for a in self.s.ar_items:
            if a["status"] == "OPEN":
                open_by_amount[round(a["amount"], 2)].append(a)
                open_by_customer[a["customer_id"]].append(a)
        alias_to_customer = {}
        for c in self.s.customers.values():
            for al in c["payer_aliases"]:
                alias_to_customer[al] = c["customer_id"]
        receipts = self.s.receipts
        flags, suggestions = [], []
        status = Counter(r["status"] for r in receipts)
        for r in receipts:
            refs = AR_REF.findall(r["remittance"] or "")
            payer_cust = alias_to_customer.get(r["payer_name"])
            if r["status"] in ("AUTO_APPLIED", "MANUAL_APPLIED"):
                for ref in refs:
                    item = ar.get(ref)
                    if item and r["applied_customer"] and item["customer_id"] != r["applied_customer"]:
                        applied = self.s.customers.get(r["applied_customer"], {})
                        flags.append({"type": "MISAPPLIED", "severity": "high", "receipt_id": r["receipt_id"],
                                      "amount": r["amount"], "currency": r["currency"], "payer": r["payer_name"],
                                      "remittance": r["remittance"], "applied_customer": r["applied_customer"],
                                      "applied_customer_name": applied.get("name"),
                                      "suggested_customer": item["customer_id"],
                                      "suggested_customer_name": item["customer_name"], "suggested_invoice": ref,
                                      "applied_by": self._name(r["applied_by"]),
                                      "detail": f"Remittance references {ref}, an open ${item['open_amount']:,.2f} "
                                                f"invoice of customer {item['customer_id']} {item['customer_name']}"
                                                f"{'; payer ' + r['payer_name'] + ' is that customer' if payer_cust == item['customer_id'] else ''}. "
                                                f"Cash was applied to {r['applied_customer']} {applied.get('name', '')} — "
                                                f"likely transposed customer number.",
                                      "score": 0.99})
                for app in r["applied_invoices"]:
                    item = ar.get(app["ar_invoice"])
                    if item and item.get("closed_by_receipt") and item["closed_by_receipt"] != r["receipt_id"]:
                        flags.append({"type": "DOUBLE_APPLICATION", "severity": "high", "receipt_id": r["receipt_id"],
                                      "amount": r["amount"], "currency": r["currency"], "payer": r["payer_name"],
                                      "remittance": r["remittance"], "applied_customer": r["applied_customer"],
                                      "applied_customer_name": item["customer_name"],
                                      "applied_by": self._name(r["applied_by"]),
                                      "detail": f"Invoice {item['ar_invoice']} was already settled by "
                                                f"{item['closed_by_receipt']}; this ${r['amount']:,.2f} application "
                                                f"creates a credit balance. Likely a second payment or a different "
                                                f"invoice.", "score": 0.95})
                continue
            # exceptions: propose a resolution
            proposal = None
            for ref in refs:
                if ref in ar and ar[ref]["status"] == "OPEN":
                    item = ar[ref]
                    diff = round(r["amount"] - item["open_amount"], 2)
                    proposal = {"ar_invoice": ref, "customer_id": item["customer_id"],
                                "customer_name": item["customer_name"],
                                "basis": "Remittance reference" + (f"; variance {diff:+,.2f}" if diff else ""),
                                "variance": diff}
                    break
            if not proposal and refs:
                for ref in refs:
                    cands = [a for a in self.s.ar_items if a["status"] == "OPEN" and len(a["ar_invoice"]) == len(ref)
                             and abs(a["amount"] - r["amount"]) < 0.01 and Levenshtein.distance(a["ar_invoice"], ref) == 1] \
                        if len(open_by_amount.get(round(r["amount"], 2), [])) else []
                    if cands:
                        a = cands[0]
                        proposal = {"ar_invoice": a["ar_invoice"], "customer_id": a["customer_id"],
                                    "customer_name": a["customer_name"],
                                    "basis": f"Reference {ref} is one digit from open invoice {a['ar_invoice']} with the "
                                             f"exact amount", "variance": 0.0}
                        break
            if not proposal:
                cands = open_by_amount.get(round(r["amount"], 2), [])
                if payer_cust:
                    mine = [a for a in cands if a["customer_id"] == payer_cust]
                    cands = mine or cands
                if len(cands) == 1:
                    a = cands[0]
                    proposal = {"ar_invoice": a["ar_invoice"], "customer_id": a["customer_id"],
                                "customer_name": a["customer_name"],
                                "basis": "Only open item in the ledger with this exact amount"
                                         + (" for this payer" if payer_cust == a["customer_id"] else ""),
                                "variance": 0.0}
            if proposal:
                suggestions.append({"receipt_id": r["receipt_id"], "status": r["status"],
                                    "exception": r["exception_code"] or r["status"], "amount": r["amount"],
                                    "currency": r["currency"], "payer": r["payer_name"],
                                    "remittance": r["remittance"], **proposal,
                                    "highlight": r["status"] == "ON_ACCOUNT" or not r["remittance"]})
        flags.sort(key=lambda f: -f["score"])
        exceptions = sum(1 for r in receipts if r["status"] in ("UNAPPLIED", "ON_ACCOUNT"))
        return {"source": "Cash application 14 Oct 2026", "lines_scanned": len(receipts), "status_counts": status,
                "auto_rate": round(status["AUTO_APPLIED"] / len(receipts), 4), "exceptions": exceptions,
                "flags": flags, "suggestions": suggestions, "ms": round((time.perf_counter() - t) * 1000),
                "value_scanned": round(sum(r["amount"] for r in receipts if r["currency"] == "USD"), 2)}

    def _name(self, pid):
        p = self.s.people.get(pid)
        return p["name"] if p else pid
