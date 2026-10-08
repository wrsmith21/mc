"""The supervisor: runs every specialist in a fixed order, merges their findings, sets the status by precedence and
asks the model for the reviewer-facing reason. It can recommend, hold and route; it cannot approve or pay.
"""
from .. import llm
from ..engine.checks import Checks
from ..engine.policy import Policy
from ..engine.recommend import Recommender
from .base import RunContext
from .investigator import TRIGGERS, investigate
from .. import clock
from .specialists import ApprovalAgent, CodingAgent, IntakeAgent, PriceAgent, RiskAgent, SupplierAgent, Work
from .tools import build_registry

BASELINE_MINUTES = {"research_coding": 6, "find_approver": 4, "chase_receipt": 5, "key_invoice": 3}
AGENT_MINUTES = {"FAST_TRACK": 1.5, "RECOMMENDED": 4, "AWAITING_CONFIRMATION": 3, "NEEDS_CODING": 9, "HELD": 6,
                 "MATCH_TO_PO": 2, "VENDOR_ONBOARDING": 5, "ROUTED_OUT": 1}
STATUS_LABEL = {"NEW": "New – not yet worked", "FAST_TRACK": "Fast-track", "RECOMMENDED": "Recommended",
                "NEEDS_CODING": "Needs coding", "AWAITING_CONFIRMATION": "Awaiting confirmation", "HELD": "Held",
                "MATCH_TO_PO": "Match to PO", "VENDOR_ONBOARDING": "Held – unknown supplier",
                "ROUTED_OUT": "Routed out of AP", "APPROVED": "Approved", "REJECTED": "Rejected",
                "IN_APPROVAL": "In approval"}
PROCESS_ORDER = ["intake", "read", "supplier", "validity", "po", "coding", "treatment", "price", "receipt", "risk",
                 "approval", "decide"]


