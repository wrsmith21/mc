"""The full non-PO process (brief section 2): every step built, not talked about."""
import os
import tempfile

os.environ["DEMO_MODE"] = "replay"
os.environ.setdefault("STATE_DB", os.path.join(tempfile.mkdtemp(), "state.db"))

import pytest  # noqa: E402

from backend import clock  # noqa: E402
from backend.service import DemoService  # noqa: E402


@pytest.fixture()
def svc():
    s = DemoService()
    s.reset()
    yield s
    clock.set_offset_hours(0)


def codes(r):
    return {f["code"] for f in r["flags"]}


def test_hartwell_rates_match_the_engagement_letter_and_budget_is_tracked(svc):
    r = svc.run(svc.by_key["legal"])
    card = r["price"]["rate_card"]
    assert card["letter"] == "EL-V2007-2025" and card["hours"] == 118.5 and not card["variances"]
    assert r["price"]["matter_budget"]["share_after"] == pytest.approx(0.82, abs=0.01)
    assert "RATE_VARIANCE" not in codes(r) and r["coding"]["confidence"] >= 0.9


def test_senior_associate_billed_over_card_is_flagged(svc):
    r = svc.run(svc.by_key["rate_variance"])
    assert "RATE_VARIANCE" in codes(r)
    v = r["price"]["rate_card"]["variances"]
    assert [x["role"] for x in v] == ["Senior Associate"] and v[0]["excess"] == pytest.approx(21.5 * 70)


def test_fixed_fee_matches_signed_sow(svc):
    r = svc.run(svc.by_key["sod"])
    assert r["price"]["sow"]["sow"] == "SOW-BPA-0926" and r["price"]["sow"]["matches_fee"]
    assert r["receipt"]["rule"] == "evidence"


def test_split_across_cost_centres_and_entities(svc):
    cc = svc.run(svc.by_key["split_cc"])["coding"]
    assert {s["cost_centre"] for s in cc["splits"]} == {"CC7100", "CC7110", "CC7160"}
    ent = svc.run(svc.by_key["split_entity"])
    assert {s["entity"] for s in ent["coding"]["splits"]} == {"US01", "EU01"} and "SPLIT" in codes(ent)


def test_unaccrued_september_service_is_reported_to_r2r(svc):
    r = svc.run(svc.by_key["cutoff"])
    assert "CUTOFF_UNACCRUED" in codes(r)
    assert r["cutoff"]["periods"] == ["SEP-26"] and r["cutoff"]["accrued_usd"] == 0


def test_accrued_september_service_relieves_the_accrual(svc):
    accrued = {j["reference"] for j in svc.s.journals if j["category"] == "Accrual"}
    iid = next(i for i, q in svc.items.items() if q.get("vendor_hint") in accrued
               and (q["document"].get("service_period") or {}).get("end") == "2026-09-30")
    r = svc.run(iid)
    assert r["cutoff"]["accrued_usd"] > 0 and "CUTOFF_UNACCRUED" not in codes(r)


def test_use_tax_accrued_on_untaxed_taxable_goods(svc):
    r = svc.run(svc.by_key["use_tax"])
    assert "USE_TAX" in codes(r)
    assert r["use_tax"]["amount_usd"] == pytest.approx(r["document"]["subtotal"] * 0.0845, abs=0.01)
    assert not svc.run(svc.by_key["dell"]).get("use_tax")


def test_early_payment_discount_is_offered_while_open(svc):
    r = svc.run(svc.by_key["discount_1"])
    d = r["payment"]["discount"]
    assert "DISCOUNT" in codes(r) and d["open"] and d["amount"] == pytest.approx(r["document"]["total"] * 0.02, abs=0.01)


def test_unconfirmed_receipt_reminds_then_escalates_then_contacts_supplier(svc):
    legal = svc.by_key["legal"]
    assert svc.result(legal)["receipt_task"]["status"] == "pending"
    stages = []
    for _ in range(12):
        stages += [e["stage"] for e in svc.advance_clock(24, "E34120")["sla_events"] if e["intake_id"] == legal]
    assert stages == ["reminder", "escalated", "supplier"]
    kinds = [e["kind"] for e in svc.audit(legal)]
    assert {"RECEIPT_REMINDER", "RECEIPT_ESCALATED", "SUPPLIER_CONTACTED"} <= set(kinds)


def test_callback_fraud_rejects_and_verified_releases(svc):
    bank = svc.by_key["bank_change"]
    svc.run(bank)
    assert any(w["intake_id"] == bank for w in svc.work()["vendor_review"])
    out = svc.callback("V4120", "fraud", "E30655", "Supplier confirms no change was requested")
    assert bank in out["invoices"] and svc.result(bank)["status"] == "REJECTED"


def test_callback_verified_clears_the_bank_change_hold(svc):
    bank = svc.by_key["bank_change"]
    svc.run(bank)
    svc.callback("V4120", "verified", "E30655", "New account confirmed with the supplier's controller")
    r = svc.result(bank)
    assert "PAYMENT_RISK" not in codes(r) and r["agent_status"] != "HELD"


def test_onboarding_creates_the_supplier_and_reruns(svc):
    iid = svc.by_key["unknown_vendor"]
    assert svc.run(iid)["agent_status"] == "VENDOR_ONBOARDING"
    r = svc.onboard(iid, "E30655", "43-1188270", "facilities")
    assert r["agent_status"] != "VENDOR_ONBOARDING" and r["vendor"]["vendor_id"].startswith("V98")
    assert r["coding"]["account"]


def test_blanket_po_request_is_recorded(svc):
    req = svc.request_po("V1102", "Standing approval rule", "E30876")
    assert svc.work()["po_requests"][0]["vendor_id"] == "V1102" and req["status"] == "Requested"
