"""Golden cases: the storyboard outcomes the demo depends on. A failure here blocks deploy."""
import os
import tempfile

os.environ["DEMO_MODE"] = "replay"
os.environ.setdefault("STATE_DB", os.path.join(tempfile.mkdtemp(), "state.db"))

import pytest  # noqa: E402

from backend.service import DemoService  # noqa: E402


@pytest.fixture(scope="module")
def svc():
    s = DemoService()
    s.reset()
    return s


@pytest.fixture(scope="module")
def story(svc):
    return {k: svc.result(iid) for k, iid in svc.by_key.items()}


def codes(r):
    return {f["code"] for f in r["flags"]}


def test_telecoms_fast_track(story):
    r = story["telecoms"]
    assert r["coding"]["account"] == "6310" and r["coding"]["cost_centre"] == "CC4420"
    assert r["coding"]["confidence"] >= 0.9 and r["agent_status"] == "FAST_TRACK"
    assert r["receipt"]["rule"] == "standing"
    assert r["approval"]["steps"][-1]["role"] == "director"


def test_dell_override_capitalise_po_breach(story):
    r = story["dell"]
    c = r["coding"]
    assert c["account"] == "1540" and c["default_contrast"]["vendor_default"] == "6420"
    assert c["default_contrast"]["invoices_coded_to_recommended"] == 55
    assert c["default_contrast"]["past_miscodes_reclassified"] == 3
    assert {"PO_POLICY", "CAPITALISE", "DEFAULT_OVERRIDE"} <= codes(r)
    roles = [s["role"] for s in r["approval"]["steps"]]
    assert roles[:2] == ["it_procurement", "fixed_assets"]
    assert r["capitalisation"]["units"] == 10


def test_legal_requester_and_legal_ops_first(story):
    r = story["legal"]
    assert r["coding"]["account"] == "6610"
    assert r["requester"]["person"]["name"] == "Julia Ortiz" and r["requester"]["source"] == "Legal matter register"
    assert r["approval"]["steps"][0]["role"] == "legal_ops"
    assert r["status"] == "AWAITING_CONFIRMATION"


def test_saas_prepaid_with_twelve_month_schedule(story):
    r = story["saas"]
    assert r["coding"]["account"] == "1310"
    assert r["amortisation"]["months"] == 12 and r["amortisation"]["monthly_amount"] == 10_000
    assert r["approval"]["steps"][-1]["role"] == "vp"
    assert "AMOUNT_VS_NORM" not in codes(r)


def test_duplicate_held(story):
    r = story["duplicate"]
    assert r["agent_status"] == "HELD" and "DUPLICATE" in codes(r)


def test_bank_change_held(story):
    r = story["bank_change"]
    assert r["agent_status"] == "HELD" and "PAYMENT_RISK" in codes(r)
    risk = {f["code"] for f in r["risk"]["flags"]}
    assert {"AMOUNT_VS_NORM", "RECENT_BANK_CHANGE", "LOOKALIKE_DOMAIN"} <= risk
    assert "SOD_REROUTE" not in codes(r)


def test_sod_reroute_to_vp(story):
    r = story["sod"]
    assert "SOD_REROUTE" in codes(r) and "PO_POLICY" not in codes(r)
    assert r["approval"]["steps"][-1]["person"]["name"] == "Grace Okafor"


def test_extra_controls(story):
    assert story["eu_vat"]["agent_status"] == "HELD" and "VAT_INVALID" in codes(story["eu_vat"])
    assert story["open_po"]["agent_status"] == "MATCH_TO_PO"
    assert story["unknown_vendor"]["agent_status"] == "VENDOR_ONBOARDING"
    assert "PO_POLICY" in codes(story["po_breach_marketing"])


def test_anomaly_layer_finds_planted_items(svc):
    a = svc.anomalies()
    top = a["journals"]["flags"][0]
    assert "Laptop refresh" in top["description"] and top["suggested_account"] == "1540"
    types = {f["type"] for f in a["journals"]["flags"]}
    assert {"MISCODED", "DUPLICATE_ENTRY", "SELF_APPROVED"} <= types
    cash = {f["type"] for f in a["cash"]["flags"]}
    assert {"MISAPPLIED", "DOUBLE_APPLICATION"} <= cash
    assert len(a["cash"]["flags"]) == 2


def test_receipt_approval_and_export_flow(svc):
    iid = svc.by_key["legal"]
    svc.confirm_receipt(iid, "E31188", "Delivered")
    r = svc.submit(iid, "accept", "E34120")
    for pid in r["decision"]["chain"]:
        r = svc.approve_step(iid, pid)
    assert r["status"] == "APPROVED"
    headers, lines = svc.export_ap()
    assert "0098" in headers and "US01.5100.6610" in lines


def test_override_teaches_the_next_invoice(svc):
    first, second = svc.by_key["learning_1"], svc.by_key["learning_2"]
    before = svc.result(second)["coding"]["lines"][0]["rec"]
    svc.submit(first, "override", "E34120", "Chargers are for IT end-user laptops",
               {"account": "6360", "cost_centre": "CC4410"})
    after = svc.result(second)["coding"]["lines"][0]["rec"]
    assert after["cost_centre"] == "CC4410" and after["confidence"] > before["confidence"]


def test_every_invoice_opens_from_cache(svc):
    """Opening an invoice must not wait on a live model call: run `scripts.precompute` with a key after any change."""
    svc.reset()
    misses = []
    for iid in svc.items:
        r = svc.result(iid)
        if r["explanation_meta"]["source"] != "cache":
            misses.append((iid, "reason"))
        if r.get("pdf") and r["extraction"]["source"] != "cache":
            misses.append((iid, "extraction"))
    assert not misses, f"{len(misses)} uncached model calls, e.g. {misses[:5]}"
