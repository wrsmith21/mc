"""The in-app assistant: plain-English questions about today's invoices, the close and cash, answered by Claude.

Claude reads through the same read-only tools the agents use, plus a few views of the demo state (queue, cases,
procurement). It cannot approve, change a status or contact anyone. Every call is recorded and returned with the
answer so the panel can show what was checked.
"""
import json
import time

from .. import clock, llm
from .base import RunContext

MAX_TOOL_ROUNDS = 6
DEADLINE_S = 50
MAX_TURNS = 12
MAX_CHARS = 2000
REGISTRY_TOOLS = ["vendor.search", "vendor.profile", "vendor.bank_change_log", "history.vendor_invoices",
                  "history.similar_lines", "po.open_for_vendor", "policy.approval_matrix", "people.directory",
                  "journal.entry", "ar.customer_items"]

SYSTEM = """You are the assistant inside CLEAR (Coding, Ledger, Exceptions, Approvals, Reconciliation), an AI agent \
demonstrated to Mastercard's GBSC Finance leadership. CLEAR works non-PO invoices end to end, then sweeps the close \
journals, the AP subledger and cash application for the same mistakes. A person approves every posting: the agent \
recommends, it never decides.

What the people asking care about:
- Non-PO invoices (P2P): coding recommended from 18 months of history with reasons and a calibrated confidence; \
requester confirmation of receipt; approval routing by the approval matrix with separation of duties and limits; \
duplicate, bank-change and fraud checks; PO-policy breaches logged for procurement.
- The Dell laptop example: Dell's vendor-master default is 6420 Repairs & Maintenance (service contracts), but laptops \
belong in 1540 Computer Hardware and route to Fixed Asset Accounting. CLEAR prevents that miscoding at entry.
- Record to report: the same engine finds miscodings in manual journals (the "Laptop refresh – Q3" journal), \
duplicate accruals and self-approved entries, with drafted reclasses posted as GL_INTERFACE files after approval.
- Cash application: about 11,400 settlement receipts a day, ~98% auto-applied; CLEAR finds the misapplied ones \
(a receipt from customer 30418 applied to 30481) and proposes matches for unapplied cash.
- Procure to pay: invoices that match an open PO go to three-way match; repeat non-PO spend becomes blanket-PO \
candidates.
- Governance: every step is logged as audit evidence; the model only reads, explains and investigates.

How to answer:
- Use the tools to check facts before answering anything about specific invoices, suppliers, cases, people, \
policies or numbers. Call independent tools in parallel. Never invent a figure, name or ID.
- Be brief and concrete: under 120 words unless the person asks for detail; two to five sentences, or a short \
"- " bullet list when listing items. Lead with the answer. Use **bold** sparingly. No headings, no tables.
- Name people, never employee IDs.
- Refer to invoices as supplier name plus intake ID (for example IN-2026-00108) and to close cases by case ID \
(for example CA-0B7A49EF), so the app can link them.
- You can take a few actions for the signed-in person: run the agent on an invoice, run the agent on this \
morning's mailbox, send a requester the confirm-receipt request, and investigate a close case. Use an action tool \
only when the person's latest message explicitly asks for that action or says yes to an action you offered; never \
act on your own initiative, and never act on an invoice other than the one they mean. The server checks their \
role; if it refuses, say who can do it. After acting, say what you did and what came out (status, recommendation, \
flags) in two or three sentences.
- You cannot approve, reject, override coding, post or change master data: those decisions stay with a person in \
the app. Say which button and which person.
- This is a demonstration on synthetic data built by Ciklum. Do not claim live integration with Mastercard's \
Oracle R12, Coupa or AppZen; CLEAR works through standard extracts and upload files. Do not quote accuracy as a \
product claim: confidence figures are measured on synthetic data.
- If a question is outside finance operations or this demo, say briefly what you can help with instead."""

