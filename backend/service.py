"""Demo service: intake, agent runs, human decisions, audit trail, KPIs, anomaly layer, exports."""
import json
import queue as queue_mod
import re
import threading
import time
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from . import clock
from .agents.supervisor import STATUS_LABEL, Supervisor
from .engine import exports
from .engine.anomaly import AnomalyLayer
from .state import BufferedState, get_state, now_iso
from .store import CACHE, get_store

NOT_APPROVABLE = {"HELD", "MATCH_TO_PO", "VENDOR_ONBOARDING", "AWAITING_CONFIRMATION", "ROUTED_OUT", "NEW"}
LIVE_DAY = "2026-10-14"  # invoices received from this day on are still open at the start of the demo
MAILBOX_CUTOFF = "2026-10-15T06:00"  # received after this: this morning's mailbox, not yet worked by the agent
# Storyboard state at the start of the demo for invoices the agent worked before today.
STORYBOARD_RECEIPTS = {
    "learning_1": ("2026-10-13T18:40", "Chargers received by IT End-User Services."),
}


def _spread(intake_id, n):
    return int(re.sub(r"\D", "", intake_id) or 0) * 7 % n


def _key(desc):
    return re.sub(r"\(\d+\)", "", desc.lower()).strip()


def _run_summary(r):
    c = r.get("coding") or {}
    run = r["run"]
    return {"run_id": run["run_id"], "trigger": run["trigger"], "actor": run["actor"],
            "started_at": run["started_at"], "ms": run.get("ms"), "tool_calls": run.get("tool_calls"),
            "status": r["agent_status"], "account": c.get("account"), "cost_centre": c.get("cost_centre"),
            "confidence": c.get("confidence"), "flags": sorted(f["code"] for f in r["flags"]),
            "chain": [s["person"]["name"] for s in (r.get("approval") or {}).get("steps", [])],
            "receipt_rule": (r.get("receipt") or {}).get("rule"), "explanation_source":
                (r.get("explanation_meta") or {}).get("source")}


