"""Demo service: queue, live runs, human decisions, audit trail, KPIs, anomaly layer, exports."""
import json
import re
import time
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from .engine import exports
from .engine.anomaly import AnomalyLayer
from .engine.pipeline import STATUS_LABEL, Agent
from .state import BufferedState, get_state, now_iso
from .store import CACHE, get_store

STATUS_LABEL = {**STATUS_LABEL, "IN_APPROVAL": "In approval"}
NOT_APPROVABLE = {"HELD", "MATCH_TO_PO", "VENDOR_ONBOARDING", "AWAITING_CONFIRMATION"}
LIVE_DAY = "2026-10-14"  # invoices received from this day on are still open at the start of the demo

# Storyboard state at the start of the demo: which receipts are already confirmed, and by whom/when.
STORYBOARD_RECEIPTS = {
    "dell": ("2026-10-08T15:20", "Delivery received at Building 2 Dock B; serials scanned into asset register."),
    "saas": ("2026-10-09T16:45", "Renewal order form OF-2026-114 signed; service continuing."),
    "sod": ("2026-10-13T17:30", "Workshop delivered 22–23 Sep; outputs received."),
    "po_breach_marketing": ("2026-10-09T15:05", "Q4 creative delivered and in market."),
    "learning_1": ("2026-10-13T18:40", "Chargers received by IT End-User Services."),
    "learning_2": ("2026-10-14T09:10", "Chargers received by IT End-User Services."),
}


def _spread(intake_id, n):
    return int(re.sub(r"\D", "", intake_id) or 0) * 7 % n


def _key(desc):
    return re.sub(r"\(\d+\)", "", desc.lower()).strip()


