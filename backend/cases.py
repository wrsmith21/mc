"""Anomaly findings as cases a controller can work: an owner, an SLA, a drafted fix, preparer-then-approver sign-off
with separation of duties, and an export to the ledger. Decisions feed back into the engine.

Status flow: Open → Pending approval → Approved → Exported, or Dismissed with a reason. A returned case goes back
to Open. The agent drafts every fix; it never prepares, approves or posts one.
"""
import csv
import hashlib
import io
import re
from datetime import date, datetime, timedelta

from . import clock
from .engine.exports import GL_COLS
from .state import now_iso

TYPE_LABEL = {"MISCODED": "Journal posted to the wrong account", "DUPLICATE_ENTRY": "Accrued twice",
              "SELF_APPROVED": "Prepared and approved by the same person",
              "AP_MISCODE": "Miscoded invoice still in the ledger", "MISAPPLIED": "Cash applied to the wrong customer",
              "DOUBLE_APPLICATION": "Applied to an invoice already paid", "UNAPPLIED_MATCH": "Unapplied receipt with a match"}
SOURCE = {"MISCODED": "journals", "DUPLICATE_ENTRY": "journals", "SELF_APPROVED": "journals",
          "AP_MISCODE": "ap_ledger", "MISAPPLIED": "cash", "DOUBLE_APPLICATION": "cash", "UNAPPLIED_MATCH": "cash"}
# Who prepares and who approves, by source. The approver must differ from the preparer and the original poster.
OWNERS = {"journals": ("E35123", "E30233"), "ap_ledger": ("E35123", "E30233"), "cash": ("E35053", "E30719")}
MATCH_CONFIDENCE = {("INVALID_REFERENCE", True): 0.97, ("UNKNOWN_PAYER", True): 0.93, ("ON_ACCOUNT", True): 0.85,
                    ("UNAPPLIED_NO_REMITTANCE", True): 0.88, ("FX_DIFFERENCE", False): 0.9,
                    ("OVER_PAY", False): 0.82, ("SHORT_PAY", False): 0.8}
DISMISS_REASONS = {"valid_as_posted": "Valid as posted", "already_corrected": "Already corrected",
                   "below_materiality": "Below materiality", "false_positive": "False positive"}
SLA_BUSINESS_DAYS = {"journals": 3, "ap_ledger": 5, "cash": 1}


def _id(prefix, *parts):
    return f"{prefix}-" + hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:8].upper()


def _desc_key(desc):
    return re.sub(r"[^a-z ]", "", (desc or "").lower()).strip()[:60]


