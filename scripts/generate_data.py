"""Generate every synthetic dataset for the demo. Deterministic: same seed, same data.

    uv run python -m scripts.generate_data
"""
import json
import random
from collections import Counter
from pathlib import Path

from scripts.datagen import reference as ref
from scripts.datagen.cash import CashBuilder
from scripts.datagen.catalog import CATEGORIES, LEGAL_MATTERS
from scripts.datagen.history import HistoryBuilder
from scripts.datagen.intake import IntakeBuilder
from scripts.datagen.journals import JournalBuilder
from scripts.datagen.people import build_people
from scripts.datagen.vendors import build_vendors

SEED = 20261015
OUT = Path(__file__).resolve().parent.parent / "data" / "seed"


def write(name, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.json"
    path.write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False))
    return path.stat().st_size


def strip_private(rows):
    for row in rows:
        for k in [k for k in row if k.startswith("_")]:
            row.pop(k)
    return rows


def main():
    rng = random.Random(SEED)
    people, cost_centres, people_by_id = build_people(rng)
    vendors = build_vendors(rng)
    hb = HistoryBuilder(rng, vendors, people_by_id, cost_centres)
    invoices, pos = hb.build()
    jb = JournalBuilder(rng, invoices, pos, vendors, people_by_id, cost_centres)
    journals, journal_planted = jb.build()
    clerks = [p["id"] for p in people if p["cost_centre"] == "CC7170" and p["level"] == "Staff"]
    customers, ar, receipts, cash_planted = CashBuilder(rng, clerks).build()
    queue = IntakeBuilder(rng, hb, vendors, pos).build()

    truth = {
        "miscoded_lines": [
            {"invoice_id": i["invoice_id"], "line_no": l["line_no"], "posted_gl": l["gl"],
             "correct_gl": l["corrected_gl"], "reclassified": l["coding"] == "RECLASSIFIED"}
            for i in invoices for l in i["lines"] if l.get("_label") == "miscode"],
        "journal_planted": journal_planted,
        "cash_planted": cash_planted,
    }
    for inv in invoices:
        strip_private(inv["lines"])
    strip_private(invoices)
    strip_private(pos)
    vendor_norms = {}
    for v in vendors:
        totals = sorted(i["total_usd"] for i in invoices if i["vendor_id"] == v["vendor_id"])
        if totals:
            v["typical_invoice"] = {"median_usd": totals[len(totals) // 2], "p10_usd": totals[len(totals) // 10],
                                    "p90_usd": totals[min(len(totals) - 1, len(totals) * 9 // 10)],
                                    "invoices_18m": len(totals)}
        vendor_norms[v["vendor_id"]] = v.get("typical_invoice")
    strip_private(vendors)

    reference = {
        "demo_date": ref.DEMO_DATE.isoformat(), "history_window": [ref.HISTORY_START.isoformat(),
                                                                   ref.HISTORY_END.isoformat()],
        "entities": ref.ENTITIES, "segment_structure": ref.SEGMENT_STRUCTURE,
        "chart_of_accounts": [{"account": a, "name": n, "type": t, "statement": s}
                              for a, n, t, s in ref.CHART_OF_ACCOUNTS],
        "cost_centres": cost_centres,
        "categories": {k: {"label": c["label"], "gl": c["gl"], "freq": c["freq"]} for k, c in CATEGORIES.items()},
        "legal_matters": [{"matter": m, "description": d, "practice_area": a,
                           "requesting_lawyer_id": hb.matter_lawyer[m]} for m, d, a in LEGAL_MATTERS],
        "fx_monthly": ref.FX_MONTHLY,
    }
    policies = {"approval_matrix": ref.APPROVAL_MATRIX, "approval_limits": ref.APPROVAL_LIMITS,
                "capitalisation": ref.CAPITALISATION_POLICY, "po_policy": ref.PO_POLICY,
                "prepaid": ref.PREPAID_POLICY, "risk": ref.RISK_POLICY}

    sizes = {
        "reference": write("reference", reference), "policies": write("policies", policies),
        "people": write("people", people), "vendors": write("vendors", vendors),
        "invoice_history": write("invoice_history", invoices), "purchase_orders": write("purchase_orders", pos),
        "journals_sep26": write("journals_sep26", journals), "customers": write("customers", customers),
        "ar_open_items": write("ar_open_items", ar), "cash_receipts_20261014": write("cash_receipts_20261014", receipts),
        "intake_queue": write("intake_queue", queue), "_truth": write("_truth", truth),
    }

    lines = [l for i in invoices for l in i["lines"]]
    print(f"people {len(people)} | cost centres {len(cost_centres)} | vendors {len(vendors)}")
    print(f"invoices {len(invoices):,} | lines {len(lines):,} | spend ${sum(i['total_usd'] for i in invoices)/1e6:,.1f}M"
          f" | PO-backed {sum(1 for i in invoices if i['po_number'])/len(invoices):.0%}")
    print(f"miscoded lines {len(truth['miscoded_lines'])} "
          f"(reclassified {sum(1 for m in truth['miscoded_lines'] if m['reclassified'])})")
    print(f"POs {len(pos):,} | open {sum(1 for p in pos if p['status'] != 'CLOSED'):,}")
    print(f"journal lines {len(journals):,} | JEs {len({j['je_id'] for j in journals}):,}")
    print(f"customers {len(customers):,} | AR items {len(ar):,} | receipts {len(receipts):,} "
          f"{dict(Counter(r['status'] for r in receipts))}")
    print(f"intake queue {len(queue)} | storyboard {[q['storyboard_key'] for q in queue if q['storyboard_key']]}")
    print("sizes KB", {k: v // 1024 for k, v in sizes.items()})


if __name__ == "__main__":
    main()