class Supervisor:
    def __init__(self, store, state):
        self.s = store
        self.state = state
        self.rec = Recommender(store)
        self.policy = Policy(store)
        self.checks = Checks(store)
        self.registry = build_registry(store, state, self.checks, self.policy, self.rec)
        self.registry.store = store
        self.agents = {"intake": IntakeAgent(), "supplier": SupplierAgent(), "coding": CodingAgent(),
                       "price": PriceAgent(), "approval": ApprovalAgent(), "risk": RiskAgent()}

    def bind_state(self, state):
        """Point the registry's state-backed tools at a different store (seeding uses a buffered one)."""
        self.state = state
        self.registry = build_registry(self.s, state, self.checks, self.policy, self.rec)
        self.registry.store = self.s

    def process(self, item, live=False, trigger="manual", actor="AGENT", on_event=None):
        ctx = RunContext(self.registry, item["intake_id"], trigger, actor, on_event)
        w = Work(item, live, today=clock.today() if trigger != "batch" else None)
        a = self.agents
        a["intake"].run(ctx, w)
        terminal = a["supplier"].run(ctx, w)
        if terminal:
            return self._finish(ctx, w, terminal)
        a["coding"].run(ctx, w)
        a["price"].run(ctx, w)
        a["approval"].run_receipt(ctx, w)
        a["risk"].run(ctx, w)
        a["approval"].run_approval(ctx, w)
        confirmed = not w.receipt["required"] or bool(w.task and w.task.get("status") == "confirmed")
        w.result["status_after_receipt"] = self.decide(w, True)
        return self._finish(ctx, w, self.decide(w, confirmed))

    @staticmethod
    def decide(w, receipt_ok):
        holds = [f for f in w.flags if f["severity"] == "hold"]
        if any(f["code"] == "OPEN_PO_MATCH" for f in holds):
            return "MATCH_TO_PO"
        if holds:
            return "HELD"
        if not receipt_ok:
            return "AWAITING_CONFIRMATION"
        if w.band == "manual":
            return "NEEDS_CODING"
        if w.band == "fast_track" and not [f for f in w.flags if f["severity"] == "warn"] and not w.contrast \
                and not w.result["capitalisation"] and not w.result.get("amortisation"):
            return "FAST_TRACK"
        return "RECOMMENDED"

    def _finish(self, ctx, w, status):
        r = w.result
        r.setdefault("total_usd", None)
        r["agent_status"] = status
        r["status"] = status
        r["status_label"] = STATUS_LABEL.get(status, status.title())
        r["flags"] = w.flags
        r["trace"] = ctx.trace
        base = sum(BASELINE_MINUTES.values())
        r["minutes"] = {"baseline": base, "agent": AGENT_MINUTES.get(status, 5), "note": "Illustrative handling-time model"}
        r["investigation"] = None
        if status in TRIGGERS:
            with ctx.step("investigator", "investigate", "Investigate the exception", 8) as st:
                inv = investigate(ctx, r)
                r["investigation"] = inv
                st["status"] = "warn"
                st["detail"] = f"{inv['next_action']} ({inv['source']})"
                st["facts"] = [inv["summary"]]
        with ctx.step("supervisor", "decide", "Decide and explain", 8) as st:
            out = ctx.call("llm.explain", findings=self._findings(r), fallback=self._template_reason(r),
                           show={"status": status, "flags": [f["code"] for f in w.flags]})
            r["explanation"], r["explanation_meta"] = out["text"], out["meta"]
            st["detail"] = f"{STATUS_LABEL.get(status, status)} · reason written ({out['meta'].get('source')})"
            st["facts"] = [f"Status precedence applied to {len(w.flags)} finding(s)"]
        r["next_action"] = self._next_action(r)
        r["run"] = ctx.finish()
        r["run"]["llm_model"] = llm.MODEL
        r["run"]["policy_version"] = getattr(self.s, "policy_version", 1)
        return r

    def _findings(self, r):
        c = r.get("coding") or {}
        return {"supplier": (r.get("vendor") or {}).get("name") or r["document"].get("vendor_name"),
                "status": r["agent_status"], "recommended_account": c.get("account"),
                "account_name": c.get("account_name"), "cost_centre": c.get("cost_centre"),
                "confidence": c.get("confidence"), "vendor_default_contrast": c.get("default_contrast"),
                "flags": [{"title": f["title"], "detail": f["detail"]} for f in r["flags"]],
                "approval_chain": [s["person"]["name"] + " (" + s["role_label"] + ")"
                                   for s in (r.get("approval") or {}).get("steps", [])],
                "evidence": [{k: e[k] for k in ("vendor", "date", "description", "account")}
                             for e in (c.get("lines") or [{}])[0].get("rec", {}).get("evidence", [])] if c else []}

    def _template_reason(self, r):
        c = r.get("coding")
        if not c:
            return r["flags"][0]["detail"] if r["flags"] else "No recommendation."
        parts = [f"Recommends {c['account']} {c['account_name']} / {c['cost_centre']} at {c['confidence']:.0%} "
                 f"confidence, based on {r['vendor']['name']}'s coding history and similar past invoices."]
        if c.get("default_contrast"):
            d = c["default_contrast"]
            parts.append(f"This overrides the vendor default {d['vendor_default']} {d['vendor_default_name']}: "
                         f"{d['invoices_coded_to_recommended']} past invoices for these items were coded to "
                         f"{c['lines'][0]['rec']['scored_account']}.")
        holds = [f for f in r["flags"] if f["severity"] in ("hold", "warn")]
        if holds:
            parts.append(holds[0]["title"] + ": " + holds[0]["detail"])
        return " ".join(parts)

    def _next_action(self, r):
        s = r["agent_status"]
        steps = (r.get("approval") or {}).get("steps") or []
        first = steps[0]["person"]["name"] if steps else None
        routing = r.get("routing") or {}
        return {"VENDOR_ONBOARDING": "Send to vendor onboarding (KYC, sanctions, bank verification).",
                "HELD": "Hold. Resolve the flagged control before any approval or payment.",
                "MATCH_TO_PO": "Route to 3-way match against the open PO.",
                "ROUTED_OUT": f"Forward to {routing.get('owner')} ({routing.get('to')}); close here.",
                "AWAITING_CONFIRMATION": f"Waiting for {((r.get('requester') or {}).get('person') or {}).get('name', 'the requester')} to confirm receipt.",
                "NEEDS_CODING": "Ask an AP specialist to code; recommendation shown as a starting point.",
                "FAST_TRACK": f"Fast-tracked within policy to {first} for approval.",
                "RECOMMENDED": f"Review the recommendation, then send to {first} for approval."}.get(s, "")
