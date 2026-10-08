"""The agent runtime: real runs with recorded tool calls, NEW until worked, decisions survive re-runs."""
import os
import tempfile

os.environ["DEMO_MODE"] = "replay"
os.environ.setdefault("STATE_DB", os.path.join(tempfile.mkdtemp(), "state.db"))

import pytest  # noqa: E402

from backend.service import MAILBOX_CUTOFF, DemoService  # noqa: E402


@pytest.fixture()
def svc():
    s = DemoService()
    s.reset()
    return s


def test_morning_mailbox_is_not_worked_until_the_agent_runs(svc):
    dell = svc.by_key["dell"]
    r = svc.result(dell)
    assert r["status"] == "NEW" and r["run"] is None and r["trace"] == []
    new = svc.new_invoices()
    assert dell in new and all(svc.items[i]["received_at"] >= MAILBOX_CUTOFF for i in new)
    worked = [i for i in svc.items if i not in new]
    assert all(svc.result(i)["run"]["trigger"] == "batch" for i in worked)


def test_every_step_records_its_tool_calls(svc):
    r = svc.run(svc.by_key["dell"])
    keys = [s["key"] for s in r["trace"]]
    assert keys == ["intake", "read", "supplier", "validity", "po", "coding", "treatment", "receipt", "risk",
                    "approval", "decide"]
    for step in r["trace"][1:]:
        assert step["tool_calls"], step["key"]
    tools = {c["tool"] for s in r["trace"] for c in s["tool_calls"]}
    assert {"vendor.resolve", "coding.recommend_line", "approval.route", "receipt.find_evidence"} <= tools
    assert r["run"]["tool_calls"] == sum(len(s["tool_calls"]) for s in r["trace"])
    assert r["run"]["trigger"] == "manual" and r["run"]["ms"] > 0


def test_events_stream_as_the_run_happens(svc):
    events = list(svc.run_events(svc.by_key["telecoms"]))
    kinds = [e["type"] for e in events]
    assert kinds[0] == "start" and kinds[-1] == "result"
    last_step = len(kinds) - 1 - kinds[::-1].index("step")
    assert kinds.index("tool") < last_step < kinds.index("result")
    assert kinds.count("stage") == kinds.count("step") == 11
    assert events[-1]["result"]["run"]["run_id"]


def test_receipt_evidence_replaces_a_confirmation_task(svc):
    r = svc.run(svc.by_key["dell"])
    assert r["receipt"]["rule"] == "evidence" and r["receipt"]["evidence"]["reference"] == "OR-9918274"
    assert r["status"] != "AWAITING_CONFIRMATION"


def test_rerun_keeps_the_decision_and_explains_what_changed(svc):
    legal = svc.by_key["legal"]
    first = svc.result(legal)
    assert first["status"] == "AWAITING_CONFIRMATION"
    svc.confirm_receipt(legal, first["requester"]["person"]["id"], "Delivered")
    svc.submit(legal, "accept", "E34120")
    events_before = len(svc.audit(legal))
    r = svc.run(legal)
    assert r["status"] == "IN_APPROVAL" and r["decision"]["status"] == "IN_APPROVAL"
    diff = r["run"]["diff"]
    assert any(d["field"] == "Status" for d in diff) and "Receipt confirmed" in diff[0]["cause"]
    assert len(r["runs"]) == 2 and r["run"]["previous_run_id"] == first["run"]["run_id"]
    assert len(svc.audit(legal)) > events_before


def test_routed_out_documents_stop_at_step_one(svc):
    ic = svc.run(svc.by_key["intercompany"])
    concur = svc.run(svc.by_key["reimbursement"])
    assert ic["agent_status"] == "ROUTED_OUT" and ic["flags"][0]["code"] == "ROUTE_INTERCOMPANY"
    assert concur["agent_status"] == "ROUTED_OUT" and concur["flags"][0]["code"] == "ROUTE_CONCUR"
    with pytest.raises(ValueError):
        svc.submit(svc.by_key["intercompany"], "accept", "E34120")


def test_mailbox_run_works_every_new_invoice(svc):
    events = list(svc.run_mailbox())
    done = events[-1]
    assert done["type"] == "done" and done["count"] == len([e for e in events if e["type"] == "invoice"])
    assert not svc.new_invoices()


def test_registry_describes_every_tool_with_a_contract(svc):
    tools = svc.agents()["tools"]
    assert len(tools) >= 18
    for t in tools:
        assert t["description"] and t["agent"] and t["input_schema"]["type"] == "object"
