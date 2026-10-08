"""Engagement letters, rate cards, matter budgets and statements of work: what "is the price right?" is checked against."""
import zlib
from collections import defaultdict

from .catalog import LEGAL_MATTERS

LEGAL_ROLES = {"Partner": 980.0, "Senior Associate": 650.0, "Associate": 520.0, "Paralegal": 225.0}
CONSULTING_ROLES = {"Partner": 650.0, "Principal": 475.0, "Senior Consultant": 340.0, "Consultant": 260.0}
HARTWELL_RATES = {"Partner": 1_100.0, "Senior Associate": 720.0, "Associate": 575.0, "Paralegal": 240.0}


def _scale(vendor_id):
    return 0.85 + (zlib.crc32(vendor_id.encode()) % 31) / 100


def build_contracts(vendors, invoices, hb, people, queue):
    general_counsel = next(p for p in people if p["cost_centre"] == "CC5100" and p["level"] in ("VP", "SVP", "Director"))
    procurement = next(p for p in people if p["cost_centre"] == "CC7180" and p["level"] != "Staff")
    rate_variance = next((q for q in queue if q.get("storyboard_key") == "rate_variance"), None)

    letters = []
    for v in vendors:
        if v["category"] not in ("legal", "consulting"):
            continue
        base = LEGAL_ROLES if v["category"] == "legal" else CONSULTING_ROLES
        if v["vendor_id"] == "V2007":
            rates = dict(HARTWELL_RATES)
        elif rate_variance and v["vendor_id"] == rate_variance["vendor_hint"]:
            rates = dict(LEGAL_ROLES)
        else:
            k = _scale(v["vendor_id"])
            rates = {role: round(r * k / 5) * 5 for role, r in base.items()}
        letters.append({
            "engagement_letter": f"EL-{v['vendor_id']}-2025", "vendor_id": v["vendor_id"], "vendor": v["name"],
            "kind": "Engagement letter" if v["category"] == "legal" else "Master services agreement",
            "effective_from": "2025-01-01", "effective_to": "2027-12-31",
            "signed_by": (general_counsel if v["category"] == "legal" else procurement)["id"],
            "rates": [{"role": role, "hourly_rate_usd": rate} for role, rate in rates.items()],
            "billing_terms": "Hourly, billed monthly in arrears; disbursements at cost; no rate increase before "
                             "1 Jan 2027 without written approval.",
        })

    billed = defaultdict(float)
    for inv in invoices:
        if inv.get("matter"):
            billed[inv["matter"]] += inv["total_usd"]
    budgets = []
    for code, desc, area in LEGAL_MATTERS:
        to_date = round(billed[code], 2)
        if code == "M-2207":
            budget = round((to_date + 86_500) / 0.82, -3)
        else:
            budget = round(to_date * 1.5 + 40_000, -3)
        budgets.append({"matter": code, "description": desc, "practice_area": area,
                        "requesting_lawyer_id": hb.matter_lawyer[code], "budget_usd": budget,
                        "billed_to_date_usd": to_date, "budget_period": "Life of matter"})

    sows = [{"sow": "SOW-BPA-0926", "vendor_id": "V5031", "description": "Finance process-mapping workshop",
             "pricing": "Fixed fee", "fixed_fee_usd": 14_200.00, "signed_on": "2026-09-08",
             "owner": next(p for p in people if p["name"] == "Diana Moreno")["id"]}]
    return {"engagement_letters": letters, "matter_budgets": budgets, "statements_of_work": sows}
