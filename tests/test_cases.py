"""Anomaly cases: worked to an exported, SoD-approved correction or dismissed with a reason."""
import csv
import io
import os
import tempfile

os.environ["DEMO_MODE"] = "replay"
os.environ.setdefault("STATE_DB", os.path.join(tempfile.mkdtemp(), "state.db"))

import pytest  # noqa: E402

from backend.service import DemoService  # noqa: E402

PREPARER, CONTROLLER, CASH_PREP, CASH_LEAD = "E35123", "E30233", "E35053", "E30719"


@pytest.fixture()
def svc():
    s = DemoService()
    s.reset()
    return s


def laptop(svc):
    return next(c for c in svc.cases.all() if "Laptop refresh" in c["finding"]["description"])


def test_every_finding_is_a_case_with_a_drafted_fix(svc):
    cases = svc.cases.all()
    assert {c["source"] for c in cases} == {"journals", "ap_ledger", "cash"}
    c = laptop(svc)
    assert c["status"] == "Open" and c["owner"] == PREPARER and c["fix"]["kind"] == "reclass"
    dr = sum(l["dr"] for l in c["fix"]["lines"])
    assert dr == sum(l["cr"] for l in c["fix"]["lines"]) == 36_900
    assert c["fix"]["lines"][0]["account"] == "1540"


def test_reclass_is_prepared_approved_and_exported_as_balanced_gl_interface(svc):
    cid = laptop(svc)["case_id"]
    svc.cases.prepare(cid, PREPARER, "Laptops are capital hardware")
    svc.cases.approve(cid, CONTROLLER)
    meta = svc.cases.export("gl", CONTROLLER)
    assert meta["totals"]["debits"] == meta["totals"]["credits"]
    rows = list(csv.DictReader(io.StringIO(svc.cases.batch_csv(meta["batch"]))))
    assert {r["SEGMENT3"] for r in rows} >= {"1540", "6420"} and rows[0]["GROUP_ID"] == meta["batch"]
    assert svc.cases.get(cid)["status"] == "Exported"


def test_preparer_cannot_approve_their_own_correction(svc):
    cid = laptop(svc)["case_id"]
    svc.cases.prepare(cid, PREPARER)
    with pytest.raises(PermissionError):
        svc.cases.approve(cid, PREPARER)


def test_original_poster_cannot_prepare_the_fix(svc):
    c = laptop(svc)
    poster = next(pid for pid, p in svc.s.people.items() if p["name"] == c["finding"]["created_by"])
    with pytest.raises(PermissionError):
        svc.cases.prepare(c["case_id"], poster)


def test_export_refuses_when_nothing_is_approved(svc):
    with pytest.raises(ValueError):
        svc.cases.export("gl", CONTROLLER)


def test_misapplied_cash_is_reapplied_to_the_named_customer(svc):
    c = next(c for c in svc.cases.all() if c["type"] == "MISAPPLIED")
    assert [l["action"] for l in c["fix"]["lines"]] == ["UNAPPLY", "APPLY"]
    assert c["fix"]["lines"][1]["customer"] == "30418"
    svc.cases.prepare(c["case_id"], CASH_PREP)
    svc.cases.approve(c["case_id"], CASH_LEAD)
    rows = list(csv.DictReader(io.StringIO(svc.cases.batch_csv(svc.cases.export("cash", CASH_LEAD)["batch"]))))
    assert ("APPLY", "30418", "9100231877") in {(r["ACTION"], r["CUSTOMER_NUMBER"], r["TRX_NUMBER"]) for r in rows}


def test_bulk_prepares_only_high_confidence_matches(svc):
    done = svc.cases.bulk_prepare(CASH_PREP, 0.95)["prepared"]
    assert done and all(svc.cases.get(c)["confidence"] >= 0.95 for c in done)


def test_dismissed_as_valid_suppresses_the_pattern(svc):
    ap = next(c for c in svc.cases.all() if c["source"] == "ap_ledger")
    before = len(svc.cases.all())
    svc.cases.dismiss(ap["case_id"], PREPARER, "valid_as_posted", "Agreed with the business")
    assert svc.cases.get(ap["case_id"])["status"] == "Dismissed"
    assert len(svc.cases.all()) <= before


def test_approved_ap_reclass_teaches_the_coding_engine(svc):
    ap = next(c for c in svc.cases.all() if c["source"] == "ap_ledger")
    svc.cases.prepare(ap["case_id"], PREPARER)
    svc.cases.approve(ap["case_id"], CONTROLLER)
    assert any("HISTORY_UPDATED" == e["kind"] for e in svc.audit(ap["case_id"]))


def test_close_dashboard_counts_value_at_risk(svc):
    d = svc.cases.dashboard()
    assert d["by_source"]["journals"]["open"] >= 4 and d["by_source"]["cash"]["value_at_risk"] > 0


def test_case_investigation_falls_back_without_a_model(svc):
    out = svc.investigate_case(laptop(svc)["case_id"], CONTROLLER)
    assert out["next_action"] == "Approve the proposed reclass" and out["source"] == "template"
