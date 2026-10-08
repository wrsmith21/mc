"""Seed data loaded into memory once per process, with the lookups the engine needs."""
import json
import os
from collections import Counter, defaultdict
from functools import cached_property
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = Path(os.environ.get("SEED_DIR", ROOT / "data" / "seed"))
CACHE = Path(os.environ.get("CACHE_DIR", ROOT / "data" / "cache"))


def _load(name):
    return json.loads((SEED / f"{name}.json").read_text())


class Store:
    def __init__(self):
        self.reference = _load("reference")
        self.policies = _load("policies")
        self.people = {p["id"]: p for p in _load("people")}
        self.vendors = {v["vendor_id"]: v for v in _load("vendors")}
        self.history = _load("invoice_history")
        self.pos = _load("purchase_orders")
        self.intake = _load("intake_queue")
        manifest = ROOT / "data" / "pdfs" / "manifest.json"
        if manifest.exists():
            pdfs = json.loads(manifest.read_text())
            for q in self.intake:
                q["pdf"] = pdfs.get(q["intake_id"])
        self.cost_centres = {c["code"]: c for c in self.reference["cost_centres"]}
        self.coa = {a["account"]: a for a in self.reference["chart_of_accounts"]}
        self.matters = {m["matter"]: m for m in self.reference["legal_matters"]}
        self.demo_date = self.reference["demo_date"]
        self.receipt_evidence = _load("receipt_evidence")
        self.contracts = _load("contracts")
        self.letters = {e["engagement_letter"]: e for e in self.contracts["engagement_letters"]}
        self.letters_by_vendor = {e["vendor_id"]: e for e in self.contracts["engagement_letters"]}
        self.matter_budgets = {m["matter"]: m for m in self.contracts["matter_budgets"]}
        self.sows = {s["sow"]: s for s in self.contracts["statements_of_work"]}
        self.entities = {e["code"]: e for e in self.reference["entities"]}

        self.history_by_vendor = defaultdict(list)
        self.lines = []  # flattened history lines with invoice context, final (corrected) coding
        for inv in self.history:
            self.history_by_vendor[inv["vendor_id"]].append(inv)
            for l in inv["lines"]:
                if l.get("line_type") == "TAX":
                    continue
                self.lines.append({
                    "invoice_id": inv["invoice_id"], "vendor_id": inv["vendor_id"], "vendor_name": inv["vendor_name"],
                    "invoice_num": inv["invoice_num"], "invoice_date": inv["invoice_date"],
                    "category": inv["category"], "entity": inv["entity"], "description": l["description"],
                    "qty": l["qty"], "unit_price": l["unit_price"], "amount_usd": l["amount_usd"],
                    "gl": l["corrected_gl"] or l["gl"], "posted_gl": l["gl"], "cc": l["cc"],
                    "reclassified": l["coding"] == "RECLASSIFIED", "reclass_date": l["reclass_date"],
                    "requester_id": inv["requester_id"],
                    "approver_ids": [a["approver_id"] for a in inv["approval_chain"]],
                    "po_number": inv["po_number"], "amortise_to": l.get("amortise_to"),
                })
        self.lines_by_vendor = defaultdict(list)
        for i, l in enumerate(self.lines):
            self.lines_by_vendor[l["vendor_id"]].append(i)
        self.open_pos = [p for p in self.pos if p["status"] != "CLOSED"]
        self.open_pos_by_vendor = defaultdict(list)
        for p in self.open_pos:
            self.open_pos_by_vendor[p["vendor_id"]].append(p)

    @cached_property
    def journals(self):
        return _load("journals_sep26")

    @cached_property
    def receipts(self):
        return _load("cash_receipts_20261014")

    @cached_property
    def ar_items(self):
        return _load("ar_open_items")

    @cached_property
    def customers(self):
        return {c["customer_id"]: c for c in _load("customers")}

    def person(self, pid):
        return self.people.get(pid)

    def person_brief(self, pid):
        p = self.people.get(pid)
        if not p:
            return None
        return {"id": p["id"], "name": p["name"], "title": p["title"], "level": p["level"],
                "cost_centre": p["cost_centre"], "approval_limit": p["approval_limit"],
                "out_of_office": p.get("out_of_office")}

    def vendor_stats(self, vendor_id):
        invs = self.history_by_vendor.get(vendor_id, [])
        totals = sorted(i["total_usd"] for i in invs)
        gls = Counter(self.lines[i]["gl"] for i in self.lines_by_vendor.get(vendor_id, []))
        return {"invoices": len(invs), "median_usd": totals[len(totals) // 2] if totals else None,
                "gl_mix": gls.most_common(), "po_backed": sum(1 for i in invs if i["po_number"])}


_store = None


def get_store() -> Store:
    global _store
    if _store is None:
        _store = Store()
    return _store