APP_TOOLS = [
    {"name": "clear_summary", "description": "Today's position: invoices received and worked, fast-tracked, held, "
     "approved, touchless rate, PO-policy breaches, open-PO matches, hours saved, and history volumes.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "search_invoices", "description": "Search today's non-PO invoice queue by supplier, invoice number, "
     "account or flag text, optionally by status. Returns up to 15 rows with status, coding, confidence and flags.",
     "input_schema": {"type": "object", "properties": {
         "query": {"type": "string", "description": "Text to match; empty for all"},
         "status": {"type": "string", "description": "One of NEW, FAST_TRACK, RECOMMENDED, NEEDS_CODING, "
                    "AWAITING_CONFIRMATION, HELD, MATCH_TO_PO, VENDOR_ONBOARDING, IN_APPROVAL, APPROVED, REJECTED, "
                    "ROUTED_OUT"}}}},
    {"name": "get_invoice", "description": "Full detail for one invoice by intake ID (IN-2026-#####): what was read, "
     "recommended coding and why, evidence, flags, requester and receipt, approval chain with SoD, treatment, status.",
     "input_schema": {"type": "object", "properties": {"intake_id": {"type": "string"}}, "required": ["intake_id"]}},
    {"name": "search_close_cases", "description": "Findings from the close: journals (record to report), ap_ledger "
     "(AP subledger miscodes) and cash (cash application). Filter by source, type or status; returns counts and up "
     "to 15 cases with amount, owner, SLA and drafted fix.",
     "input_schema": {"type": "object", "properties": {
         "source": {"type": "string", "enum": ["journals", "ap_ledger", "cash"]},
         "type": {"type": "string", "description": "MISCODED, DUPLICATE_ENTRY, SELF_APPROVED, AP_MISCODE, "
                  "MISAPPLIED, DOUBLE_APPLICATION, UNAPPLIED_MATCH"},
         "status": {"type": "string", "description": "Open, Pending approval, Approved, Exported, Dismissed"},
         "query": {"type": "string"}}}},
    {"name": "get_case", "description": "One close case by case ID: finding, drafted fix, owner, approver, "
     "investigation and decision log.",
     "input_schema": {"type": "object", "properties": {"case_id": {"type": "string"}}, "required": ["case_id"]}},
    {"name": "procurement_insights", "description": "Non-PO share of AP spend, non-PO spend by category including "
     "spend in PO-required categories, and recurring suppliers that are blanket-PO candidates.",
     "input_schema": {"type": "object", "properties": {}}},
]


def _invoice_view(r):
    doc, c = r["document"], r.get("coding") or {}
    rec = ((c.get("lines") or [{}])[0].get("rec") or {})
    appr = r.get("approval") or {}
    return {
        "intake_id": r["intake_id"], "status": r.get("status_label") or r.get("status"),
        "received_at": r.get("received_at"), "sender": r.get("sender"),
        "supplier": (r.get("vendor") or {}).get("name") or doc.get("vendor_name"),
        "invoice_num": doc.get("invoice_num"), "invoice_date": doc.get("invoice_date"), "currency": doc.get("currency"),
        "total": doc.get("total"), "total_usd": r.get("total_usd"), "entity": doc.get("entity"),
        "lines": [{"description": l["description"], "qty": l["qty"], "unit_price": l["unit_price"]} for l in doc["lines"]],
        "recommendation": {k: c.get(k) for k in ("account", "account_name", "cost_centre", "confidence", "band")},
        "vendor_default_contrast": c.get("default_contrast"),
        "reason": r.get("explanation"),
        "similar_past_invoices": [{k: e.get(k) for k in ("vendor", "date", "description", "account", "approved_by")}
                                  for e in rec.get("evidence", [])[:3]],
        "flags": [{"title": f["title"], "severity": f["severity"], "detail": f["detail"]} for f in r.get("flags", [])],
        "requester": {"name": ((r.get("requester") or {}).get("person") or {}).get("name"),
                      "source": (r.get("requester") or {}).get("source")},
        "receipt": {"rule": (r.get("receipt") or {}).get("rule"), "detail": (r.get("receipt") or {}).get("detail"),
                    "task": {k: (r.get("receipt_task") or {}).get(k) for k in ("status", "assignee_name",
                                                                                 "confirmed_by_name", "confirmed_at")}},
        "approval_chain": [{"name": s["person"]["name"], "role": s["role_label"],
                            "skipped": [k["reason"] for k in s.get("skipped", [])]} for s in appr.get("steps", [])],
        "capitalisation": r.get("capitalisation"),
        "amortisation": {k: (r.get("amortisation") or {}).get(k) for k in ("months", "monthly_amount",
                                                                            "expense_account")} if r.get("amortisation") else None,
        "investigation": {k: (r.get("investigation") or {}).get(k) for k in ("summary", "next_action")}
        if r.get("investigation") else None,
        "next_action": r.get("next_action"),
        "decision": {k: (r.get("decision") or {}).get(k) for k in ("status", "reason", "approvals")}
        if r.get("decision") else None,
    }


def _case_view(c, people, full=False):
    v = {"case_id": c["case_id"], "type": c["type_label"], "source": c["source"], "reference": c["reference"],
         "amount": c["amount"], "currency": c["currency"], "status": c["status"], "owner": c.get("owner_name"),
         "sla_due": c.get("sla_due"), "overdue": c.get("overdue"), "detail": c["detail"]}
    if full:
        name = lambda pid: (people.get(pid or "") or {}).get("name")
        v.update(fix=c.get("fix"), finding={k: x for k, x in c["finding"].items() if k not in ("evidence", "score")},
                 designated_approver=name(c.get("approver_role")), approved_by=name(c.get("approver")),
                 decision_log=c.get("decision_log"))
    return v


