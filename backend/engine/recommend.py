"""Explainable GL / cost-centre recommendation from coding history.

score(account) = 0.60 * similar-line vote + 0.25 * vendor frequency + 0.15 * amount fit
Policy (capitalisation per unit, prepaid) is applied after scoring so the reason is visible.
"""
from collections import Counter, defaultdict
from datetime import date

from .text import TfIdfIndex, tokens

W_TEXT, W_VENDOR, W_AMOUNT = 0.60, 0.25, 0.15
SAME_VENDOR_WEIGHT, SAME_CATEGORY_WEIGHT, OTHER_WEIGHT = 1.0, 0.5, 0.15
MIN_SIM = 0.22
CLOSE_MATCH = 0.55  # only lines within 55% of the best similarity vote
MAX_CONFIDENCE = 0.98
MAX_LINES_PER_DESCRIPTION = 10  # stop one very common description out-voting closer matches
PREPAID_ACCOUNTS = {"1310", "1320"}


def months_between(start: str, end: str) -> int:
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    return (e.year - s.year) * 12 + e.month - s.month + 1


def month_end(d: date) -> date:
    nxt = date(d.year + d.month // 12, d.month % 12 + 1, 1)
    return date.fromordinal(nxt.toordinal() - 1)


class Recommender:
    def __init__(self, store):
        self.s = store
        groups = defaultdict(list)
        for i, l in enumerate(store.lines):
            groups[" ".join(t for t in tokens(l["description"]) if "_" not in t)].append(i)
        self.keys = list(groups.keys())
        self.key_lines = [groups[k] for k in self.keys]
        self.index = TfIdfIndex(self.keys)
        pol = store.policies
        self.cap_rules = {r["account"]: r for r in pol["capitalisation"]["rules"]}
        self.prepaid = pol["prepaid"]

    # ---------- evidence ----------
    def similar_lines(self, vendor_id, description):
        hits = self.index.search(description, k=60)
        if not hits:
            return []
        floor = max(MIN_SIM, hits[0][1] * CLOSE_MATCH)
        out = []
        for key_idx, sim in hits:
            if sim < floor:
                continue
            for li in self.key_lines[key_idx]:
                l = self.s.lines[li]
                out.append((li, sim, l["vendor_id"] == vendor_id, key_idx))
        return out

    def recommend_line(self, vendor_id, description, qty, unit_price, amount_usd, service_period=None,
                       requester_cc=None, as_of=None):
        lines = self.s.lines
        category = self.s.vendors[vendor_id]["category"]
        sims = self.similar_lines(vendor_id, description)
        votes = defaultdict(float)
        support = defaultdict(lambda: [0, 0, 0])  # gl -> [same vendor, same category, other]
        per_key = Counter()
        for li, sim, same, key_idx in sims:
            per_key[(key_idx, same)] += 1
            if per_key[(key_idx, same)] > MAX_LINES_PER_DESCRIPTION:
                continue
            gl = lines[li]["gl"]
            if gl in PREPAID_ACCOUNTS and lines[li]["amortise_to"]:
                gl = lines[li]["amortise_to"]
            if same:
                votes[gl] += sim * SAME_VENDOR_WEIGHT
                support[gl][0] += 1
            elif lines[li]["category"] == category:
                votes[gl] += sim * SAME_CATEGORY_WEIGHT
                support[gl][1] += 1
            else:
                votes[gl] += sim * OTHER_WEIGHT
                support[gl][2] += 1
        vtotal = sum(votes.values()) or 1.0
        text_share = {g: v / vtotal for g, v in votes.items()}

        vlines = [lines[i] for i in self.s.lines_by_vendor.get(vendor_id, [])]
        inv_gls = defaultdict(set)
        for l in vlines:
            inv_gls[l["invoice_id"]].add(l["amortise_to"] if l["gl"] in PREPAID_ACCOUNTS and l["amortise_to"]
                                         else l["gl"])
        vcount = Counter(g for gls in inv_gls.values() for g in gls)
        vfreq = {g: c / len(inv_gls) for g, c in vcount.items()} if inv_gls else {}

        candidates = set(text_share) | set(vfreq)
        if not candidates:
            return None
        scores, fits = {}, {}
        for g in candidates:
            ref = [lines[li]["unit_price"] for li, sim, same, _k in sims if lines[li]["gl"] == g or
                   lines[li]["amortise_to"] == g]
            if not ref:
                fit = 0.4
            else:
                lo, hi = min(ref), max(ref)
                fit = 1.0 if lo * 0.7 <= unit_price <= hi * 1.3 else 0.35
            fits[g] = fit
            scores[g] = W_TEXT * text_share.get(g, 0) + W_VENDOR * vfreq.get(g, 0) + W_AMOUNT * fit
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        top_gl, top_score = ranked[0]
        runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
        same_n, cat_n, other_n = support[top_gl]
        evidence_strength = min(1.0, same_n / 8 + cat_n / 30 + other_n / 100)
        share = top_score / (top_score + runner_up) if top_score + runner_up else 1.0
        confidence = top_score * (0.85 + 0.15 * evidence_strength) * (0.80 + 0.20 * share)
        confidence = round(min(MAX_CONFIDENCE, confidence), 3)

        account = top_gl
        policy_notes = []
        expense_account = top_gl
        cap = self.cap_rules.get(top_gl)
        capitalise = None
        if cap:
            if unit_price >= cap["threshold_per_unit"]:
                capitalise = {"asset_class": cap["asset_class"], "account": cap["account"],
                              "threshold_per_unit": cap["threshold_per_unit"], "unit_price": unit_price,
                              "useful_life_months": cap["useful_life_months"]}
                policy_notes.append(f"Unit price ${unit_price:,.2f} is at or above the ${cap['threshold_per_unit']:,} "
                                    f"per-unit threshold for {cap['asset_class']}: route to Fixed Asset Accounting.")
            else:
                account = cap["expense_account_below"]
                policy_notes.append(f"Unit price ${unit_price:,.2f} is below the ${cap['threshold_per_unit']:,} "
                                    f"per-unit threshold: expense to {account}.")

        amortisation = None
        if service_period and service_period.get("start") and service_period.get("end"):
            months = months_between(service_period["start"], service_period["end"])
            gl_period_end = month_end(date.fromisoformat(as_of)) if as_of else None
            extends_forward = gl_period_end is None or date.fromisoformat(service_period["end"]) > gl_period_end
            if months >= self.prepaid["min_service_months"] and amount_usd >= self.prepaid["min_amount"] \
                    and extends_forward and account not in self.cap_rules:
                prepaid_acct = self.prepaid["prepaid_account"]
                amortisation = {"prepaid_account": prepaid_acct, "expense_account": expense_account,
                                "months": months, "monthly_amount": round(amount_usd / months, 2),
                                "start": service_period["start"], "end": service_period["end"]}
                account = prepaid_acct
                policy_notes.append(f"Service period of {months} months and ${amount_usd:,.0f}: book to "
                                    f"{prepaid_acct} Prepaid and amortise ${amount_usd / months:,.2f}/month to "
                                    f"{expense_account}.")

        cc, cc_conf = self.recommend_cc(vendor_id, top_gl, sims, requester_cc)
        evidence = self.evidence(vendor_id, sims, top_gl)
        alternatives = [{"account": g, "name": self.s.coa.get(g, {}).get("name"), "score": round(s, 3),
                         "text_vote": round(text_share.get(g, 0), 3), "vendor_freq": round(vfreq.get(g, 0), 3)}
                        for g, s in ranked[:4]]
        return {
            "account": account, "account_name": self.s.coa.get(account, {}).get("name"),
            "scored_account": top_gl, "cost_centre": cc, "cost_centre_confidence": cc_conf,
            "confidence": confidence, "components": {
                "text_vote": round(text_share.get(top_gl, 0), 3), "vendor_freq": round(vfreq.get(top_gl, 0), 3),
                "amount_fit": fits[top_gl], "lead_over_runner_up": round(share, 3),
                "similar_same_vendor": same_n, "similar_same_category": cat_n, "similar_other_vendors": other_n,
                "vendor_lines": len(vlines)},
            "alternatives": alternatives, "capitalise": capitalise, "amortisation": amortisation,
            "policy_notes": policy_notes, "evidence": evidence,
        }

    def recommend_cc(self, vendor_id, gl, sims, requester_cc):
        lines = self.s.lines
        vl = [lines[i]["cc"] for i in self.s.lines_by_vendor.get(vendor_id, [])
              if lines[i]["gl"] == gl or lines[i]["amortise_to"] == gl]
        if not vl:
            vl = [lines[li]["cc"] for li, sim, same, _k in sims if lines[li]["gl"] == gl][:40]
        if not vl:
            return requester_cc, 0.5
        c = Counter(vl)
        if requester_cc and requester_cc in c:
            c[requester_cc] += len(vl) * 0.25
        cc, n = c.most_common(1)[0]
        return cc, round(min(0.99, n / sum(c.values())), 3)

    def evidence(self, vendor_id, sims, gl):
        lines = self.s.lines
        seen, out = set(), []
        def key(t):
            l = lines[t[0]]
            matches = l["gl"] == gl or l["amortise_to"] == gl
            return (not t[2], not matches, -round(t[1], 2), -date.fromisoformat(l["invoice_date"]).toordinal())

        ordered = sorted(sims, key=key)
        for li, sim, same, _k in ordered:
            l = lines[li]
            if l["invoice_id"] in seen:
                continue
            seen.add(l["invoice_id"])
            approver = self.s.people.get(l["approver_ids"][-1]) if l["approver_ids"] else None
            out.append({"invoice_id": l["invoice_id"], "invoice_num": l["invoice_num"], "vendor": l["vendor_name"],
                        "date": l["invoice_date"], "description": l["description"], "amount_usd": l["amount_usd"],
                        "account": l["gl"], "cost_centre": l["cc"], "similarity": round(sim, 3),
                        "approved_by": approver["name"] if approver else None, "same_vendor": same})
            if len(out) == 3:
                break
        return out

    def vendor_default_contrast(self, vendor_id, account, description):
        """When history contradicts the vendor-master default, quantify it in plain terms."""
        v = self.s.vendors[vendor_id]
        default = v["default_gl"]
        if default == account:
            return None
        lines = [self.s.lines[i] for i in self.s.lines_by_vendor.get(vendor_id, [])]
        invs_to = {l["invoice_id"] for l in lines if l["gl"] == account}
        invs_default = {l["invoice_id"] for l in lines if l["gl"] == default}
        default_descs = Counter(" ".join(l["description"].split(" – ")[0].split()[:4])
                                for l in lines if l["gl"] == default).most_common(1)
        reclassed = [l for l in lines if l["reclassified"] and l["posted_gl"] == default and l["gl"] == account]
        lag = None
        if reclassed:
            lag = round(sum((date.fromisoformat(l["reclass_date"]) - date.fromisoformat(l["invoice_date"])).days
                            for l in reclassed) / len(reclassed))
        return {"vendor_default": default, "vendor_default_name": self.s.coa[default]["name"],
                "invoices_coded_to_recommended": len(invs_to), "invoices_coded_to_default": len(invs_default),
                "default_used_for": default_descs[0][0] if default_descs else None,
                "past_miscodes_reclassified": len(reclassed), "avg_days_to_reclass": lag,
                "master_note": v.get("master_note")}
