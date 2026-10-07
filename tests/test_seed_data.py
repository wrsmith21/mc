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
                                 "cash_receipts_20261014", "ar_open_items", "intake_queue", "policies", "_truth")}


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
    assert last["date"] == "2026-10-12" and last["callback_verified"] is False
