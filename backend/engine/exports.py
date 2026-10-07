"""Standard Oracle R12 open-interface files: the same upload path the CoE uses today, no screen-scraping."""
import csv
import io
from datetime import date

AP_HEADER_COLS = ["INVOICE_ID", "INVOICE_NUM", "INVOICE_TYPE_LOOKUP_CODE", "INVOICE_DATE", "VENDOR_NUM",
                  "VENDOR_SITE_CODE", "INVOICE_AMOUNT", "INVOICE_CURRENCY_CODE", "EXCHANGE_RATE_TYPE", "TERMS_NAME",
                  "DESCRIPTION", "SOURCE", "GROUP_ID", "ORG_ID", "GL_DATE", "PAYMENT_METHOD_CODE",
                  "REQUESTER_ID", "ATTRIBUTE_CATEGORY", "ATTRIBUTE1", "ATTRIBUTE2", "ATTRIBUTE3"]
AP_LINE_COLS = ["INVOICE_ID", "INVOICE_LINE_ID", "LINE_NUMBER", "LINE_TYPE_LOOKUP_CODE", "AMOUNT", "ACCOUNTING_DATE",
                "DESCRIPTION", "QUANTITY_INVOICED", "UNIT_PRICE", "DIST_CODE_CONCATENATED", "ORG_ID",
                "ASSETS_TRACKING_FLAG", "ASSET_BOOK_TYPE_CODE", "PRORATE_ACROSS_FLAG", "ATTRIBUTE_CATEGORY",
                "ATTRIBUTE1", "ATTRIBUTE2"]
GL_COLS = ["STATUS", "LEDGER_ID", "ACCOUNTING_DATE", "CURRENCY_CODE", "DATE_CREATED", "CREATED_BY", "ACTUAL_FLAG",
           "USER_JE_CATEGORY_NAME", "USER_JE_SOURCE_NAME", "SEGMENT1", "SEGMENT2", "SEGMENT3", "SEGMENT4",
           "SEGMENT5", "SEGMENT6", "ENTERED_DR", "ENTERED_CR", "REFERENCE1", "REFERENCE4", "REFERENCE10", "GROUP_ID"]
PAYMENT_METHOD = {"ACH": "EFT", "SEPA": "EFT", "NEFT": "EFT"}


