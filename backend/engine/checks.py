"""Pre-payment controls: supplier, validity, duplicates, payment risk."""
import re
from datetime import date

from rapidfuzz import fuzz, process
from rapidfuzz.distance import Levenshtein

from ..integrations import external


def _digits(s):
    return re.sub(r"\D", "", s or "").lstrip("0")


def _domain(addr):
    m = re.search(r"@([\w.\-]+)", addr or "")
    return m.group(1).lower() if m else None


class Checks:
    def __init__(self, store):
        self.s = store
        self.vendor_names = {vid: v["name"] for vid, v in store.vendors.items()}
        self.risk = store.policies["risk"]

    # ---------- step 1: should this be here? ----------
    def resolve_vendor(self, doc):
        name = doc.get("vendor_name") or ""
        hit = process.extractOne(name, self.vendor_names, scorer=fuzz.token_sort_ratio, score_cutoff=0)
        tax_hit = next((vid for vid, v in self.s.vendors.items()
                        if doc.get("vendor_tax_id") and v["tax_id"] == doc.get("vendor_tax_id")), None)
        if hit and hit[1] >= 90:
            vid = hit[2]
            v = self.s.vendors[vid]
            return {"found": True, "vendor_id": vid, "name": v["name"], "match_score": round(hit[1], 1),
                    "status": v["status"], "tax_id_match": tax_hit == vid,
                    "default_gl": v["default_gl"], "default_cc": v["default_cc"], "category": v["category"],
                    "category_label": v["category_label"], "entity": v["entity"], "terms": v["payment_terms"],
                    "since": v["created_date"]}
        return {"found": False, "name": name, "closest": hit[0] if hit else None,
                "closest_score": round(hit[1], 1) if hit else None,
                "detail": "Supplier is not in the vendor master. Stop: route to vendor onboarding (KYC, sanctions, "
                          "bank verification) before anything else happens."}

    def sanctions(self, name):
        return external.ofac.screen(name)

    # ---------- step 2: is the invoice valid? ----------
    def validity(self, doc, vendor, live=False):
        issues, passed = [], []
        for field, label in (("invoice_num", "Invoice number"), ("invoice_date", "Invoice date"),
                             ("total", "Total"), ("currency", "Currency")):
            (passed if doc.get(field) not in (None, "") else issues).append(label)
        bill_entity = doc.get("entity")
        if vendor and vendor.get("entity") and bill_entity and bill_entity != vendor["entity"]:
            issues.append(f"Billed to {bill_entity} but supplier is set up for {vendor['entity']}")
        else:
            passed.append(f"Billed-to entity {bill_entity}")
        if vendor and doc.get("currency") and vendor.get("vendor_id"):
            vcur = self.s.vendors[vendor["vendor_id"]]["currency"]
            (passed if vcur == doc["currency"] else issues).append(f"Currency {doc['currency']} (supplier {vcur})")
        tax = {"status": "n/a"}
        if doc.get("currency") == "EUR":
            printed = doc.get("vendor_tax_id")
            master = self.s.vendors[vendor["vendor_id"]]["tax_id"] if vendor and vendor.get("vendor_id") else None
            checksum = external.be_vat_checksum_ok(printed) if printed else False
            if printed and printed == master:
                # master VAT numbers are validated at onboarding; VIES is re-queried only on a mismatch
                vies = {"valid": True, "source": "vendor master", "detail": "Validated at supplier onboarding"}
            else:
                vies = external.vies_check(printed, live=live) if printed else {"valid": None, "source": "missing"}
            ok = printed == master and vies.get("valid") is not False
            tax = {"status": "ok" if ok else "fail", "printed_vat": printed, "master_vat": master,
                   "matches_master": printed == master, "checksum_ok": checksum, "vies": vies,
                   "vat_amount": doc.get("tax"),
                   "detail": "VAT number matches vendor master and is valid on EU VIES." if ok else
                   f"VAT number on invoice ({printed}) "
                   f"{'differs from vendor master (' + str(master) + ')' if printed != master else ''}"
                   f"{' and ' if printed != master and vies.get('valid') is False else ''}"
                   f"{'is not registered on EU VIES' if vies.get('valid') is False else ''}. "
                   f"Input VAT of €{doc.get('tax', 0):,.2f} is not recoverable on this document."}
            if not ok:
                issues.append("VAT number check failed")
        elif doc.get("tax_rate"):
            tax = {"status": "ok", "detail": f"{doc.get('tax_label')} applied at expected rate."}
        return {"issues": issues, "passed": passed, "tax": tax}

    # ---------- duplicates ----------
    def duplicates(self, vendor_id, doc, earlier_queue):
        num = _digits(doc.get("invoice_num"))
        amt = doc.get("total") or 0
        inv_date = doc.get("invoice_date")
        window = self.risk["duplicate_window_days"]
        candidates = []
        pool = [("history", i["invoice_id"], i["invoice_num"], i["total"], i["invoice_date"], i.get("service_period"),
                 i["received_date"])
                for i in self.s.history_by_vendor.get(vendor_id, [])]
        pool += [("queue", q["intake_id"], q["document"].get("invoice_num"), q["document"].get("total"),
                  q["document"].get("invoice_date"), q["document"].get("service_period"), q["received_at"][:10])
                 for q in earlier_queue if q.get("vendor_hint") == vendor_id]
        for src, ref, other_num, other_amt, other_date, period, received in pool:
            if not other_amt or not inv_date or not other_date:
                continue
            reasons, score = [], 0.0
            if abs(other_amt - amt) <= max(0.01, amt * 0.005):
                reasons.append(f"same amount (${other_amt:,.2f})")
                score += 0.4
            days = abs((date.fromisoformat(other_date) - date.fromisoformat(inv_date)).days)
            if days == 0:
                reasons.append("same invoice date")
                score += 0.2
            elif days <= window:
                score += 0.05
            if period and doc.get("service_period") and period == doc.get("service_period"):
                reasons.append("same service period")
                score += 0.15
            on = _digits(other_num)
            if num and on and num == on:
                reasons.append(f"invoice number {other_num} ≈ {doc.get('invoice_num')} (format differs)"
                               if other_num != doc.get("invoice_num") else "identical invoice number")
                score += 0.35
            elif num and on and fuzz.ratio(num, on) >= 85:
                reasons.append(f"similar invoice number {other_num}")
                score += 0.2
            if score >= 0.75:
                candidates.append({"source": src, "ref": ref, "invoice_num": other_num, "amount": other_amt,
                                   "invoice_date": other_date, "received": received, "score": round(min(score, 1), 2),
                                   "reasons": reasons})
        candidates.sort(key=lambda c: -c["score"])
        return candidates[:3]

    # ---------- step 7: is it safe to pay? ----------
    def comparable_median(self, vendor_id, account, multi_month=False):
        """Median of this supplier's past invoices of the same kind: same account, and annual vs. monthly billing."""
        invs = self.s.history_by_vendor.get(vendor_id, [])
        same = sorted(i["total_usd"] for i in invs
                      if bool(i.get("service_period")) == multi_month
                      and any((l["corrected_gl"] or l["gl"]) == account or l.get("amortise_to") == account
                              for l in i["lines"] if l.get("line_type") != "TAX"))
        pool = same if len(same) >= 2 else sorted(i["total_usd"] for i in invs)
        return (pool[len(pool) // 2], len(pool), len(same) >= 2) if pool else (None, 0, False)

    def payment_risk(self, vendor_id, doc, total_usd, sender, as_of, account=None):
        v = self.s.vendors[vendor_id]
        flags, notes = [], []
        sp = doc.get("service_period") or {}
        multi = bool(sp.get("start") and sp.get("end") and sp["end"][:7] > sp["start"][:7])
        norm, n_comp, like_for_like = self.comparable_median(vendor_id, account, multi)
        ratio = round(total_usd / norm, 2) if norm else None
        if ratio and ratio >= self.risk["amount_vs_norm_multiple"]:
            flags.append({"code": "AMOUNT_VS_NORM", "severity": "medium",
                          "detail": f"${total_usd:,.0f} is {ratio}x this supplier's median "
                                    f"{'comparable ' if like_for_like else ''}invoice (${norm:,.0f}, "
                                    f"{n_comp} invoices)."})
        elif ratio:
            notes.append(f"Amount is {ratio}x the supplier median (${norm:,.0f}).")
        last_change = v["bank_change_log"][-1] if v["bank_change_log"] else None
        if last_change:
            days = (date.fromisoformat(as_of) - date.fromisoformat(last_change["date"])).days
            if days <= self.risk["bank_change_window_days"]:
                verified = last_change.get("callback_verified")
                flags.append({"code": "RECENT_BANK_CHANGE", "severity": "high" if not verified else "low",
                              "detail": f"Bank details changed {days} day(s) ago via "
                                        f"{last_change['request_channel']}; call-back verification "
                                        f"{'completed' if verified else 'NOT completed'}."})
        remit = doc.get("remit_to") or {}
        if remit.get("account_last4") and remit["account_last4"] != v["bank"]["account_last4"]:
            flags.append({"code": "REMIT_MISMATCH", "severity": "high",
                          "detail": f"Remit-to account ••{remit['account_last4']} differs from vendor master "
                                    f"••{v['bank']['account_last4']}."})
        if remit.get("routing_number"):
            ok = external.aba_valid(remit["routing_number"])
            notes.append(f"Routing number checksum {'valid' if ok else 'INVALID'}.")
        sd, vd = _domain(sender), _domain(v.get("remit_email"))
        if sd and vd and sd != vd:
            dist = Levenshtein.distance(sd.split(".")[0], vd.split(".")[0])
            if dist <= 3:
                flags.append({"code": "LOOKALIKE_DOMAIN", "severity": "high",
                              "detail": f"Sent from {sd}, which is {dist} character(s) from the supplier's "
                                        f"registered domain {vd}."})
        if doc.get("due_date") and doc.get("invoice_date"):
            days = (date.fromisoformat(doc["due_date"]) - date.fromisoformat(doc["invoice_date"])).days
            agreed = {"NET30": 30, "NET45": 45, "NET60": 60, "2/10 NET30": 30}.get(v["payment_terms"])
            if agreed and days < agreed - 10:
                flags.append({"code": "TERMS_SHORTENED", "severity": "low",
                              "detail": f"Invoice asks for payment in {days} days; agreed terms are "
                                        f"{v['payment_terms']}."})
        return {"flags": flags, "notes": notes, "ratio_to_norm": ratio, "median_usd": norm,
                "bank_last_changed": last_change}