ACTION_TOOLS = [
    {"name": "run_agent", "description": "ACTION. Run the agent on one invoice now (all checks, coding, routing), "
     "as the signed-in person. Use only when they ask for it. Returns the new result.",
     "input_schema": {"type": "object", "properties": {"intake_id": {"type": "string"}}, "required": ["intake_id"]}},
    {"name": "run_mailbox", "description": "ACTION. Run the agent on every invoice in this morning's mailbox that "
     "has not been worked yet. Use only when asked. Returns counts by outcome.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "request_receipt", "description": "ACTION. Send the identified requester the confirm-receipt request "
     "for an invoice. Use only when asked.",
     "input_schema": {"type": "object", "properties": {"intake_id": {"type": "string"}}, "required": ["intake_id"]}},
    {"name": "investigate_case", "description": "ACTION. Have the investigator work a close case with read-only "
     "checks and record its finding and recommended next step. Use only when asked.",
     "input_schema": {"type": "object", "properties": {"case_id": {"type": "string"}}, "required": ["case_id"]}},
]


class Assistant:
    def __init__(self, svc):
        self.svc = svc

    def _registry_defs(self):
        reg = self.svc.agent.registry
        out = []
        for name in REGISTRY_TOOLS:
            t = reg[name]
            props = {k: {kk: vv for kk, vv in v.items() if kk != "optional"} for k, v in t.inputs.items()}
            out.append({"name": name.replace(".", "_"), "description": t.description,
                        "input_schema": {"type": "object", "properties": props,
                                         "required": [k for k, v in t.inputs.items() if not v.get("optional")]}})
        return out

    def _app_tool(self, name, args):
        s = self.svc
        if name == "clear_summary":
            return s.summary()
        if name == "search_invoices":
            q = (args.get("query") or "").lower()
            st = (args.get("status") or "").upper()
            rows = [r for r in s.queue() if (not st or r["status"] == st or r["agent_status"] == st)
                    and (not q or q in " ".join(str(x) for x in (r["vendor"], r["invoice_num"], r["account"],
                                                                 r["account_name"], r["intake_id"],
                                                                 *(f["title"] for f in r["flags"]))).lower())]
            return {"matches": len(rows), "rows": [{k: r[k] for k in ("intake_id", "vendor", "invoice_num", "total",
                                                                       "currency", "status_label", "account",
                                                                       "account_name", "cost_centre", "confidence")}
                                                    | {"flags": [f["title"] for f in r["flags"]]} for r in rows[:15]]}
        if name == "get_invoice":
            return _invoice_view(s.result(args["intake_id"].strip().upper()))
        if name == "search_close_cases":
            cases = s.cases.all()
            q = (args.get("query") or "").lower()
            sel = [c for c in cases if (not args.get("source") or c["source"] == args["source"])
                   and (not args.get("type") or c["type"] == args["type"])
                   and (not args.get("status") or c["status"] == args["status"])
                   and (not q or q in (c["detail"] + c["reference"] + str(c["finding"].get("description", ""))).lower())]
            sel.sort(key=lambda c: -(c["amount"] or 0))
            counts = {}
            for c in sel:
                counts[c["type_label"]] = counts.get(c["type_label"], 0) + 1
            return {"matches": len(sel), "by_type": counts, "cases": [_case_view(c, s.s.people) for c in sel[:15]]}
        if name == "get_case":
            c = s.cases.get(args["case_id"].strip().upper())
            v = _case_view(c, s.s.people, full=True)
            inv = s.state.get(f"caseinv:{c['case_id']}")
            if inv:
                v["investigation"] = {"summary": inv.get("summary"), "next_action": inv.get("next_action")}
            return v
        if name == "procurement_insights":
            p = s.procurement()
            return {"non_po_share_of_spend": p["non_po_share"], "by_category": p["by_category"][:10],
                    "blanket_po_candidates": p["blanket_po_candidates"][:10]}
        raise KeyError(name)

    def _action(self, name, args, actor):
        """Write actions run as the signed-in person; the service enforces their permissions and logs them."""
        s = self.svc
        if name == "run_agent":
            iid = args["intake_id"].strip().upper()
            r = s.run(iid, "manual", actor, live=True)
            run = r.get("run") or {}
            view = _invoice_view(r) | {"run": {"ms": run.get("ms"), "tool_calls": run.get("tool_calls"),
                                               "changes_from_previous_run": run.get("diff")}}
            return view, {"type": "run_agent", "intake_id": iid, "label": f"Ran the agent on {iid}",
                          "status": r.get("status_label")}
        if name == "run_mailbox":
            outcomes, count = {}, 0
            for ev in s.run_mailbox(actor=actor):
                if ev["type"] == "invoice":
                    count += 1
                    outcomes[ev["status_label"]] = outcomes.get(ev["status_label"], 0) + 1
            return ({"worked": count, "by_outcome": outcomes},
                    {"type": "run_mailbox", "label": f"Ran the agent on {count} mailbox invoice(s)"})
        if name == "request_receipt":
            iid = args["intake_id"].strip().upper()
            task = s.request_receipt(iid, actor=actor)
            return task, {"type": "request_receipt", "intake_id": iid,
                          "label": f"Asked {task.get('assignee_name', 'the requester')} to confirm receipt"}
        if name == "investigate_case":
            cid = args["case_id"].strip().upper()
            out = s.investigate_case(cid, actor)
            return ({k: out.get(k) for k in ("summary", "next_action", "evidence", "source")},
                    {"type": "investigate_case", "case_id": cid, "label": f"Investigated case {cid}"})
        raise KeyError(name)

    def answer(self, messages, actor, context=None):
        """messages: [{role, content}] from the panel, newest last. Returns the reply and what was checked."""
        convo = [{"role": m["role"], "content": str(m["content"])[:MAX_CHARS]} for m in messages[-MAX_TURNS:]
                 if m.get("role") in ("user", "assistant") and str(m.get("content", "")).strip()]
        while convo and convo[0]["role"] != "user":
            convo.pop(0)
        if not convo or convo[-1]["role"] != "user":
            raise ValueError("Ask a question first")
        if context:
            convo[-1] = {"role": "user", "content": f"{convo[-1]['content']}\n\n(Context: the person is viewing "
                                                    f"{json.dumps(context)} in the app; \"this\" refers to it.)"}
        person = self.svc.s.people.get(actor, {})
        system = SYSTEM + (f"\n\nThe person asking is {person.get('name')}, {person.get('title')}. "
                           f"The demo clock reads {clock.now_iso()}.")

        ctx = RunContext(self.svc.agent.registry, "CHAT", "chat", actor)
        tools = APP_TOOLS + ACTION_TOOLS + self._registry_defs()
        checked, actions, t0, rounds = [], [], time.time(), 0
        client = llm._client()
        while True:
            budget = rounds < MAX_TOOL_ROUNDS and time.time() - t0 < DEADLINE_S
            response = client.beta.messages.create(
                model=llm.MODEL, max_tokens=4000, betas=[llm.FALLBACK_BETA], fallbacks="default",
                system=system, tools=tools, tool_choice={"type": "auto" if budget else "none"},
                output_config={"effort": "low"}, messages=convo)
            if response.stop_reason == "refusal":
                return {"reply": "I can’t help with that one. Ask me about today’s invoices, the close or cash "
                                 "application.", "checked": checked, "actions": actions, "model": response.model,
                        "ms": round((time.time() - t0) * 1000)}
            uses = [b for b in response.content if b.type == "tool_use"]
            if response.stop_reason != "tool_use" or not uses:
                text = "\n".join(b.text for b in response.content if b.type == "text").strip()
                return {"reply": text or "I didn’t find an answer to that.", "checked": checked, "actions": actions,
                        "model": response.model, "ms": round((time.time() - t0) * 1000)}
            rounds += 1
            convo.append({"role": "assistant", "content": response.content})
            results = []
            for b in uses:
                args = dict(b.input or {})
                try:
                    if b.name in {t["name"] for t in ACTION_TOOLS}:
                        result, action = self._action(b.name, args, actor)
                        actions.append({**action, "ok": True})
                        summary = action["label"]
                    elif b.name in {t["name"] for t in APP_TOOLS}:
                        result = self._app_tool(b.name, args)
                        summary = b.name.replace("_", " ")
                    else:
                        name = b.name.replace("_", ".", 1)
                        if name not in REGISTRY_TOOLS:
                            raise KeyError(f"Unknown tool {b.name}")
                        result = ctx.call(name, **args)
                        summary = ctx.last_call.get("summary") or name
                    checked.append({"tool": b.name, "args": args, "summary": summary})
                    results.append({"type": "tool_result", "tool_use_id": b.id,
                                    "content": json.dumps(result, default=str)[:9000]})
                except Exception as e:  # report to the model; it can try another way or explain the refusal
                    if b.name in {t["name"] for t in ACTION_TOOLS}:
                        actions.append({"type": b.name, "label": f"Couldn’t {b.name.replace('_', ' ')}: {e}",
                                        "ok": False, **{k: v for k, v in args.items() if k in ("intake_id", "case_id")}})
                    checked.append({"tool": b.name, "args": args, "summary": "not found", "error": True})
                    results.append({"type": "tool_result", "tool_use_id": b.id, "is_error": True,
                                    "content": f"{type(e).__name__}: {e}"})
            convo.append({"role": "user", "content": results})