def _csv(cols, rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


def _entities(store):
    return {e["code"]: e for e in store.reference["entities"]}


def ap_interface(store, results, group_id="NONPO-AGENT-20261015"):
    ents = _entities(store)
    headers, lines = [], []
    for n, r in enumerate(results, 1):
        doc, coding = r["document"], r["coding"]
        v = store.vendors[r["vendor"]["vendor_id"]]
        inv_id = 880000 + n
        org = ents[doc["entity"]]["org_id"]
        gl_date = (r.get("decision") or {}).get("at", store.demo_date)[:10]
        req = (r.get("requester") or {}).get("person") or {}
        headers.append({"INVOICE_ID": inv_id, "INVOICE_NUM": doc["invoice_num"], "INVOICE_TYPE_LOOKUP_CODE": "STANDARD",
                        "INVOICE_DATE": doc["invoice_date"], "VENDOR_NUM": v["vendor_id"],
                        "VENDOR_SITE_CODE": v["site_code"], "INVOICE_AMOUNT": f"{doc['total']:.2f}",
                        "INVOICE_CURRENCY_CODE": doc["currency"],
                        "EXCHANGE_RATE_TYPE": "Corporate" if doc["currency"] != "USD" else "",
                        "TERMS_NAME": v["payment_terms"], "DESCRIPTION": doc["lines"][0]["description"][:240],
                        "SOURCE": "NONPO_AGENT", "GROUP_ID": group_id, "ORG_ID": org, "GL_DATE": gl_date,
                        "PAYMENT_METHOD_CODE": PAYMENT_METHOD.get(v["bank"]["type"], "CHECK"),
                        "REQUESTER_ID": req.get("id", ""), "ATTRIBUTE_CATEGORY": "NONPO_AGENT",
                        "ATTRIBUTE1": r["intake_id"], "ATTRIBUTE2": f"{coding['confidence']:.2f}",
                        "ATTRIBUTE3": "OVERRIDDEN" if (r.get("decision") or {}).get("override") else "AS_RECOMMENDED"})
        for i, lr in enumerate(coding["lines"], 1):
            rec = lr["rec"]
            ov = ((r.get("decision") or {}).get("override") or {})
            account = ov.get("account") or rec["account"]
            cc = ov.get("cost_centre") or rec["cost_centre"]
            capital = bool(rec.get("capitalise"))
            lines.append({"INVOICE_ID": inv_id, "INVOICE_LINE_ID": inv_id * 100 + i, "LINE_NUMBER": i,
                          "LINE_TYPE_LOOKUP_CODE": "ITEM", "AMOUNT": f"{lr['amount']:.2f}", "ACCOUNTING_DATE": gl_date,
                          "DESCRIPTION": lr["description"][:240], "QUANTITY_INVOICED": lr["qty"],
                          "UNIT_PRICE": f"{lr['unit_price']:.2f}",
                          "DIST_CODE_CONCATENATED": f"{doc['entity']}.{cc.replace('CC', '')}.{account}.000.000.000",
                          "ORG_ID": org, "ASSETS_TRACKING_FLAG": "Y" if capital else "N",
                          "ASSET_BOOK_TYPE_CODE": f"{doc['entity']} CORP" if capital else "",
                          "PRORATE_ACROSS_FLAG": "N", "ATTRIBUTE_CATEGORY": "NONPO_AGENT",
                          "ATTRIBUTE1": f"{rec['confidence']:.2f}", "ATTRIBUTE2": rec["scored_account"]})
        if doc.get("tax"):
            k = len(coding["lines"]) + 1
            tax_account = "1410" if doc["currency"] in ("EUR", "INR") else coding["lines"][0]["rec"]["account"]
            lines.append({"INVOICE_ID": inv_id, "INVOICE_LINE_ID": inv_id * 100 + k, "LINE_NUMBER": k,
                          "LINE_TYPE_LOOKUP_CODE": "TAX", "AMOUNT": f"{doc['tax']:.2f}", "ACCOUNTING_DATE": gl_date,
                          "DESCRIPTION": doc.get("tax_label") or "Tax", "QUANTITY_INVOICED": "", "UNIT_PRICE": "",
                          "DIST_CODE_CONCATENATED": f"{doc['entity']}.{coding['cost_centre'].replace('CC', '')}."
                                                    f"{tax_account}.000.000.000",
                          "ORG_ID": org, "ASSETS_TRACKING_FLAG": "N", "PRORATE_ACROSS_FLAG": "N",
                          "ATTRIBUTE_CATEGORY": "NONPO_AGENT"})
    return _csv(AP_HEADER_COLS, headers), _csv(AP_LINE_COLS, lines)


def gl_amortisation(store, result):
    am = result["amortisation"]
    ent = result["document"]["entity"]
    ledger = _entities(store)[ent]["ledger_id"]
    cc = result["coding"]["cost_centre"].replace("CC", "")
    rows = []
    for s in am["schedule"]:
        mon = s["period"]
        y, m = 2000 + int(mon[-2:]), ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV",
                                      "DEC"].index(mon[:3]) + 1
        last = date(y + m // 12, m % 12 + 1, 1).toordinal() - 1
        acct_date = date.fromordinal(last).isoformat()
        desc = f"{result['document']['vendor_name']} {result['document']['invoice_num']} amortisation {mon}"
        base = {"STATUS": "NEW", "LEDGER_ID": ledger, "ACCOUNTING_DATE": acct_date, "CURRENCY_CODE": "USD",
                "DATE_CREATED": store.demo_date, "CREATED_BY": "NONPO_AGENT", "ACTUAL_FLAG": "A",
                "USER_JE_CATEGORY_NAME": "Amortisation", "USER_JE_SOURCE_NAME": "Spreadsheet",
                "SEGMENT1": ent, "SEGMENT2": cc, "SEGMENT4": "000", "SEGMENT5": "000", "SEGMENT6": "000",
                "REFERENCE1": f"Prepaid amortisation {result['document']['invoice_num']}",
                "REFERENCE4": desc, "REFERENCE10": desc, "GROUP_ID": "AMORT-" + result["intake_id"]}
        rows.append({**base, "SEGMENT3": s["debit"], "ENTERED_DR": f"{s['amount']:.2f}", "ENTERED_CR": ""})
        rows.append({**base, "SEGMENT3": s["credit"], "ENTERED_DR": "", "ENTERED_CR": f"{s['amount']:.2f}"})
    return _csv(GL_COLS, rows)


def gl_reclass(store, flags):
    rows = []
    for f in flags:
        if f.get("type") != "MISCODED":
            continue
        ent = f["entity"]
        ledger = _entities(store)[ent]["ledger_id"]
        desc = f"Reclass {f['je_id']} {f['account']}->{f['suggested_account']}"
        base = {"STATUS": "NEW", "LEDGER_ID": ledger, "ACCOUNTING_DATE": "2026-09-30", "CURRENCY_CODE": "USD",
                "DATE_CREATED": store.demo_date, "CREATED_BY": "ANOMALY_LAYER", "ACTUAL_FLAG": "A",
                "USER_JE_CATEGORY_NAME": "Reclass", "USER_JE_SOURCE_NAME": "Spreadsheet", "SEGMENT1": ent,
                "SEGMENT2": f["cost_centre"].replace("CC", ""), "SEGMENT4": "000", "SEGMENT5": "000", "SEGMENT6": "000",
                "REFERENCE1": "SEP-26 Anomaly layer proposed reclasses", "REFERENCE4": desc,
                "REFERENCE10": f["description"][:240], "GROUP_ID": "ANOMALY-SEP26"}
        rows.append({**base, "SEGMENT3": f["suggested_account"], "ENTERED_DR": f"{f['amount']:.2f}", "ENTERED_CR": ""})
        rows.append({**base, "SEGMENT3": f["account"], "ENTERED_DR": "", "ENTERED_CR": f"{f['amount']:.2f}"})
    return _csv(GL_COLS, rows)


def procurement_report(results):
    cols = ["INTAKE_ID", "SUPPLIER", "CATEGORY", "INVOICE_NUM", "INVOICE_DATE", "AMOUNT_USD", "POLICY_RULE",
            "REQUESTER", "COST_CENTRE", "RECOMMENDATION"]
    rows = []
    for r in results:
        po = (r.get("po") or {}).get("policy") or {}
        if not po.get("breach"):
            continue
        rows.append({"INTAKE_ID": r["intake_id"], "SUPPLIER": r["vendor"]["name"],
                     "CATEGORY": r["vendor"]["category_label"], "INVOICE_NUM": r["document"]["invoice_num"],
                     "INVOICE_DATE": r["document"]["invoice_date"], "AMOUNT_USD": f"{r['total_usd']:.2f}",
                     "POLICY_RULE": po["rule"],
                     "REQUESTER": ((r.get("requester") or {}).get("person") or {}).get("name", ""),
                     "COST_CENTRE": r["coding"]["cost_centre"],
                     "RECOMMENDATION": "Raise PO / catalogue item for future purchases"})
    return _csv(cols, rows)