class DemoService:
    def __init__(self):
        self.s = get_store()
        self.state = get_state()
        self.agent = Supervisor(self.s, self.state)
        self.anomaly_layer = AnomalyLayer(self.s, self.agent.rec)
        self.items = {q["intake_id"]: q for q in self.s.intake}
        self.by_key = {q["storyboard_key"]: q["intake_id"] for q in self.s.intake if q.get("storyboard_key")}
        self._anomaly = None
        self._lock = threading.Lock()
        if not self.state.get("meta:seeded"):
            self.reset()
        clock.set_offset_hours((self.state.get("meta:clock") or {}).get("offset_hours", 0))

    # ---------- results & runs ----------
    def _batch_results(self):
        path = CACHE / "agent_results.json"
        if path.exists():
            return json.loads(path.read_text())
        return {iid: self.agent.process(item, trigger="batch")
                for iid, item in self.items.items() if item["received_at"] < MAILBOX_CUTOFF}

    def all_items(self):
        items = dict(self.items)
        for w in self.state.prefix("wildcard:").values():
            items[w["intake_id"]] = w
        return items

    def latest(self, intake_id):
        return self.state.get(f"result:{intake_id}")

    def _usd(self, amount, currency):
        if currency == "USD":
            return round(amount, 2)
        eur, inr = self.s.reference["fx_monthly"]["2026-10"]
        return round(amount * eur, 2) if currency == "EUR" else round(amount / inr, 2)

    def _skeleton(self, item):
        doc = item["document"]
        return {"intake_id": item["intake_id"], "received_at": item["received_at"], "channel": item["channel"],
                "sender": item["sender"], "subject": item["subject"], "storyboard_key": item.get("storyboard_key"),
                "scene": item.get("scene"), "pdf": item.get("pdf"), "document": doc, "extraction": None,
                "total_usd": self._usd(doc["total"], doc["currency"]), "agent_status": "NEW", "status": "NEW",
                "status_label": STATUS_LABEL["NEW"], "flags": [], "trace": [], "run": None, "coding": None,
                "explanation": None, "explanation_meta": None, "next_action": "Run the agent to work this invoice."}

    def result(self, intake_id):
        item = self.all_items()[intake_id]
        r = self.latest(intake_id) or self._skeleton(item)
        out = self._overlay(r)
        out["runs"] = self.state.get(f"runs:{intake_id}") or []
        out["stale"] = self._stale(r)
        return out

    def _stale(self, r):
        """Why the latest run may no longer reflect the facts: something changed after it finished."""
        run = r.get("run")
        if not run or not r.get("vendor") or not r["vendor"].get("vendor_id"):
            return None
        done = run.get("finished_at") or run["started_at"]
        for lesson in self.state.prefix(f"learned:{r['vendor']['vendor_id']}:").values():
            if lesson["at"] >= done and lesson.get("source_invoice") != r["document"].get("invoice_num"):
                return f"A correction for this supplier was learned at {lesson['at'][11:16]}, after this run. " \
                       f"Re-run the agent to apply it."
        return None

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

    def _diff(self, prev, new):
        if not prev or not prev.get("run"):
            return []
        a, b = _run_summary(prev), _run_summary(new)
        labels = {"status": "Status", "account": "Account", "cost_centre": "Cost centre", "confidence": "Confidence",
                  "flags": "Flags", "chain": "Approval chain", "receipt_rule": "Receipt"}
        out = []
        for k, label in labels.items():
            if a[k] != b[k]:
                out.append({"field": label, "before": a[k], "after": b[k]})
        if not out:
            return [{"field": "No change", "before": None, "after": None,
                     "cause": "Same inputs, same policy, same result."}]
        task = self.state.get(f"receipt:{new['intake_id']}")
        vid = (new.get("vendor") or {}).get("vendor_id")
        learned = [l for l in self.state.prefix(f"learned:{vid}:").values() if l["at"] > prev["run"]["started_at"]] \
            if vid else []
        if task and task.get("status") == "confirmed" and task["confirmed_at"] > prev["run"]["started_at"]:
            cause = f"Receipt confirmed by {task['confirmed_by_name']} at {task['confirmed_at'][11:16]}"
        elif learned:
            cause = f"Correction learned from invoice {learned[-1]['source_invoice']} ({learned[-1]['by']})"
        else:
            cause = "Inputs or reference data changed since the last run"
        for d in out:
            d["cause"] = cause
        return out

    def _save(self, r, state=None):
        st = state or self.state
        iid = r["intake_id"]
        runs = st.get(f"runs:{iid}") or []
        runs.append(_run_summary(r))
        st.put(f"result:{iid}", r)
        st.put(f"runs:{iid}", runs[-20:])

    def run(self, intake_id, trigger="manual", actor="E34120", on_event=None, live=True):
        item = self.all_items()[intake_id]
        with self._lock:
            prev = self.latest(intake_id)
            r = self.agent.process(item, live=live, trigger=trigger, actor=actor, on_event=on_event)
            r["run"]["previous_run_id"] = prev["run"]["run_id"] if prev and prev.get("run") else None
            r["run"]["diff"] = self._diff(prev, r)
            self._save(r)
            self.state.add_event(intake_id, actor if trigger == "manual" else "AGENT", "RUN_COMPLETED", {
                "run_id": r["run"]["run_id"], "trigger": trigger, "ms": r["run"]["ms"],
                "tool_calls": r["run"]["tool_calls"], "status": r["agent_status"]})
            self._log_run(r)
        return self.result(intake_id)

    def run_events(self, intake_id, actor="E34120", live=True):
        """Stream the run as it happens: each step and tool call is sent the moment it completes."""
        events = queue_mod.Queue()

        def work():
            try:
                events.put({"type": "result", "result": self.run(intake_id, "manual", actor, events.put, live)})
            except Exception as e:  # surfaced to the client, never swallowed
                events.put({"type": "error", "message": f"{type(e).__name__}: {e}"})
            finally:
                events.put(None)

        yield {"type": "start", "intake_id": intake_id, "steps": ["intake", "read", "supplier", "validity", "po",
                                                                   "coding", "treatment", "receipt", "risk",
                                                                   "approval", "decide"]}
        threading.Thread(target=work, daemon=True).start()
        while True:
            ev = events.get()
            if ev is None:
                return
            yield ev

    def new_invoices(self):
        return sorted([iid for iid in self.all_items() if not self.latest(iid)],
                      key=lambda i: self.all_items()[i]["received_at"])

    def run_mailbox(self, actor="E34120"):
        """Work every invoice still waiting in the mailbox, streaming one event per invoice."""
        todo = self.new_invoices()
        yield {"type": "start", "count": len(todo)}
        t = time.perf_counter()
        for iid in todo:
            try:
                r = self.run(iid, "mailbox", actor)
                yield {"type": "invoice", "intake_id": iid, "status": r["status"], "status_label": r["status_label"],
                       "ms": r["run"]["ms"], "tool_calls": r["run"]["tool_calls"],
                       "vendor": (r.get("vendor") or {}).get("name") or r["document"].get("vendor_name")}
            except Exception as e:
                yield {"type": "error", "intake_id": iid, "message": f"{type(e).__name__}: {e}"}
        yield {"type": "done", "count": len(todo), "ms": round((time.perf_counter() - t) * 1000)}

    def agents(self):
        return {"tools": self.agent.registry.describe()}

    # ---------- queue & summary ----------
    def _results(self):
        return {k.split(":", 1)[1]: v for k, v in self.state.prefix("result:").items()}

    def queue(self):
        decisions = self.state.prefix("decision:")
        receipts = self.state.prefix("receipt:")
        results = self._results()
        rows = []
        for iid, item in self.all_items().items():
            r = results.get(iid) or self._skeleton(item)
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
                         "pdf": bool(o.get("pdf")), "wildcard": iid.startswith("WC-"),
                         "worked_at": (o.get("run") or {}).get("started_at"),
                         "trigger": (o.get("run") or {}).get("trigger")})
        rows.sort(key=lambda x: x["received_at"], reverse=True)
        return rows

    def summary(self):
        rows = self.queue()
        results = self._results()
        worked = [r for r in rows if r["status"] != "NEW"]
        decisions = self.state.prefix("decision:")
        approved = [d for d in decisions.values() if d["status"] == "APPROVED"]
        touchless = [d for d in approved if not d.get("override")]
        by_status = Counter(r["status"] for r in rows)
        agent_status = Counter(r["agent_status"] for r in worked)
        base = sum(results[r["intake_id"]]["minutes"]["baseline"] for r in worked)
        agent = sum(results[r["intake_id"]]["minutes"]["agent"] for r in worked)
        held = [r for r in rows if r["status"] in ("HELD", "VENDOR_ONBOARDING")]
        prevented = [r for r in worked if (results[r["intake_id"]].get("coding") or {}).get("default_contrast")]
        breaches = [r for r in rows if any(f["code"] == "PO_POLICY" for f in r["flags"])]
        cycle = []
        for iid, d in decisions.items():
            if d["status"] == "APPROVED" and d.get("approvals"):
                rec = results.get(iid.split(":", 1)[1])
                if rec:
                    t0 = datetime.fromisoformat(rec["received_at"])
                    t1 = datetime.fromisoformat(d["approvals"][-1]["at"][:16])
                    cycle.append((t1 - t0).total_seconds() / 86400)
        return {
            "processed": len(worked), "received": len(rows), "new": by_status["NEW"],
            "by_status": by_status, "agent_status": agent_status,
            "fast_tracked": agent_status["FAST_TRACK"], "held": len(held),
            "held_value_usd": round(sum(r["total_usd"] for r in held), 2),
            "approved": len(approved), "touchless": len(touchless),
            "touchless_rate": round(len(touchless) / len(approved), 3) if approved else None,
            "miscodings_prevented": len(prevented),
            "miscodings_prevented_value": round(sum(r["total_usd"] for r in prevented), 2),
            "po_policy_breaches": len(breaches), "po_breach_value": round(sum(r["total_usd"] for r in breaches), 2),
            "open_po_matches": agent_status["MATCH_TO_PO"], "routed_out": agent_status["ROUTED_OUT"],
            "awaiting_confirmation": by_status["AWAITING_CONFIRMATION"],
            "hours_saved": round((base - agent) / 60, 1), "baseline_hours": round(base / 60, 1),
            "avg_cycle_days": round(sum(cycle) / len(cycle), 1) if cycle else None, "baseline_cycle_days": 6.5,
            "value_in_queue_usd": round(sum(r["total_usd"] for r in rows), 2),
            "history": {"invoices": len(self.s.history), "lines": len(self.s.lines), "vendors": len(self.s.vendors),
                        "people": len(self.s.people), "pos": len(self.s.pos), "journals": len(self.s.journals),
                        "receipts": len(self.s.receipts)},
        }

    def _log_run(self, r, ts=None):
        iid = r["intake_id"]
        ex = r.get("extraction") or {}
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
        r = self.latest(intake_id)
        if not r:
            raise ValueError("Run the agent before requesting receipt")
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
        r = self.latest(intake_id)
        if not r:
            raise ValueError("Run the agent first: this invoice has not been worked")
        return self._overlay(r) if seeding else self.result(intake_id)

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
        results = self._results()
        results = [self._overlay(results[i]) for i in approved if i in results and results[i].get("coding")]
        return exports.ap_interface(self.s, results)

    def export_amortisation(self, intake_id):
        r = self.result(intake_id)
        if not r.get("amortisation"):
            raise ValueError("No amortisation for this invoice")
        return exports.gl_amortisation(self.s, r)

    def export_reclass(self):
        return exports.gl_reclass(self.s, self.anomalies()["journals"]["flags"])

    def export_procurement(self):
        return exports.procurement_report([r for r in self._results().values() if r.get("coding")])

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
        item = {"intake_id": iid, "received_at": clock.now_iso()[:16], "channel": received_by,
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
        clock.set_offset_hours(0)
        buffered = BufferedState(real)
        self.state = buffered
        self.agent.bind_state(buffered)
        try:
            batch = self._batch_results()
            for item in sorted(self.items.values(), key=lambda q: q["received_at"]):
                iid = item["intake_id"]
                recv = datetime.fromisoformat(item["received_at"])
                self.state.add_event(iid, "AGENT", "RECEIVED", {"channel": item["channel"], "from": item["sender"],
                                                                 "subject": item["subject"]},
                                     recv.isoformat(timespec="minutes"))
                r = batch.get(iid)
                if not r or item["received_at"] >= MAILBOX_CUTOFF:
                    continue
                at = (recv + timedelta(minutes=1)).isoformat(timespec="seconds")
                r["run"].update(trigger="batch", actor="AGENT", started_at=at, finished_at=at,
                                previous_run_id=None, diff=[])
                self._save(r)
                self.state.add_event(iid, "AGENT", "RUN_COMPLETED", {
                    "run_id": r["run"]["run_id"], "trigger": "batch", "ms": r["run"]["ms"],
                    "tool_calls": r["run"]["tool_calls"], "status": r["agent_status"]}, at[:16])
                self._seed(r)
            buffered.put("meta:seeded", {"at": now_iso()})
        finally:
            self.state = real
            self.agent.bind_state(real)
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
        self._log_run(r, ts(0.02))
        if r["agent_status"] in ("HELD", "MATCH_TO_PO", "VENDOR_ONBOARDING", "ROUTED_OUT"):
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
