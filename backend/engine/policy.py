"""Policy: requester, receipt confirmation, approval routing (DoA + SoD), PO policy, open-PO match."""
from collections import Counter
from datetime import date, timedelta

from rapidfuzz import fuzz, process

from .text import TfIdfIndex

ROLE_LABEL = {"legal_ops": "Legal Operations", "it_procurement": "IT Procurement",
              "fixed_assets": "Fixed Asset Accounting", "cost_centre_owner": "Cost-centre owner",
              "director": "Director", "vp": "VP", "svp": "SVP / CFO"}


class Policy:
    def __init__(self, store):
        self.s = store
        self.p = store.policies
        self.specialists = {p["specialist_role"]: p["id"] for p in store.people.values() if p.get("specialist_role")}
        self.names = {pid: p["name"] for pid, p in store.people.items()}
        self.svp = next(pid for pid, p in store.people.items() if p["title"] == "Chief Financial Officer")

    # ---------- requester ----------
    def identify_requester(self, vendor_id, doc, cc=None):
        matter = doc.get("matter")
        if matter and matter in self.s.matters:
            m = self.s.matters[matter]
            pid = m["requesting_lawyer_id"]
            prior = [i for i in self.s.history_by_vendor.get(vendor_id, []) if i.get("matter") == matter]
            return {"person": self.s.person_brief(pid), "source": "Legal matter register",
                    "evidence": f"Matter {matter} \"{m['description']}\" is registered to "
                                f"{self.names[pid]}; {len(prior)} earlier invoice(s) on this matter were "
                                f"requested by them."}
        for field in ("ordered_by", "prepared_for", "client_contact", "attention"):
            text = doc.get(field)
            if not text:
                continue
            name = text.split(",")[0].strip()
            hit = process.extractOne(name, self.names, scorer=fuzz.WRatio, score_cutoff=86)
            if hit:
                _n, score, pid = hit
                return {"person": self.s.person_brief(pid), "source": f"Named on invoice ({field.replace('_', ' ')})",
                        "evidence": f"Invoice names \"{text}\"; matched to {self.names[pid]} "
                                    f"({self.s.people[pid]['title']}) at {score:.0f}% similarity."}
        invs = self.s.history_by_vendor.get(vendor_id, [])[-12:]
        if not invs:
            return {"person": None, "source": "Not identified", "evidence": "No history for this supplier."}
        c = Counter(i["requester_id"] for i in invs if not cc or any(l["cc"] == cc for l in i["lines"]))
        if not c:
            c = Counter(i["requester_id"] for i in invs)
        pid, n = c.most_common(1)[0]
        return {"person": self.s.person_brief(pid), "source": "Coding history",
                "evidence": f"{self.names[pid]} requested {n} of the last {sum(c.values())} invoices from this "
                            f"supplier."}

    # ---------- receipt confirmation ----------
    def receipt_requirement(self, vendor_id, total_usd, as_of):
        v = self.s.vendors[vendor_id]
        risk = self.p["risk"]
        if v["category"] in risk["standing_receipt_categories"]:
            cutoff = (date.fromisoformat(as_of) - timedelta(days=190)).isoformat()
            recent = [i["total_usd"] for i in self.s.history_by_vendor.get(vendor_id, []) if i["invoice_date"] >= cutoff]
            if len(recent) >= 3:
                avg = sum(recent) / len(recent)
                dev = abs(total_usd - avg) / avg
                if dev <= risk["standing_receipt_tolerance"]:
                    return {"required": False, "rule": "standing",
                            "detail": f"Recurring {v['category_label'].lower()} supplier; amount is {dev:.1%} from the "
                                      f"6-month average of ${avg:,.0f}. Standing rule: approval doubles as receipt "
                                      f"confirmation."}
                return {"required": True, "rule": "standing_exceeded",
                        "detail": f"Recurring supplier but amount is {dev:.0%} from the 6-month average of "
                                  f"${avg:,.0f} (tolerance {risk['standing_receipt_tolerance']:.0%}): requester must "
                                  f"confirm."}
        return {"required": True, "rule": "requester",
                "detail": "No PO and no goods receipt: the requester's confirmation is the evidence of receipt."}

    # ---------- approval routing ----------
    def route(self, amount_usd, category, cc, requester_id):
        cc_rec = self.s.cost_centres[cc]
        steps = []
        overrides = []
        for ov in self.p["approval_matrix"]["category_overrides"]:
            if ov["category"] == category and amount_usd >= ov["min"]:
                overrides.append(ov["label"])
                for role in ov["first_approver"]:
                    pid = self.specialists[role]
                    steps.append({"role": role, "role_label": ROLE_LABEL[role], "person": self.s.person_brief(pid),
                                  "basis": ov["label"], "skipped": []})
        tiers = self.p["approval_matrix"]["tiers"]
        tier = next(t for t in tiers if amount_usd >= t["min"] and (t["max"] is None or amount_usd < t["max"]))
        ladder = [("cost_centre_owner", cc_rec["owner_id"]), ("director", cc_rec["director_id"]),
                  ("vp", cc_rec["vp_id"]), ("svp", self.svp)]
        start = ["cost_centre_owner", "director", "vp"].index(tier["approver"])
        skipped = []
        sod_reroute = None
        for role, pid in ladder[start:]:
            person = self.s.people[pid]
            if pid == requester_id:
                why = f"{person['name']} is the requester. Separation of duties: nobody approves their own spend."
                skipped.append({"person": self.s.person_brief(pid), "role": ROLE_LABEL[role], "reason": why,
                                "rule": "SoD"})
                sod_reroute = why
                continue
            limit = person["approval_limit"]
            if limit is not None and limit < amount_usd:
                skipped.append({"person": self.s.person_brief(pid), "role": ROLE_LABEL[role],
                                "reason": f"Approval limit ${limit:,.0f} is below ${amount_usd:,.0f}.",
                                "rule": "DoA"})
                continue
            if person.get("out_of_office"):
                delegate = self.s.people.get(person["delegate_id"])
                skipped.append({"person": self.s.person_brief(pid), "role": ROLE_LABEL[role],
                                "reason": f"Out of office; delegated to {delegate['name']}.", "rule": "Delegate"})
                pid, person = delegate["id"], delegate
            steps.append({"role": role, "role_label": ROLE_LABEL[role], "person": self.s.person_brief(pid),
                          "basis": tier["label"], "skipped": skipped})
            break
        return {"steps": steps, "tier": tier["label"], "category_rules": overrides, "sod_reroute": sod_reroute,
                "limit_check": f"Final approver limit "
                               f"{'unlimited' if steps[-1]['person']['approval_limit'] is None else '$' + format(steps[-1]['person']['approval_limit'], ',.0f')}"
                               f" ≥ ${amount_usd:,.0f}"}

    # ---------- PO policy ----------
    def po_policy(self, category, amount_usd, has_po_ref):
        for rule in self.p["po_policy"]["required"]:
            if rule["category"] == category and amount_usd >= rule["min"] and not has_po_ref:
                return {"breach": True, "rule": rule["label"],
                        "detail": f"Policy requires a PO ({rule['label']}). Processed, and logged to the "
                                  f"procurement non-compliance report."}
        exempt = category in self.p["po_policy"]["exempt"]
        return {"breach": False, "rule": "Exempt category" if exempt else "Below PO threshold",
                "detail": self.p["po_policy"]["exempt_label"] if exempt else "No PO required at this amount."}

    def open_po_match(self, vendor_id, subtotal, descriptions):
        pos = self.s.open_pos_by_vendor.get(vendor_id, [])
        if not pos:
            return None
        best = None
        idx = TfIdfIndex([" ".join(l["description"] for l in p["lines"]) for p in pos])
        sims = dict(idx.search(" ".join(descriptions), k=len(pos)))
        for i, p in enumerate(pos):
            open_amt = sum((l["qty"] - (l["qty_billed"] or 0)) * l["unit_price"] for l in p["lines"])
            amount_ok = abs(open_amt - subtotal) / max(subtotal, 1) <= 0.001 or \
                abs(p["amount"] - subtotal) / max(subtotal, 1) <= 0.001
            sim = sims.get(i, 0)
            score = (0.6 if amount_ok else 0) + 0.4 * sim
            if score >= 0.75 and (best is None or score > best["score"]):
                best = {"po_number": p["po_number"], "status": p["status"], "amount": p["amount"],
                        "open_amount": round(open_amt, 2), "created_date": p["created_date"],
                        "requester": self.s.person_brief(p["requester_id"]), "buyer": self.s.person_brief(p["buyer_id"]),
                        "description": p["lines"][0]["description"], "score": round(score, 2),
                        "similarity": round(sim, 2)}
        return best
