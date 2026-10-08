import json
from collections import defaultdict
from pathlib import Path

import pytest

SEED = Path(__file__).resolve().parent.parent / "data" / "seed"


def load(name):
    return json.loads((SEED / f"{name}.json").read_text())


@pytest.fixture(scope="module")
def data():
    return {n: load(n) for n in ("people", "vendors", "invoice_history", "purchase_orders", "journals_sep26",
                                 "cash_receipts_20261014", "ar_open_items", "intake_queue", "policies", "_truth",
                                 "receipt_evidence", "contracts", "reference")}


def test_requester_never_approves_own_spend(data):
    for inv in data["invoice_history"]:
        assert inv["requester_id"] not in {a["approver_id"] for a in inv["approval_chain"]}, inv["invoice_id"]


def test_final_approver_has_sufficient_limit(data):
    people = {p["id"]: p for p in data["people"]}
    for inv in data["invoice_history"]:
        final = people[inv["approval_chain"][-1]["approver_id"]]
        assert final["approval_limit"] is None or final["approval_limit"] >= inv["total_usd"], inv["invoice_id"]


def test_dell_history_supports_the_storyboard(data):
    dell = [i for i in data["invoice_history"] if i["vendor_id"] == "V1043"]
    assert len(dell) == 60
    hw = [i for i in dell if any((l["corrected_gl"] or l["gl"]) == "1540" for l in i["lines"])]
    service = [i for i in dell if all(l["gl"] == "6420" and l["coding"] == "ORIGINAL" for l in i["lines"]
                                      if l.get("line_type") != "TAX")]
    reclassed = [l for i in dell for l in i["lines"] if l["coding"] == "RECLASSIFIED"]
    assert len(hw) == 55 and len(service) == 5 and len(reclassed) == 3
    vendor = next(v for v in data["vendors"] if v["vendor_id"] == "V1043")
    assert vendor["default_gl"] == "6420"


def test_laptops_meet_per_unit_capitalisation_threshold(data):
    rule = next(r for r in data["policies"]["capitalisation"]["rules"] if r["account"] == "1540")
    planted = {(m["invoice_id"], m["line_no"]) for m in data["_truth"]["miscoded_lines"] if not m["reclassified"]}
    for inv in data["invoice_history"]:
        for l in inv["lines"]:
            if (l["corrected_gl"] or l["gl"]) == "1540" and (inv["invoice_id"], l["line_no"]) not in planted:
                assert l["unit_price"] >= rule["threshold_per_unit"], (inv["invoice_id"], l["description"])


def test_journals_balance_per_entry(data):
    totals = defaultdict(lambda: [0.0, 0.0])
    for j in data["journals_sep26"]:
        totals[j["je_id"]][0] += j["dr"]
        totals[j["je_id"]][1] += j["cr"]
    for je, (dr, cr) in totals.items():
        assert abs(dr - cr) < 0.02, je


def test_planted_anomalies_present(data):
    t = data["_truth"]
    jes = {j["je_id"] for j in data["journals_sep26"]}
    assert set(t["journal_planted"].values()) <= jes
    receipts = {r["receipt_id"]: r for r in data["cash_receipts_20261014"]}
    mis = receipts[t["cash_planted"]["misapplied"]]
    assert mis["applied_customer"] == "30481" and "9100231877" in mis["remittance"]
    ar = {a["ar_invoice"]: a for a in data["ar_open_items"]}
    assert ar["9100231877"]["customer_id"] == "30418" and ar["9100231877"]["status"] == "OPEN"


def test_cash_auto_apply_rate_matches_stated_volume(data):
    receipts = data["cash_receipts_20261014"]
    auto = sum(1 for r in receipts if r["status"] == "AUTO_APPLIED") / len(receipts)
    assert len(receipts) == 11_400 and 0.98 <= auto <= 0.99


def test_storyboard_intake_matches_brief(data):
    q = {x["storyboard_key"]: x["document"] for x in data["intake_queue"] if x["storyboard_key"]}
    assert len(data["intake_queue"]) == 142
    assert q["telecoms"]["total"] == 42_310.55
    assert q["dell"]["lines"][0]["qty"] == 10 and q["dell"]["lines"][0]["unit_price"] == 1_845.00
    assert q["legal"]["total"] == q["duplicate"]["total"] == 86_500.00
    assert q["saas"]["total"] == 120_000.00
    assert q["bank_change"]["total"] == 9_870.00
    assert q["sod"]["total"] == 14_200.00
    hp = [i["invoice_num"] for i in data["invoice_history"] if i["vendor_id"] == "V2007"]
    assert max(int(n) for n in hp) < 98