class Cases:
    def __init__(self, svc):
        self.svc = svc
        self.s = svc.s

    # ---------- building cases from the sweep ----------
    def _from_flag(self, f, source):
        t = f["type"]
        if source == "journals":
            cid = _id("JR", f["je_id"], f.get("line"), t)
            ref = f["je_id"] + (f" line {f['line']}" if f.get("line") else "")
        elif source == "ap_ledger":
            cid = _id("AP", f["invoice_id"], f["description"])
            ref = f"{f['vendor']} invoice {f['invoice_num']}"
        else:
            cid = _id("CA", f["receipt_id"], t)
            ref = f["receipt_id"]
        return {"case_id": cid, "type": t, "type_label": TYPE_LABEL[t], "source": source, "reference": ref,
                "amount": f["amount"], "currency": f.get("currency", "USD"), "entity": f.get("entity", "US01"),
                "detail": f["detail"], "finding": f, "severity": f.get("severity", "medium"),
                "confidence": f.get("confidence"), "created_at": f"{self.s.demo_date}T06:30:00"}

    def _base(self):
        a = self.svc.anomalies()
        out = [self._from_flag(f, "journals") for f in a["journals"]["flags"]]
        out += [self._from_flag(f, "ap_ledger") for f in a["ap_ledger"]["flags"]]
        out += [self._from_flag(f, "cash") for f in a["cash"]["flags"]]
        for m in a["cash"]["suggestions"]:
            f = {**m, "type": "UNAPPLIED_MATCH", "severity": "medium",
                 "detail": f"{m['basis']}. Proposed: apply to {m['ar_invoice']} ({m['customer_id']} "
                           f"{m['customer_name']}).",
                 "confidence": MATCH_CONFIDENCE.get((m["exception"], m["variance"] == 0), 0.8)}
            out.append(self._from_flag(f, "cash"))
        return out

    def _suppressed(self, case):
        f = case["finding"]
        if case["source"] == "ap_ledger":
            key = f"suppress:{f['vendor']}|{f['account']}|{_desc_key(f['description'])}"
        elif case["source"] == "journals" and f.get("account"):
            key = f"suppress:{f.get('account')}|{_desc_key(f['description'])}"
        else:
            return None
        return self.svc.state.get(key)

    def _business_days_after(self, start, n):
        holidays = set(self.s.reference["close_calendar"]["holidays"])
        d = date.fromisoformat(start[:10])
        while n:
            d += timedelta(days=1)
            if d.weekday() < 5 and d.isoformat() not in holidays:
                n -= 1
        return d.isoformat()

    def _merge(self, case, overlays):
        st = overlays.get(f"case:{case['case_id']}") or {}
        preparer, approver = OWNERS[case["source"]]
        out = {**case, "status": "Open", "owner": preparer, "approver_role": approver, "preparer": None,
               "approver": None, "decision_log": [], **st}
        out["owner_name"] = self.s.people[out["owner"]]["name"]
        out["sla_due"] = self._business_days_after(case["created_at"], SLA_BUSINESS_DAYS[case["source"]])
        out["overdue"] = out["status"] in ("Open", "Pending approval") and clock.today() > out["sla_due"]
        out["fix"] = out.get("fix") or self.draft_fix(out)
        return out

    def all(self, include_suppressed=False):
        overlays = self.svc.state.prefix("case:")
        out = []
        for c in self._base():
            m = self._merge(c, overlays)
            sup = self._suppressed(c)
            if sup and m["status"] == "Open":
                if not include_suppressed:
                    continue
                m["suppressed_by"] = sup
            out.append(m)
        return out

    def get(self, case_id):
        c = next((c for c in self.all(include_suppressed=True) if c["case_id"] == case_id), None)
        if not c:
            raise KeyError(case_id)
        c["audit"] = self.svc.audit(case_id)
        return c

    # ---------- the agent's drafted fix ----------
    def draft_fix(self, c):
        f = c["finding"]
        t = c["type"]
        if t in ("MISCODED", "AP_MISCODE"):
            ref = f.get("je_id") or f"{f['vendor']} {f['invoice_num']}"
            return {"kind": "reclass", "period": "OCT-26", "accounting_date": clock.today(),
                    "lines": [{"account": f["suggested_account"], "cost_centre": f["cost_centre"], "dr": f["amount"],
                               "cr": 0, "description": f"Reclass {ref} to {f['suggested_account']}"},
                              {"account": f["account"], "cost_centre": f["cost_centre"], "dr": 0, "cr": f["amount"],
                               "description": f"Reclass {ref} from {f['account']}"}],
                    "note": "September is closed: the correction posts in October with a prior-period reference."}
        if t == "DUPLICATE_ENTRY":
            return {"kind": "reversal", "period": "OCT-26", "accounting_date": clock.today(),
                    "lines": [{"account": "2150", "cost_centre": "CC7150", "dr": f["amount"], "cr": 0,
                               "description": f"Reverse duplicate accrual {f['je_id']}"},
                              {"account": f["account"], "cost_centre": f["cost_centre"], "dr": 0, "cr": f["amount"],
                               "description": f"Reverse duplicate accrual {f['je_id']}"}],
                    "note": f"Keeps {f.get('duplicate_of')}; reverses the second posting."}
        if t == "SELF_APPROVED":
            return {"kind": "review", "lines": [],
                    "note": "Retrospective review of the entry by a second approver; escalate to the SOX control "
                            "owner if support is missing."}
        if t == "MISAPPLIED":
            return {"kind": "reapply", "lines": [
                {"action": "UNAPPLY", "receipt": f["receipt_id"], "customer": f["applied_customer"],
                 "invoice": None, "amount": f["amount"]},
                {"action": "APPLY", "receipt": f["receipt_id"], "customer": f["suggested_customer"],
                 "invoice": f["suggested_invoice"], "amount": f["amount"]}],
                "note": "Moves the cash to the customer named in the remittance."}
        if t == "DOUBLE_APPLICATION":
            return {"kind": "reapply", "lines": [
                {"action": "UNAPPLY", "receipt": f["receipt_id"], "customer": f["applied_customer"],
                 "invoice": None, "amount": f["amount"]},
                {"action": "ON_ACCOUNT", "receipt": f["receipt_id"], "customer": f["applied_customer"],
                 "invoice": None, "amount": f["amount"]}],
                "note": "Holds the cash on account until the customer says what it pays."}
        if t == "UNAPPLIED_MATCH":
            return {"kind": "apply", "lines": [
                {"action": "APPLY", "receipt": f["receipt_id"], "customer": f["customer_id"],
                 "invoice": f["ar_invoice"], "amount": f["amount"]}],
                "note": f"Variance {f.get('variance', 0):,.2f} to the standard adjustment activity."
                if f.get("variance") else "Exact amount."}
        return {"kind": "none", "lines": []}

    # ---------- actions ----------
    def _save(self, c, actor, kind, payload):
        keep = {k: c[k] for k in ("status", "owner", "preparer", "approver", "fix", "decision_log", "export_batch",
                                  "dismissed") if k in c}
        self.svc.state.put(f"case:{c['case_id']}", keep)
        self.svc.state.add_event(c["case_id"], actor, kind, payload)

    def _log(self, c, actor, action, note=""):
        c["decision_log"] = c["decision_log"] + [{"by": actor, "by_name": self.s.people[actor]["name"],
                                                  "action": action, "note": note, "at": now_iso()}]

    def prepare(self, case_id, by, note="", account=None):
        c = self.get(case_id)
        if c["status"] != "Open":
            raise ValueError(f"Case is {c['status'].lower()}, not open")
        original = c["finding"].get("created_by") or c["finding"].get("applied_by")
        if original and original == self.s.people[by]["name"]:
            raise PermissionError(f"{original} posted the original entry and cannot prepare its correction")
        if account and c["fix"]["kind"] == "reclass":
            c["fix"]["lines"][0]["account"] = account
        c.update(status="Pending approval", preparer=by)
        self._log(c, by, "Prepared", note)
        self._save(c, by, "CASE_PREPARED", {"fix": c["fix"]["kind"], "note": note})
        return self.get(case_id)

    def approve(self, case_id, by, note=""):
        c = self.get(case_id)
        if c["status"] != "Pending approval":
            raise ValueError("Only a prepared case can be approved")
        names = {c["preparer"]: "prepared this correction"}
        original = c["finding"].get("created_by") or c["finding"].get("applied_by")
        if by in names or self.s.people[by]["name"] == original:
            why = names.get(by) or "posted the original entry"
            raise PermissionError(f"{self.s.people[by]['name']} {why}: separation of duties requires another approver")
        c.update(status="Approved", approver=by)
        self._log(c, by, "Approved", note)
        self._save(c, by, "CASE_APPROVED", {"note": note})
        self._feedback(c, by)
        return self.get(case_id)

    def send_back(self, case_id, by, reason):
        c = self.get(case_id)
        if c["status"] != "Pending approval":
            raise ValueError("Only a prepared case can be sent back")
        c.update(status="Open", preparer=None)
        self._log(c, by, "Sent back", reason)
        self._save(c, by, "CASE_SENT_BACK", {"reason": reason})
        return self.get(case_id)

    def dismiss(self, case_id, by, reason, note=""):
        if reason not in DISMISS_REASONS:
            raise ValueError("Unknown dismissal reason")
        c = self.get(case_id)
        if c["status"] not in ("Open", "Pending approval"):
            raise ValueError(f"Case is {c['status'].lower()}")
        c.update(status="Dismissed", dismissed={"reason": reason, "label": DISMISS_REASONS[reason], "note": note})
        self._log(c, by, f"Dismissed: {DISMISS_REASONS[reason]}", note)
        self._save(c, by, "CASE_DISMISSED", {"reason": reason, "note": note})
        if reason == "valid_as_posted":
            f = c["finding"]
            key = (f"suppress:{f['vendor']}|{f['account']}|{_desc_key(f['description'])}" if c["source"] == "ap_ledger"
                   else f"suppress:{f.get('account')}|{_desc_key(f['description'])}")
            self.svc.state.put(key, {"case_id": case_id, "by": by, "at": now_iso(), "note": note})
        return self.get(case_id)

    def bulk_prepare(self, by, min_confidence=0.95):
        done = []
        for c in self.all():
            if c["type"] == "UNAPPLIED_MATCH" and c["status"] == "Open" and (c["confidence"] or 0) >= min_confidence:
                self.prepare(c["case_id"], by, f"Bulk: match confidence {c['confidence']:.0%}")
                done.append(c["case_id"])
        return {"prepared": done}

    def _feedback(self, c, by):
        """An approved correction becomes history the coding engine learns from."""
        f = c["finding"]
        if c["type"] == "AP_MISCODE":
            vid = next((v["vendor_id"] for v in self.s.vendors.values() if v["name"] == f["vendor"]), None)
            if vid:
                key = re.sub(r"\(\d+\)", "", f["description"].lower()).strip()
                self.svc.state.put(f"learned:{vid}:{key}", {
                    "description_key": key.split(" – ")[0], "account": c["fix"]["lines"][0]["account"],
                    "cost_centre": f["cost_centre"], "reason": f"Reclass approved in case {c['case_id']}",
                    "by": self.s.people[by]["name"], "at": now_iso(), "source_invoice": f["invoice_num"]})
                self.svc.state.add_event(c["case_id"], "AGENT", "HISTORY_UPDATED", {
                    "lesson": f"Future '{f['description']}' lines from {f['vendor']} will recommend "
                              f"{c['fix']['lines'][0]['account']}"})

    # ---------- export to the ledger ----------
    def export(self, kind, by):
        cases = [c for c in self.all() if c["status"] == "Approved" and
                 (c["source"] in ("journals", "ap_ledger") if kind == "gl" else c["source"] == "cash")
                 and c["fix"]["lines"]]
        if not cases:
            raise ValueError("Nothing approved to export")
        batch = f"{'GLCORR' if kind == 'gl' else 'CASHREAPP'}-{clock.today().replace('-', '')}-" \
                f"{len(self.svc.state.prefix('batch:')) + 1:02d}"
        if kind == "gl":
            dr = round(sum(l["dr"] for c in cases for l in c["fix"]["lines"]), 2)
            cr = round(sum(l["cr"] for c in cases for l in c["fix"]["lines"]), 2)
            if abs(dr - cr) > 0.005:
                raise ValueError(f"Batch does not balance: debits {dr:,.2f}, credits {cr:,.2f}")
            text = self._gl_csv(cases, batch)
            totals = {"debits": dr, "credits": cr, "lines": sum(len(c["fix"]["lines"]) for c in cases)}
        else:
            text = self._cash_csv(cases, batch)
            totals = {"amount": round(sum(c["amount"] for c in cases), 2),
                      "lines": sum(len(c["fix"]["lines"]) for c in cases)}
        for c in cases:
            c.update(status="Exported", export_batch=batch)
            self._log(c, by, f"Exported in {batch}")
            self._save(c, by, "CASE_EXPORTED", {"batch": batch})
        meta = {"batch": batch, "kind": kind, "cases": [c["case_id"] for c in cases], "totals": totals,
                "by": by, "at": now_iso()}
        self.svc.state.put(f"batch:{batch}", {**meta, "csv": text})
        return meta

    def batch_csv(self, batch):
        b = self.svc.state.get(f"batch:{batch}")
        if not b:
            raise KeyError(batch)
        return b["csv"]

    def _gl_csv(self, cases, batch):
        ents = {e["code"]: e for e in self.s.reference["entities"]}
        rows = []
        for c in cases:
            ent = c["entity"]
            for l in c["fix"]["lines"]:
                rows.append({"STATUS": "NEW", "LEDGER_ID": ents[ent]["ledger_id"],
                             "ACCOUNTING_DATE": c["fix"]["accounting_date"], "CURRENCY_CODE": "USD",
                             "DATE_CREATED": clock.today(), "CREATED_BY": "ANOMALY_LAYER", "ACTUAL_FLAG": "A",
                             "USER_JE_CATEGORY_NAME": "Reclass" if c["fix"]["kind"] == "reclass" else "Adjustment",
                             "USER_JE_SOURCE_NAME": "Spreadsheet", "SEGMENT1": ent,
                             "SEGMENT2": l["cost_centre"].replace("CC", ""), "SEGMENT3": l["account"],
                             "SEGMENT4": "000", "SEGMENT5": "000", "SEGMENT6": "000",
                             "ENTERED_DR": f"{l['dr']:.2f}" if l["dr"] else "",
                             "ENTERED_CR": f"{l['cr']:.2f}" if l["cr"] else "",
                             "REFERENCE1": f"Anomaly layer corrections {batch}", "REFERENCE4": c["case_id"],
                             "REFERENCE10": l["description"][:240], "GROUP_ID": batch})
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=GL_COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
        return buf.getvalue()

    def _cash_csv(self, cases, batch):
        cols = ["BATCH", "CASE_ID", "RECEIPT_NUMBER", "ACTION", "CUSTOMER_NUMBER", "TRX_NUMBER", "AMOUNT",
                "CURRENCY", "APPLY_DATE", "REASON"]
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=cols)
        w.writeheader()
        for c in cases:
            for l in c["fix"]["lines"]:
                w.writerow({"BATCH": batch, "CASE_ID": c["case_id"], "RECEIPT_NUMBER": l["receipt"],
                            "ACTION": l["action"], "CUSTOMER_NUMBER": l["customer"], "TRX_NUMBER": l["invoice"] or "",
                            "AMOUNT": f"{l['amount']:.2f}", "CURRENCY": c["currency"], "APPLY_DATE": clock.today(),
                            "REASON": c["type_label"]})
        return buf.getvalue()

    # ---------- the controller's view ----------
    def dashboard(self):
        cases = self.all()
        hidden = len(self.all(include_suppressed=True)) - len(cases)
        by_source = {}
        for src in ("journals", "ap_ledger", "cash"):
            cs = [c for c in cases if c["source"] == src]
            open_ = [c for c in cs if c["status"] in ("Open", "Pending approval")]
            by_source[src] = {"total": len(cs), "open": len(open_),
                              "value_at_risk": round(sum(c["amount"] for c in open_), 2),
                              "pending_approval": sum(1 for c in cs if c["status"] == "Pending approval"),
                              "approved": sum(1 for c in cs if c["status"] == "Approved"),
                              "exported": sum(1 for c in cs if c["status"] == "Exported"),
                              "dismissed": sum(1 for c in cs if c["status"] == "Dismissed"),
                              "overdue": sum(1 for c in open_ if c["overdue"])}
        owners = {}
        for c in cases:
            if c["status"] in ("Open", "Pending approval"):
                who = c["owner_name"] if c["status"] == "Open" else self.s.people[c["approver_role"]]["name"]
                owners[who] = owners.get(who, 0) + 1
        batches = [{k: v for k, v in b.items() if k != "csv"} for b in self.svc.state.prefix("batch:").values()]
        return {"by_source": by_source, "workload": owners, "suppressed": hidden, "batches": batches,
                "period": "OCT-26 open · SEP-26 closed 7 Oct", "now": clock.now_iso()}