class DemoService:
    def __init__(self):
        self.s = get_store()
        self.state = get_state()
        self.agent = Agent(self.s, self.state)
        self.anomaly_layer = AnomalyLayer(self.s, self.agent.rec)
        self.items = {q["intake_id"]: q for q in self.s.intake}
        self.by_key = {q["storyboard_key"]: q["intake_id"] for q in self.s.intake if q.get("storyboard_key")}
        self.base = self._load_base()
        self._anomaly = None
        if not self.state.get("meta:seeded"):
            self.reset()

    # ---------- base results ----------
    def _load_base(self):
        path = CACHE / "agent_results.json"
        if path.exists():
            return json.loads(path.read_text())
        return {iid: self.agent.process(item) for iid, item in self.items.items()}

    def all_items(self):
        items = dict(self.items)
        for k, w in self.state.prefix("wildcard:").items():
            items[w["intake_id"]] = w
        return items

    def result(self, intake_id, live=False):
        item = self.all_items()[intake_id]
        r = self.agent.process(item, live=live)
        self.base[intake_id] = r
        return self._overlay(r)

    def _overlay(self, r, decisions=None, receipts=None):
        iid = r["intake_id"]
        decision = (decisions or {}).get(f"decision:{iid}") if decisions is not None else self.state.get(f"decision:{iid}")
        task = (receipts or {}).get(f"receipt:{iid}") if receipts is not None else self.state.get(f"receipt:{iid}")
        status = r["agent_status"]
        if status == "AWAITING_CONFIRMATION" and task and task.get("status") == "confirmed":
            status = r.get("status_after_receipt", "RECOMMENDED")
        if decision:
            status = decision["status"]
        out = dict(r)
        out["status"], out["status_label"] = status, STATUS_LABEL.get(status, status.title())
        out["decision"], out["receipt_task"] = decision, task
        return out

    # ---------- queue & summary ----------
    def queue(self):
        decisions = self.state.prefix("decision:")
        receipts = self.state.prefix("receipt:")
        rows = []
        items = self.all_items()
        for iid in items:
            r = self.base.get(iid) or self.agent.process(items[iid])
            self.base[iid] = r
            o = self._overlay(r, decisions, receipts)
            c = o.get("coding") or {}
            rows.append({"intake_id": iid, "received_at": o["received_at"], "channel": o["channel"],
                         "vendor": (o.get("vendor") or {}).get("name") or o["document"].get("vendor_name"),
                         "vendor_id": (o.get("vendor") or {}).get("vendor_id"),
                         "invoice_num": o["document"].get("invoice_num"), "currency": o["document"]["currency"],
                         "total": o["document"]["total"], "total_usd": o["total_usd"], "entity": o["document"]["entity"],
                         "status": o["status"], "status_label": o["status_label"], "agent_status": o["agent_status"],
                         "account": c.get("account"), "account_name": c.get("account_name"),
                         "cost_centre": c.get("cost_centre"), "confidence": c.get("confidence"),
                         "band": c.get("band"), "flags": [{"code": f["code"], "severity": f["severity"],
                                                           "title": f["title"]} for f in o["flags"]],
                         "storyboard_key": o.get("storyboard_key"), "scene": o.get("scene"),
                         "pdf": bool(o.get("pdf")), "wildcard": iid.startswith("WC-")})
        rows.sort(key=lambda x: x["received_at"], reverse=True)
        return rows

    def summary(self):
        rows = self.queue()
        decisions = self.state.prefix("decision:")
        approved = [d for d in decisions.values() if d["status"] == "APPROVED"]
        touchless = [d for d in approved if not d.get("override")]
        by_status = Counter(r["status"] for r in rows)
        agent_status = Counter(r["agent_status"] for r in rows)
        base = sum(self.base[r["intake_id"]]["minutes"]["baseline"] for r in rows)
        agent = sum(self.base[r["intake_id"]]["minutes"]["agent"] for r in rows)
        held = [r for r in rows if r["status"] in ("HELD", "VENDOR_ONBOARDING")]
        prevented = [r for r in rows if (self.base[r["intake_id"]].get("coding") or {}).get("default_contrast")]
        breaches = [r for r in rows if any(f["code"] == "PO_POLICY" for f in r["flags"])]
        cycle = []
        for iid, d in decisions.items():
            if d["status"] == "APPROVED" and d.get("approvals"):
                rec = self.base.get(iid.split(":", 1)[1])
                if rec:
                    t0 = datetime.fromisoformat(rec["received_at"])
                    t1 = datetime.fromisoformat(d["approvals"][-1]["at"][:16])
                    cycle.append((t1 - t0).total_seconds() / 86400)
        return {
            "processed": len(rows), "by_status": by_status, "agent_status": agent_status,
            "fast_tracked": agent_status["FAST_TRACK"], "held": len(held),
            "held_value_usd": round(sum(r["total_usd"] for r in held), 2),
            "approved": len(approved), "touchless": len(touchless),
            "touchless_rate": round(len(touchless) / len(approved), 3) if approved else None,
            "miscodings_prevented": len(prevented),
            "miscodings_prevented_value": round(sum(r["total_usd"] for r in prevented), 2),
            "po_policy_breaches": len(breaches), "po_breach_value": round(sum(r["total_usd"] for r in breaches), 2),
            "open_po_matches": agent_status["MATCH_TO_PO"],
            "awaiting_confirmation": by_status["AWAITING_CONFIRMATION"],
            "hours_saved": round((base - agent) / 60, 1), "baseline_hours": round(base / 60, 1),
            "avg_cycle_days": round(sum(cycle) / len(cycle), 1) if cycle else None, "baseline_cycle_days": 6.5,
            "value_in_queue_usd": round(sum(r["total_usd"] for r in rows), 2),
            "history": {"invoices": len(self.s.history), "lines": len(self.s.lines), "vendors": len(self.s.vendors),
                        "people": len(self.s.people), "pos": len(self.s.pos), "journals": len(self.s.journals),
                        "receipts": len(self.s.receipts)},
        }

    # ---------- live run (SSE) ----------
    def run_events(self, intake_id, pace=1.0, actor="E34120"):
        item = self.all_items()[intake_id]
        yield {"type": "start", "intake_id": intake_id, "steps": ["intake", "read", "supplier", "validity", "po",
                                                                   "coding", "treatment", "receipt", "risk", "approval"]}
        yield {"type": "stage", "key": "read", "status": "running",
               "label": "Reading the invoice" + (" with Claude" if item.get("pdf") else "")}
        t = time.time()
        r = self.agent.process(item, live=True)
        self.base[intake_id] = r
        elapsed = time.time() - t
        delays = {"intake": 0.35, "read": 0.9, "supplier": 0.8, "validity": 0.8, "po": 0.6, "coding": 1.3,
                  "treatment": 0.7, "receipt": 0.8, "risk": 0.8, "approval": 0.8}
        for step in r["trace"]:
            d = delays.get(step["key"], 0.5) * pace
            if step["key"] == "read":
                d = max(0.0, d - elapsed)
            time.sleep(d)
            yield {"type": "step", **step}
        self._log_run(r, actor)
        time.sleep(0.3 * pace)
        yield {"type": "result", "result": self._overlay(r)}

    def _log_run(self, r, actor, ts=None):
        iid = r["intake_id"]
        ex = r["extraction"]
        self.state.add_event(iid, "AGENT", "EXTRACTED", {
            "source": ex.get("source"), "model": ex.get("model"), "latency_ms": ex.get("latency_ms"),
            "fields": {k: r["document"].get(k) for k in ("vendor_name", "invoice_num", "invoice_date", "currency",
                                                          "total")}}, ts)
        if r.get("coding"):
            c = r["coding"]
            self.state.add_event(iid, "AGENT", "RECOMMENDED", {
                "account": c["account"], "account_name": c["account_name"], "cost_centre": c["cost_centre"],
                "confidence": c["confidence"], "band": c["band"], "reason": r["explanation"],
                "evidence": [e["invoice_num"] for e in c["lines"][0]["rec"]["evidence"]],
                "vendor_default": (c.get("default_contrast") or {}).get("vendor_default")}, ts)
        for f in r["flags"]:
            self.state.add_event(iid, "AGENT", "FLAGGED", {"code": f["code"], "title": f["title"],
                                                           "detail": f["detail"], "severity": f["severity"]}, ts)
        if r.get("approval"):
            self.state.add_event(iid, "AGENT", "ROUTED", {
                "chain": [f"{s['person']['name']} ({s['role_label']})" for s in r["approval"]["steps"]],
                "tier": r["approval"]["tier"], "sod": r["approval"]["sod_reroute"]}, ts)

    # ---------- receipt confirmation ----------
    def request_receipt(self, intake_id, actor="AGENT", ts=None):
        r = self.base.get(intake_id) or self.result(intake_id)
        person = (r.get("requester") or {}).get("person")
        if not person:
            raise ValueError("No requester identified")
        task = self.state.get(f"receipt:{intake_id}")
        if task:
            return task
        task = {"intake_id": intake_id, "status": "pending", "assignee_id": person["id"],
                "assignee_name": person["name"], "requested_at": ts or now_iso(),
                "vendor": r["vendor"]["name"], "invoice_num": r["document"]["invoice_num"],
                "amount": r["document"]["total"], "currency": r["document"]["currency"],
                "description": r["document"]["lines"][0]["description"],
                "evidence": r["requester"]["evidence"], "source": r["requester"]["source"]}
        self.state.put(f"receipt:{intake_id}", task)
        self.state.add_event(intake_id, actor, "RECEIPT_REQUESTED",
                             {"to": person["name"], "why": r["receipt"]["detail"]}, ts)
        return task

    def confirm_receipt(self, intake_id, by_id, note="", ts=None):
        task = self.state.get(f"receipt:{intake_id}") or self.request_receipt(intake_id, ts=ts)
        person = self.s.people[by_id]
        task.update(status="confirmed", confirmed_by=by_id, confirmed_by_name=person["name"],
                    confirmed_at=ts or now_iso(), note=note)
        self.state.put(f"receipt:{intake_id}", task)
        self.state.add_event(intake_id, by_id, "RECEIPT_CONFIRMED", {"by": person["name"], "note": note}, ts)
        return task

    def tasks(self, person_id=None):
        out = [t for t in self.state.prefix("receipt:").values() if t["status"] == "pending"]
        if person_id:
            out = [t for t in out if t["assignee_id"] == person_id]
        return sorted(out, key=lambda t: t["requested_at"], reverse=True)

    # ---------- human decisions ----------
    def _current(self, intake_id, seeding):
        return self._overlay(self.base[intake_id]) if seeding else self.result(intake_id)

    def submit(self, intake_id, action, actor, reason=None, override=None, ts=None):
        seeding = ts is not None
        r = self._current(intake_id, seeding)
        if action in ("accept", "override") and r["status"] in NOT_APPROVABLE:
            raise ValueError(f"Cannot submit for approval while {r['status_label'].lower()}")
        if action in ("override", "reject") and not reason:
            raise ValueError("A reason is required")
        chain = [s["person"]["id"] for s in r["approval"]["steps"]] if r.get("approval") else []
        if action == "reject":
            decision = {"status": "REJECTED", "by": actor, "at": ts or now_iso(), "reason": reason, "chain": chain,
                        "approvals": []}
            self.state.put(f"decision:{intake_id}", decision)
            self.state.add_event(intake_id, actor, "REJECTED", {"reason": reason}, ts)
            return None if seeding else self.result(intake_id)
        decision = {"status": "IN_APPROVAL", "by": actor, "at": ts or now_iso(), "reason": reason,
                    "override": None, "chain": chain, "approvals": []}
        if action == "override":
            c = r["coding"]
            decision["override"] = {"from_account": c["account"], "from_cost_centre": c["cost_centre"],
                                    "account": override.get("account") or c["account"],
                                    "cost_centre": override.get("cost_centre") or c["cost_centre"]}
            self.state.add_event(intake_id, actor, "CODING_OVERRIDDEN", {**decision["override"], "reason": reason}, ts)
            vid = r["vendor"]["vendor_id"]
            for lr in c["lines"]:
                k = _key(lr["description"])
                self.state.put(f"learned:{vid}:{k}", {
                    "description_key": k, "account": decision["override"]["account"],
                    "cost_centre": decision["override"]["cost_centre"], "reason": reason,
                    "by": self.s.people[actor]["name"] if actor in self.s.people else actor,
                    "at": ts or now_iso(), "source_invoice": r["document"]["invoice_num"]})
            self.state.add_event(intake_id, "AGENT", "HISTORY_UPDATED", {
                "lesson": f"Future '{c['lines'][0]['description']}' lines from {r['vendor']['name']} will recommend "
                          f"{decision['override']['account']} / {decision['override']['cost_centre']}"}, ts)
        else:
            self.state.add_event(intake_id, actor, "ACCEPTED", {"account": r["coding"]["account"],
                                                                "cost_centre": r["coding"]["cost_centre"]}, ts)
        self.state.put(f"decision:{intake_id}", decision)
        self.state.add_event(intake_id, actor, "SUBMITTED_FOR_APPROVAL",
                             {"chain": [self.s.people[p]["name"] for p in chain]}, ts)
        return None if seeding else self.result(intake_id)

    def approve_step(self, intake_id, approver_id, ts=None):
        decision = self.state.get(f"decision:{intake_id}")
        if not decision or decision["status"] != "IN_APPROVAL":
            raise ValueError("Not awaiting approval")
        nxt = decision["chain"][len(decision["approvals"])]
        if approver_id != nxt:
            raise ValueError(f"Next approver is {self.s.people[nxt]['name']}")
        decision["approvals"].append({"person_id": approver_id, "name": self.s.people[approver_id]["name"],
                                      "at": ts or now_iso()})
        if len(decision["approvals"]) == len(decision["chain"]):
            decision["status"] = "APPROVED"
        self.state.put(f"decision:{intake_id}", decision)
        self.state.add_event(intake_id, approver_id, "APPROVED_STEP" if decision["status"] != "APPROVED" else "APPROVED",
                             {"by": self.s.people[approver_id]["name"],
                              "step": len(decision["approvals"]), "of": len(decision["chain"])}, ts)
        if decision["status"] == "APPROVED":
            self.state.add_event(intake_id, "AGENT", "EXPORTED",
                                 {"file": "AP_INVOICES_INTERFACE / AP_INVOICE_LINES_INTERFACE",
                                  "group_id": "NONPO-AGENT-20261015"}, ts)
        return None if ts else self.result(intake_id)

    # ---------- audit ----------
    def audit(self, intake_id):
        events = self.state.events(intake_id)
        for e in events:
            if e["actor"] in self.s.people:
                e["actor_name"] = self.s.people[e["actor"]]["name"]
                e["actor_title"] = self.s.people[e["actor"]]["title"]
            else:
                e["actor_name"] = "Non-PO agent" if e["actor"] == "AGENT" else e["actor"]
        return events

    # ---------- anomaly & insights ----------
    def anomalies(self):
        if self._anomaly is None:
            self._anomaly = {"journals": self.anomaly_layer.scan_journals(),
                             "ap_ledger": self.anomaly_layer.scan_ap_ledger(),
                             "cash": self.anomaly_layer.scan_cash()}
        return self._anomaly

    def procurement(self):
        by_month = defaultdict(lambda: {"po": 0.0, "non_po": 0.0})
        by_cat = defaultdict(lambda: {"po": 0.0, "non_po": 0.0, "breach": 0.0, "invoices_non_po": 0})
        repeat = defaultdict(lambda: {"count": 0, "value": 0.0, "months": set()})
        po_req = {r["category"]: r["min"] for r in self.s.policies["po_policy"]["required"]}
        for inv in self.s.history:
            m = inv["invoice_date"][:7]
            kind = "po" if inv["po_number"] else "non_po"
            by_month[m][kind] += inv["total_usd"]
            cat = inv["category"]
            by_cat[cat][kind] += inv["total_usd"]
            if not inv["po_number"]:
                by_cat[cat]["invoices_non_po"] += 1
                if cat in po_req and inv["total_usd"] >= po_req[cat]:
                    by_cat[cat]["breach"] += inv["total_usd"]
                if inv["invoice_date"] >= "2025-10-01":
                    rv = repeat[inv["vendor_id"]]
                    rv["count"] += 1
                    rv["value"] += inv["total_usd"]
                    rv["months"].add(m)
        cats = self.s.reference["categories"]
        candidates = []
        for vid, rv in repeat.items():
            v = self.s.vendors[vid]
            if len(rv["months"]) >= 9 and rv["value"] >= 150_000:
                candidates.append({"vendor_id": vid, "vendor": v["name"], "category": v["category_label"],
                                   "invoices_12m": rv["count"], "months_billed": len(rv["months"]),
                                   "value_12m": round(rv["value"], 2),
                                   "recommendation": "Blanket PO" if v["category"] not in
                                   self.s.policies["po_policy"]["exempt"] else "Standing approval rule"})
        candidates.sort(key=lambda c: -c["value_12m"])
        return {"by_month": [{"month": m, **{k: round(v, 2) for k, v in d.items()}} for m, d in sorted(by_month.items())],
                "by_category": sorted([{"category": cats[c]["label"], "key": c, **{k: round(v, 2) for k, v in d.items()}}
                                       for c, d in by_cat.items()], key=lambda x: -(x["non_po"])),
                "blanket_po_candidates": candidates[:15],
                "non_po_share": round(sum(d["non_po"] for d in by_month.values()) /
                                      sum(d["po"] + d["non_po"] for d in by_month.values()), 3)}

    # ---------- exports ----------
    def export_ap(self):
        approved = [iid.split(":", 1)[1] for iid, d in self.state.prefix("decision:").items() if d["status"] == "APPROVED"]
        results = [self._overlay(self.base[i]) for i in approved if i in self.base and self.base[i].get("coding")]
        return exports.ap_interface(self.s, results)

    def export_amortisation(self, intake_id):
        r = self.result(intake_id)
        if not r.get("amortisation"):
            raise ValueError("No amortisation for this invoice")
        return exports.gl_amortisation(self.s, r)

    def export_reclass(self):
        return exports.gl_reclass(self.s, self.anomalies()["journals"]["flags"])

    def export_procurement(self):
        return exports.procurement_report([self.base[i] for i in self.base if self.base[i].get("coding")])

    # ---------- wildcard (live, uncached) ----------
    def add_wildcard(self, pdf_bytes, filename, received_by="EMAIL"):
        from . import llm
        fields, meta = llm.extract_pdf(pdf_bytes, force_live=True)
        if not fields:
            raise ValueError("Extraction unavailable: " + meta.get("reason", meta.get("source", "")))
        cur = (fields.get("currency") or "USD").upper()
        doc = {"vendor_name": fields["vendor_name"], "vendor_tax_id": fields.get("vendor_tax_id"),
               "invoice_num": fields["invoice_num"], "invoice_date": fields["invoice_date"],
               "due_date": fields.get("due_date"), "currency": cur,
               "entity": {"EUR": "EU01", "INR": "IN01"}.get(cur, "US01"),
               "lines": fields["lines"] or [{"description": "Invoice total", "qty": 1, "unit_price": fields["total"],
                                             "amount": fields["total"]}],
               "subtotal": fields["subtotal"] or fields["total"] - (fields.get("tax") or 0),
               "tax": fields.get("tax") or 0, "total": fields["total"], "matter": fields.get("matter"),
               "ordered_by": fields.get("named_contact"), "customer_po": fields.get("po_reference"),
               "remit_to": {"account_last4": fields.get("remit_account_last4"),
                            "routing_number": fields.get("remit_routing_number")}}
        if fields.get("service_period_start") and fields.get("service_period_end"):
            doc["service_period"] = {"start": fields["service_period_start"], "end": fields["service_period_end"]}
        iid = f"WC-{uuid.uuid4().hex[:6].upper()}"
        item = {"intake_id": iid, "received_at": datetime.now().isoformat(timespec="minutes"), "channel": received_by,
                "sender": "Live upload", "subject": filename, "storyboard_key": "wildcard", "scene": None,
                "vendor_hint": None, "pdf": None, "document": doc,
                "extraction_override": {**meta, "fields": fields}}
        self.state.put(f"wildcard:{iid}", item)
        self.state.add_event(iid, "AGENT", "RECEIVED", {"channel": "Live upload", "file": filename}, None)
        return iid

    # ---------- reset & seed ----------
    def reset(self):
        real = self.state
        real.reset()
        self._anomaly = None
        self.base = {k: v for k, v in self._load_base().items()}
        buffered = BufferedState(real)
        self.state = self.agent.state = buffered
        try:
            for r in sorted(self.base.values(), key=lambda x: x["received_at"]):
                if not r["intake_id"].startswith("WC-"):
                    self._seed(r)
            buffered.put("meta:seeded", {"at": now_iso()})
        finally:
            self.state = self.agent.state = real
        buffered.flush()

    def _alternate_cc(self, r):
        """Second most common cost centre this supplier has been coded to, if any."""
        vid = r["vendor"]["vendor_id"]
        counts = Counter(self.s.lines[i]["cc"] for i in self.s.lines_by_vendor.get(vid, []))
        options = [cc for cc, _ in counts.most_common() if cc != r["coding"]["cost_centre"]]
        return options[0] if options else None

    def _seed(self, r):
        iid, key = r["intake_id"], r.get("storyboard_key")
        recv = datetime.fromisoformat(r["received_at"])
        ts = lambda h: (recv + timedelta(hours=h)).isoformat(timespec="minutes")
        self.state.add_event(iid, "AGENT", "RECEIVED", {"channel": r["channel"], "from": r["sender"],
                                                         "subject": r["subject"]}, ts(0))
        self._log_run(r, "AGENT", ts(0.02))
        if r["agent_status"] in ("HELD", "MATCH_TO_PO", "VENDOR_ONBOARDING"):
            return
        needs_receipt = (r.get("receipt") or {}).get("required")
        if key:
            if key in STORYBOARD_RECEIPTS and needs_receipt:
                at, note = STORYBOARD_RECEIPTS[key]
                self.request_receipt(iid, ts=ts(0.05))
                self.confirm_receipt(iid, r["requester"]["person"]["id"], note, ts=at)
            elif key == "legal":
                self.request_receipt(iid, ts=ts(0.05))
            return
        if r["received_at"][:10] >= LIVE_DAY:
            if needs_receipt:
                self.request_receipt(iid, ts=ts(0.05))
            return
        if needs_receipt:
            self.request_receipt(iid, ts=ts(0.05))
            self.confirm_receipt(iid, r["requester"]["person"]["id"], "Goods / service received as invoiced.",
                                 ts=ts(5 + _spread(iid, 20)))
        status_now = r.get("status_after_receipt", r["agent_status"])
        reviewer = "E34120"
        t = 26 + _spread(iid, 10)
        c = r["coding"]
        alt_cc = self._alternate_cc(r)
        corrected = (status_now == "RECOMMENDED" and _spread(iid, 3) == 0) or \
            (status_now == "FAST_TRACK" and _spread(iid, 11) == 0)
        if status_now == "NEEDS_CODING" or (corrected and alt_cc):
            self.submit(iid, "override", reviewer, "Requester confirmed the spend belongs to their cost centre",
                        {"account": c["account"], "cost_centre": alt_cc or c["cost_centre"]}, ts=ts(t))
        else:
            self.submit(iid, "accept", reviewer, ts=ts(t))
        decision = self.state.get(f"decision:{iid}")
        for i, pid in enumerate(decision["chain"]):
            self.approve_step(iid, pid, ts=ts(t + 3 + i * 5))