def test_summit_bank_change_unverified_and_recent(data):
    v = next(v for v in data["vendors"] if v["vendor_id"] == "V4120")
    last = v["bank_change_log"][-1]
    assert last["date"] == "2026-10-13" and last["callback_verified"] is False


MORNING_KEYS = {"telecoms", "dell", "saas", "duplicate", "bank_change", "sod", "eu_vat", "open_po", "unknown_vendor",
                "po_breach_marketing", "utility_spike", "learning_2", "split_cc", "split_entity", "cutoff", "use_tax",
                "discount_1", "discount_2", "rate_variance", "intercompany", "reimbursement"}


def test_storyboard_arrives_in_the_demo_morning_mailbox(data):
    q = {x["storyboard_key"]: x for x in data["intake_queue"] if x["storyboard_key"]}
    for key in MORNING_KEYS:
        assert "2026-10-15T06:00" <= q[key]["received_at"] <= "2026-10-15T09:00", key
    assert q["legal"]["received_at"][:10] == "2026-10-06" and q["learning_1"]["received_at"][:10] == "2026-10-13"
    late = [x for x in data["intake_queue"] if x["received_at"][:10] == "2026-10-15" and x["received_at"] > "2026-10-15T09:00"]
    assert not late, "nothing can arrive after the demo starts"


def test_hartwell_timekeeper_lines_match_the_brief(data):
    doc = next(x["document"] for x in data["intake_queue"] if x["storyboard_key"] == "legal")
    fees = [l for l in doc["lines"] if "hrs" in l["description"]]
    assert round(sum(l["qty"] for l in fees), 1) == 118.5
    assert round(sum(l["amount"] for l in fees), 2) == 84_950.00 and doc["total"] == 86_500.00
    letter = next(e for e in data["contracts"]["engagement_letters"] if e["engagement_letter"] == "EL-V2007-2025")
    card = {r["role"]: r["hourly_rate_usd"] for r in letter["rates"]}
    for l in fees:
        role = l["description"].split(" – ")[0]
        assert l["unit_price"] == card[role], role


def test_rate_variance_invoice_exceeds_its_card_on_one_role(data):
    q = next(x for x in data["intake_queue"] if x["storyboard_key"] == "rate_variance")
    letter = next(e for e in data["contracts"]["engagement_letters"] if e["vendor_id"] == q["vendor_hint"])
    card = {r["role"]: r["hourly_rate_usd"] for r in letter["rates"]}
    over = [l for l in q["document"]["lines"] if l["unit_price"] > card[l["description"].split(" – ")[0]]]
    assert [l["description"].split(" – ")[0] for l in over] == ["Senior Associate"]


def test_receipt_evidence_covers_the_storyboard(data):
    ev = {(e["vendor_id"], e["reference"]) for e in data["receipt_evidence"]}
    assert ("V1043", "OR-9918274") in ev and ("V3015", "OF-2026-114") in ev and ("V5031", "SOW-BPA-0926") in ev


def test_cutoff_invoice_is_september_service_and_unaccrued(data):
    q = next(x for x in data["intake_queue"] if x["storyboard_key"] == "cutoff")
    accrued = {j["reference"] for j in data["journals_sep26"] if j["category"] == "Accrual"}
    assert q["document"]["service_period"]["end"] == "2026-09-30" and q["vendor_hint"] not in accrued
    assert q["document"]["total"] >= data["policies"]["cutoff"]["materiality_usd"]


def test_use_tax_invoice_has_no_tax_on_taxable_goods(data):
    q = next(x for x in data["intake_queue"] if x["storyboard_key"] == "use_tax")
    v = next(v for v in data["vendors"] if v["vendor_id"] == q["vendor_hint"])
    assert q["document"]["tax"] == 0 and v["category"] in data["policies"]["tax"]["taxable_categories"]
    assert v["region"] != "MO"


def test_routed_out_documents_are_not_vendors(data):
    q = {x["storyboard_key"]: x for x in data["intake_queue"] if x["storyboard_key"]}
    names = {v["name"] for v in data["vendors"]}
    assert q["intercompany"]["document"]["intercompany_entity"] == "IN01"
    assert q["reimbursement"]["document"]["employee_id"] in {p["id"] for p in data["people"]}
    assert q["intercompany"]["document"]["vendor_name"] not in names


def test_close_calendar_has_september_closed(data):
    periods = {p["period"]: p for p in data["reference"]["close_calendar"]["periods"]}
    assert periods["SEP-26"]["status"] == "CLOSED" and periods["OCT-26"]["status"] == "OPEN"
