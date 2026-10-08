"""Server-enforced roles: a person can only do what their role permits, and every refusal is audited."""
import os
import tempfile

os.environ["DEMO_MODE"] = "replay"
os.environ.pop("DEMO_PASSWORD", None)
os.environ.setdefault("STATE_DB", os.path.join(tempfile.mkdtemp(), "state.db"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend import app as app_module  # noqa: E402

AP, CONTROLLER, GL, ADMIN, KEVIN, JULIA, GRACE = "E34120", "E30233", "E35123", "E35051", "E33901", "E31188", "E10022"


@pytest.fixture()
def client():
    app_module.svc().reset()
    return TestClient(app_module.app)


def as_(client, pid):
    r = client.post("/api/session", json={"person_id": pid})
    assert r.status_code == 200
    return r.json()


def denied(client):
    return [e for e in client.get("/api/audit?kind=ACCESS_DENIED").json()["events"]]


def test_signed_in_person_and_roles(client):
    s = as_(client, CONTROLLER)
    assert "controller" in s["roles"] and "case_approve_journals" in s["can"] and "decide" not in s["can"]
    assert client.get("/api/session").json()["person"]["id"] == CONTROLLER


def test_only_ap_can_decide_and_refusal_is_audited(client):
    sv = app_module.svc()
    iid = sv.by_key["telecoms"]
    as_(client, AP)
    assert client.get(f"/api/invoices/{iid}/run").status_code == 200
    as_(client, KEVIN)
    r = client.post(f"/api/invoices/{iid}/decision", json={"action": "accept"})
    assert r.status_code == 403 and "AP specialist" in r.json()["detail"]
    assert denied(client)[0]["actor"] == KEVIN


def test_only_the_next_approver_can_approve(client):
    sv = app_module.svc()
    iid = sv.by_key["telecoms"]
    sv.run(iid)
    sv.submit(iid, "accept", AP)
    chain = sv.result(iid)["decision"]["chain"]
    outsider = GRACE if GRACE not in chain else CONTROLLER
    as_(client, outsider)
    assert client.post(f"/api/invoices/{iid}/approve", json={}).status_code == 403
    as_(client, chain[0])
    assert client.post(f"/api/invoices/{iid}/approve", json={}).status_code == 200


def test_only_the_requester_confirms_receipt(client):
    legal = app_module.svc().by_key["legal"]
    as_(client, KEVIN)
    assert client.post(f"/api/invoices/{legal}/receipt/confirm", json={"note": "x"}).status_code == 403
    as_(client, JULIA)
    assert client.post(f"/api/invoices/{legal}/receipt/confirm", json={"note": "Delivered"}).status_code == 200


def test_policy_changes_need_an_admin_and_mark_runs_stale(client):
    sv = app_module.svc()
    iid = sv.by_key["telecoms"]
    sv.run(iid)
    as_(client, AP)
    body = {"changes": {"risk.amount_vs_norm_multiple": 3}, "reason": "Fewer false holds on seasonal suppliers"}
    assert client.post("/api/policies", json=body).status_code == 403
    as_(client, ADMIN)
    r = client.post("/api/policies", json=body)
    assert r.status_code == 200 and r.json()["version"] == 2
    assert "Policy changed to version 2" in client.get(f"/api/invoices/{iid}").json()["stale"]
    versions = client.get("/api/policies").json()["versions"]
    assert versions[-1]["changes"][0]["before"] == 2.5 and versions[-1]["by"] == ADMIN


def test_another_instance_picks_up_a_policy_change(client):
    sv = app_module.svc()
    iid = sv.by_key["telecoms"]
    sv.run(iid)
    as_(client, ADMIN)
    body = {"changes": {"risk.amount_vs_norm_multiple": 3}, "reason": "Fewer false holds on seasonal suppliers"}
    assert client.post("/api/policies", json=body).status_code == 200
    sv.s.policy_version, sv.s.policies["risk"]["amount_vs_norm_multiple"], sv._gen = 1, 2.5, "before-the-change"
    assert "Policy changed to version 2" in client.get(f"/api/invoices/{iid}").json()["stale"]
    assert sv.s.policies["risk"]["amount_vs_norm_multiple"] == 3


def test_state_seeded_before_brief_rows_still_lists_and_summarises(client):
    sv = app_module.svc()
    worked = sum(1 for r in sv.queue() if r["status"] != "NEW")
    sv.state.conn.execute("DELETE FROM kv WHERE key LIKE 'brief:%' OR key = 'meta:briefs'")
    sv.state.conn.commit()
    sv._briefs_ok = False
    as_(client, AP)
    assert client.get("/api/summary").status_code == 200
    assert sum(1 for r in client.get("/api/queue").json() if r["status"] != "NEW") == worked


def test_policy_rejects_out_of_range_values(client):
    as_(client, ADMIN)
    r = client.post("/api/policies", json={"changes": {"risk.confidence_bands.review": 0.99}, "reason": "Testing bounds"})
    assert r.status_code == 409


def test_case_roles_are_enforced_over_http(client):
    sv = app_module.svc()
    cid = next(c["case_id"] for c in sv.cases.all() if "Laptop refresh" in c["finding"]["description"])
    as_(client, AP)
    assert client.post(f"/api/cases/{cid}/prepare", json={}).status_code == 403
    as_(client, GL)
    assert client.post(f"/api/cases/{cid}/prepare", json={"note": "Capital hardware"}).status_code == 200
    assert client.post(f"/api/cases/{cid}/approve", json={}).status_code == 403
    as_(client, CONTROLLER)
    assert client.post(f"/api/cases/{cid}/approve", json={}).status_code == 200


def test_evidence_pack_renders_the_record(client):
    sv = app_module.svc()
    iid = sv.by_key["dell"]
    sv.run(iid)
    html = client.get(f"/api/invoices/{iid}/evidence").text
    assert "SOX evidence pack" in html and "coding.recommend_line" in html and "1540" in html


def test_signed_requester_link_confirms_without_a_session(client):
    sv = app_module.svc()
    legal = sv.by_key["legal"]
    token = client.get(f"/api/invoices/{legal}").json()["requester_link_token"]
    phone = TestClient(app_module.app)  # a separate device, no session
    as_(client, AP)  # the presenter's laptop is signed in as someone else
    assert phone.post(f"/api/invoices/{legal}/receipt/confirm", json={"by": JULIA, "token": "forged.token"}).status_code == 403
    r = phone.post(f"/api/invoices/{legal}/receipt/confirm", json={"by": JULIA, "token": token, "note": "Delivered"})
    assert r.status_code == 200 and r.json()["status"] == "confirmed"
