"""The investigator: Claude works an exception with read-only tools, then reports what it found.

It runs only when the deterministic agents could not clear an invoice (held, needs coding, unknown supplier). Every
tool it calls goes through the same recorded registry as the specialists, it cannot write or change a status, and its
answer is schema-checked: evidence must cite tool calls that actually ran. If the model is unavailable, over budget or
returns something invalid, a deterministic summary of the findings is used instead.
"""
import json
import time

from .. import llm

PROMPT_VERSION = "inv-1"
MAX_CALLS = 8
DEADLINE_S = 45
TRIGGERS = {"HELD", "NEEDS_CODING", "VENDOR_ONBOARDING"}
LLM_TOOLS = ["vendor.profile", "vendor.bank_change_log", "history.vendor_invoices", "history.similar_lines",
             "invoice.find", "po.open_for_vendor", "policy.approval_matrix", "people.directory", "vendor.search",
             "price.matter_budget", "cutoff.check"]
NEXT_ACTIONS = ["Reject as a duplicate", "Hold for vendor-master call-back", "Reject as suspected fraud",
                "Send to supplier onboarding", "Ask the supplier for a corrected invoice",
                "Code manually starting from the closest past invoices", "Ask the requester to confirm the coding",
                "Route to three-way match against the open PO", "Release after the check is cleared"]
DEFAULT_ACTION = {"HELD": "Hold for vendor-master call-back", "NEEDS_CODING": "Ask the requester to confirm the coding",
                  "VENDOR_ONBOARDING": "Send to supplier onboarding"}

SYSTEM = (
    "You are the exception investigator in an accounts-payable agent at a global payments company. The deterministic "
    "agents have already worked the invoice and could not clear it. Your job is to find out why and say what a "
    "person should do next. Use the tools to check the facts; call several in parallel when they are independent. "
    "You can only read: you cannot approve, change a status, contact anyone or edit master data. "
    "Every tool result starts with a call id like [T07]. Cite those ids as evidence; never cite a fact you did not "
    "read from a tool or from the case file. Be specific with numbers, dates and names. Write for an AP reviewer: "
    "plain English, no hedging, two to four sentences in the summary.")

ANSWER_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["summary", "evidence", "next_action", "confidence"],
    "properties": {
        "summary": {"type": "string"},
        "evidence": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["text", "tool_call_id"],
            "properties": {"text": {"type": "string"}, "tool_call_id": {"type": "string"}}}},
        "next_action": {"type": "string", "enum": NEXT_ACTIONS},
        "confidence": {"type": "number"},
    },
}


def _tool_defs(registry):
    out = []
    for name in LLM_TOOLS:
        t = registry[name]
        props = {k: {kk: vv for kk, vv in v.items() if kk != "optional"} for k, v in t.inputs.items()}
        out.append({"name": name.replace(".", "_"), "description": t.description,
                    "input_schema": {"type": "object", "properties": props,
                                     "required": [k for k, v in t.inputs.items() if not v.get("optional")]}})
    return out


def case_file(r):
    """What the investigator is told up front: the invoice and the deterministic findings."""
    doc = r["document"]
    return {"intake_id": r["intake_id"], "status": r["agent_status"], "received_at": r["received_at"],
            "sender": r["sender"], "vendor_id": (r.get("vendor") or {}).get("vendor_id"),
            "supplier_on_invoice": doc.get("vendor_name"), "invoice_num": doc.get("invoice_num"),
            "invoice_date": doc.get("invoice_date"), "due_date": doc.get("due_date"), "currency": doc["currency"],
            "total": doc["total"], "total_usd": r.get("total_usd"), "service_period": doc.get("service_period"),
            "lines": [{"description": l["description"], "qty": l["qty"], "unit_price": l["unit_price"]}
                      for l in doc["lines"]],
            "remit_to": doc.get("remit_to"),
            "recommended_coding": {k: (r.get("coding") or {}).get(k) for k in ("account", "cost_centre", "confidence")},
            "flags": [{"code": f["code"], "severity": f["severity"], "detail": f["detail"]} for f in r["flags"]]}


def fallback(r, calls, reason):
    holds = [f for f in r["flags"] if f["severity"] == "hold"] or r["flags"]
    summary = holds[0]["detail"] if holds else "No exception detail available."
    return {"summary": summary, "evidence": [{"text": c["summary"], "tool_call_id": c["id"]} for c in calls[:4]],
            "next_action": DEFAULT_ACTION.get(r["agent_status"], NEXT_ACTIONS[-1]), "confidence": 0.5,
            "source": "template", "reason": reason}


