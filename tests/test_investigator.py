"""The investigator's guardrails: tool budget, schema, cited evidence, cache replay, and fallback."""
import json
import os
import tempfile
from types import SimpleNamespace as NS

os.environ["DEMO_MODE"] = "replay"
os.environ.setdefault("STATE_DB", os.path.join(tempfile.mkdtemp(), "state.db"))
os.environ["CACHE_DIR"] = tempfile.mkdtemp()  # investigations written here, never into data/cache

import pytest  # noqa: E402

from backend import llm  # noqa: E402
from backend.agents import investigator as inv  # noqa: E402
from backend.service import DemoService  # noqa: E402


def text(payload):
    return NS(type="text", text=json.dumps(payload) if not isinstance(payload, str) else payload)


def tool_use(i, name="vendor_profile", args=None):
    return NS(type="tool_use", id=f"toolu_{i}", name=name, input=args or {"vendor_id": "V4120"})


class FakeClient:
    """Calls a tool on every turn it is allowed to; answers once tool_choice is none."""

    def __init__(self, final):
        self.final = final
        self.calls = 0
        self.beta = NS(messages=NS(create=self.create))

    def create(self, **kw):
        self.calls += 1
        usage = NS(input_tokens=100, output_tokens=20)
        if kw["tool_choice"]["type"] == "none":
            return NS(content=[text(self.final(kw))], stop_reason="end_turn", usage=usage, model="fake")
        return NS(content=[tool_use(self.calls, "vendor_bank_change_log"), tool_use(self.calls + 100)],
                  stop_reason="tool_use", usage=usage, model="fake")


@pytest.fixture()
def svc(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "CACHE", tmp_path)
    s = DemoService()
    s.reset()
    return s


def _cited(kw):
    last = kw["messages"][-1]["content"]
    first_id = last[0]["content"][1:4]
    return {"summary": "Bank details changed from a look-alike domain.", "next_action": "Reject as suspected fraud",
            "confidence": 0.9, "evidence": [{"text": "Change log", "tool_call_id": first_id},
                                           {"text": "Invented", "tool_call_id": "T99"}]}


def test_budget_caps_tool_calls_and_uncited_evidence_is_dropped(svc, monkeypatch):
    fake = FakeClient(_cited)
    monkeypatch.setattr(llm, "live_enabled", lambda: True)
    monkeypatch.setattr(llm, "_client", lambda: fake)
    r = svc.run(svc.by_key["bank_change"])
    i = r["investigation"]
    step = next(s for s in r["trace"] if s["key"] == "investigate")
    assert i["source"] == "live" and len(step["tool_calls"]) == inv.MAX_CALLS
    assert [e["tool_call_id"] for e in i["evidence"]] == [step["tool_calls"][-2]["id"]]


def test_invalid_answer_falls_back_without_failing_the_run(svc, monkeypatch):
    monkeypatch.setattr(llm, "live_enabled", lambda: True)
    monkeypatch.setattr(llm, "_client", lambda: FakeClient(lambda kw: "not json"))
    r = svc.run(svc.by_key["duplicate"])
    assert r["investigation"]["source"] == "template" and r["agent_status"] == "HELD"
    assert r["investigation"]["next_action"] in inv.NEXT_ACTIONS


def test_answer_outside_the_action_list_is_rejected(svc, monkeypatch):
    bad = lambda kw: {"summary": "x", "next_action": "Pay it now", "confidence": 1, "evidence": []}  # noqa: E731
    monkeypatch.setattr(llm, "live_enabled", lambda: True)
    monkeypatch.setattr(llm, "_client", lambda: FakeClient(bad))
    assert svc.run(svc.by_key["bank_change"])["investigation"]["source"] == "template"


def test_cached_investigation_replays_its_tool_calls(svc, monkeypatch):
    monkeypatch.setattr(llm, "live_enabled", lambda: True)
    monkeypatch.setattr(llm, "_client", lambda: FakeClient(_cited))
    first = svc.run(svc.by_key["bank_change"])["investigation"]
    monkeypatch.setattr(llm, "_client", lambda: (_ for _ in ()).throw(AssertionError("no model call on replay")))
    again = svc.run(svc.by_key["bank_change"])
    i = again["investigation"]
    step = next(s for s in again["trace"] if s["key"] == "investigate")
    assert i["source"] == "cache" and i["summary"] == first["summary"]
    assert {e["tool_call_id"] for e in i["evidence"]} <= {c["id"] for c in step["tool_calls"]}


def test_only_exceptions_are_investigated(svc):
    assert svc.run(svc.by_key["telecoms"])["investigation"] is None
    assert svc.run(svc.by_key["unknown_vendor"])["investigation"]["next_action"] == "Send to supplier onboarding"