def _validate(answer, call_ids):
    if not isinstance(answer, dict) or answer.get("next_action") not in NEXT_ACTIONS or not answer.get("summary"):
        raise ValueError("Answer failed the schema")
    answer["evidence"] = [e for e in answer.get("evidence", []) if e.get("tool_call_id") in call_ids]
    answer["confidence"] = max(0.0, min(1.0, float(answer.get("confidence", 0.5))))
    return answer


def investigate(ctx, r):
    """Run inside the supervisor's 'investigate' step; every tool call is recorded on the run."""
    case = case_file(r)
    key = llm._key(case, llm.MODEL, PROMPT_VERSION, SYSTEM)
    cached = llm._cache_get(llm.CACHE / "investigations", key)
    step_calls = []

    def run_tool(name, args):
        try:
            result = ctx.call(name, **args)
            tc = ctx.last_call
            step_calls.append(tc)
            return tc, json.dumps(result, default=str)[:6000], False
        except Exception as e:
            tc = ctx.last_call
            step_calls.append(tc)
            return tc, f"Error: {type(e).__name__}: {e}", True

    if cached:
        # Replay the same read-only calls so the run shows the full trail, then remap the cited ids.
        ids = []
        for c in cached["calls"]:
            tc, _, _ = run_tool(c["tool"], c["args"])
            ids.append(tc["id"])
        remap = {old: new for old, new in zip(cached["call_ids"], ids)}
        answer = dict(cached["answer"])
        answer["evidence"] = [{**e, "tool_call_id": remap.get(e["tool_call_id"], e["tool_call_id"])}
                              for e in answer["evidence"]]
        return {**answer, "source": "cache", "model": cached["meta"].get("model"), "tool_calls": ids}
    if not llm.live_enabled():
        return {**fallback(r, step_calls, "Replay mode and no cached investigation"), "tool_calls": []}

    tools = _tool_defs(ctx.registry)
    messages = [{"role": "user", "content": "Case file:\n" + json.dumps(case, indent=1, default=str)}]
    t0 = time.time()
    used, record = 0, []
    try:
        client = llm._client()
        while True:
            budget_left = used < MAX_CALLS and time.time() - t0 < DEADLINE_S
            response = client.beta.messages.create(
                model=llm.MODEL, max_tokens=8000, betas=[llm.FALLBACK_BETA], fallbacks="default",
                system=SYSTEM, tools=tools, tool_choice={"type": "auto" if budget_left else "none"},
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": ANSWER_SCHEMA}},
                messages=messages)
            ctx.add_tokens({"input_tokens": response.usage.input_tokens,
                            "output_tokens": response.usage.output_tokens})
            if response.stop_reason == "refusal":
                raise RuntimeError("Model declined the request")
            uses = [b for b in response.content if b.type == "tool_use"]
            if response.stop_reason != "tool_use" or not uses:
                text = next(b.text for b in response.content if b.type == "text")
                answer = _validate(json.loads(text), {c["id"] for c in step_calls})
                meta = {"model": response.model, "latency_ms": round((time.time() - t0) * 1000)}
                llm._cache_put(llm.CACHE / "investigations", key, {
                    "answer": {k: answer[k] for k in ("summary", "evidence", "next_action", "confidence")},
                    "calls": record, "call_ids": [c["id"] for c in step_calls], "meta": meta})
                return {**answer, "source": "live", **meta, "tool_calls": [c["id"] for c in step_calls]}
            messages.append({"role": "assistant", "content": response.content})
            results = []
            for b in uses:
                name = b.name.replace("_", ".", 1)
                if name not in LLM_TOOLS or used >= MAX_CALLS:
                    results.append({"type": "tool_result", "tool_use_id": b.id, "is_error": True,
                                    "content": "Tool not available or call budget used. Answer now."})
                    continue
                used += 1
                tc, content, is_error = run_tool(name, dict(b.input))
                record.append({"tool": name, "args": dict(b.input)})
                results.append({"type": "tool_result", "tool_use_id": b.id, "is_error": is_error,
                                "content": f"[{tc['id']}] {content}"})
            messages.append({"role": "user", "content": results})
    except Exception as e:  # the run never fails on the investigator
        return {**fallback(r, step_calls, f"{type(e).__name__}: {e}"), "tool_calls": [c["id"] for c in step_calls]}
