"""Render invoice PDFs for the storyboard and a sample of background invoices.

    uv run python -m scripts.render_pdfs

Uses the locally installed Google Chrome through Playwright (no browser download).
Writes data/pdfs/*.pdf and data/pdfs/manifest.json (intake_id -> pdf path).
"""
import json
import re
import zlib
from datetime import date
from pathlib import Path

from jinja2 import Environment
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "data" / "seed"
OUT = ROOT / "data" / "pdfs"
BACKGROUND_PDFS = 34

STREETS = ["Market St", "Commerce Dr", "Industrial Pkwy", "Lakeview Ave", "Corporate Blvd", "Riverfront Way",
           "Enterprise Ct", "Union Ave", "Gateway Plaza", "Harbor Rd", "Technology Way", "Main St"]
EU_STREETS = ["Chaussée de Bruxelles", "Rue du Commerce", "Avenue des Arts", "Boulevard de Waterloo"]
STYLE_BY_KEY = {"telecoms": "telecom", "dell": "dell", "legal": "law", "duplicate": "law", "saas": "saas",
                "bank_change": "contractor", "sod": "consult", "eu_vat": "eu", "open_po": "consult",
                "unknown_vendor": "scan", "learning_1": "generic_b", "learning_2": "generic_b",
                "po_breach_marketing": "agency", "utility_spike": "utility", "rate_variance": "law",
                "split_cc": "generic_a", "split_entity": "saas_seats", "cutoff": "generic_c", "use_tax": "generic_b",
                "intercompany": "generic_c", "reimbursement": "scan_receipt"}
ZIP_BASE = {"MO": 63100, "TX": 78600, "IL": 60600, "GA": 30300, "NC": 28200, "OH": 43200, "CO": 80200, "MN": 55400,
            "NY": 10000, "CT": 6900, "NJ": 7100, "MA": 2100, "AZ": 85000, "TN": 37200, "IN": 46200, "NE": 68100,
            "WA": 98100, "FL": 33100}
GENERIC = ["generic_a", "generic_b", "generic_c"]
PALETTE = ["#1f4e79", "#7a2e2e", "#2d5d3b", "#4b3f72", "#8a5a12", "#225a6b", "#5a5a5a", "#6b2f57"]


def h(s, n):
    return zlib.crc32(s.encode()) % n


def address(v):
    k = v["vendor_id"]
    if v["currency"] == "EUR":
        return f"{EU_STREETS[h(k, 4)]} {10 + h(k + 'n', 180)}", f"{1300 + h(k, 80)} {v['city']}, Belgique"
    if v["currency"] == "INR":
        return f"Plot {10 + h(k, 90)}, Hinjewadi Phase {1 + h(k, 3)}", f"{v['city']} 4110{h(k, 60):02d}, Maharashtra"
    zipc = ZIP_BASE.get(v["region"], 63000) + h(k, 900)
    return f"{100 + h(k, 9800)} {STREETS[h(k, len(STREETS))]}", f"{v['city']}, {v['region']} {zipc:05d}"


def money(x, cur="USD"):
    sym = {"USD": "$", "EUR": "€", "INR": "₹"}.get(cur, "")
    return f"{sym}{x:,.2f}"


def nice_date(iso, style="us"):
    if not iso:
        return ""
    d = date.fromisoformat(iso)
    return d.strftime("%d/%m/%Y") if style == "eu" else d.strftime("%B %-d, %Y")


TEMPLATE = r"""<!doctype html><html><head><meta charset="utf-8"><style>
@page { size: Letter; margin: 0; }
* { box-sizing: border-box; }
body { margin: 0; font-family: {{ font }}; color: #1d1d1f; font-size: 10.5pt; }
.page { width: 8.5in; min-height: 11in; padding: 0.6in 0.65in; position: relative; {{ page_extra }} }
.row { display: flex; justify-content: space-between; gap: 24px; }
.mark { width: 46px; height: 46px; border-radius: {{ radius }}; background: {{ accent }}; color: #fff; display: grid;
  place-items: center; font-weight: 700; font-size: 16pt; letter-spacing: .5px; }
.brand { display: flex; gap: 12px; align-items: center; }
.brand b { font-size: 17pt; color: {{ accent }}; display: block; }
.muted { color: #666; } .small { font-size: 8.5pt; } .right { text-align: right; }
h1 { font-size: 22pt; margin: 0; letter-spacing: 1px; color: {{ accent }}; font-weight: 600; }
.box { border: 1px solid #d0d0d0; padding: 10px 12px; border-radius: 4px; }
.meta td { padding: 2px 0 2px 14px; } .meta td:first-child { color: #666; padding-left: 0; }
table.items { width: 100%; border-collapse: collapse; margin-top: 22px; }
table.items th { text-align: left; font-size: 8.5pt; text-transform: uppercase; letter-spacing: .6px;
  border-bottom: 2px solid {{ accent }}; padding: 6px 4px; color: #333; }
table.items td { border-bottom: 1px solid #e3e3e3; padding: 8px 4px; vertical-align: top; }
table.items td.num, table.items th.num { text-align: right; white-space: nowrap; }
.totals { margin-left: auto; width: 46%; margin-top: 14px; }
.totals td { padding: 4px 4px; } .totals tr.grand td { border-top: 2px solid #222; font-weight: 700; font-size: 12pt; }
.banner { background: #b3261e; color: #fff; font-weight: 700; text-align: center; padding: 6px; letter-spacing: 2px;
  margin: -0.6in -0.65in 18px; }
.alert { border: 2px solid #b3261e; color: #b3261e; padding: 8px 12px; font-weight: 600; margin-top: 16px; }
.foot { position: absolute; bottom: 0.5in; left: 0.65in; right: 0.65in; font-size: 8pt; color: #777;
  border-top: 1px solid #ddd; padding-top: 8px; }
.stamp { position: absolute; top: 2.2in; right: 0.9in; transform: rotate(-14deg); border: 3px solid #2d5d9f;
  color: #2d5d9f; padding: 4px 14px; font-weight: 800; font-size: 15pt; opacity: .55; letter-spacing: 2px; }
.serif { font-family: Georgia, 'Times New Roman', serif; }
.summary { background: #f4f6f9; border-left: 4px solid {{ accent }}; padding: 10px 14px; margin-top: 18px; }
</style></head><body><div class="page">
{% if banner %}<div class="banner">{{ banner }}</div>{% endif %}
{% if style == 'scan' %}<div class="stamp">RECEIVED OCT 12</div>{% endif %}
<div class="row">
  <div class="brand">
    {% if style != 'dell' %}<div class="mark">{{ initials }}</div>{% endif %}
    <div><b {% if style == 'law' %}class="serif"{% endif %}>{{ vendor_name }}</b>
      <span class="small muted">{{ street }} · {{ city_line }}</span><br>
      <span class="small muted">{{ tax_label }}: {{ tax_id or '—' }}</span></div>
  </div>
  <div class="right">
    <h1 {% if style == 'law' %}class="serif"{% endif %}>{{ title }}</h1>
    <table class="meta" style="margin-left:auto">
      <tr><td>{{ L.number }}</td><td><b>{{ invoice_num }}</b></td></tr>
      <tr><td>{{ L.date }}</td><td>{{ invoice_date }}</td></tr>
      <tr><td>{{ L.due }}</td><td>{{ due_date }}</td></tr>
      {% for k, v in extra_meta %}<tr><td>{{ k }}</td><td>{{ v }}</td></tr>{% endfor %}
    </table>
  </div>
</div>
<div class="row" style="margin-top:26px">
  <div class="box" style="flex:1"><div class="small muted">{{ L.bill_to }}</div><b>{{ bill_to_name }}</b><br>{{ bill_to_addr }}
    {% if attention %}<br><span class="small">Attn: {{ attention }}</span>{% endif %}</div>
  {% if ship_to %}<div class="box" style="flex:1"><div class="small muted">Ship to</div>{{ ship_to }}</div>{% endif %}
  {% if matter %}<div class="box" style="flex:1"><div class="small muted">Matter</div><b>{{ matter }}</b> — {{ matter_desc }}
    <br><span class="small">Client contact: {{ client_contact }}</span></div>{% endif %}
</div>
{% if summary %}<div class="summary">{{ summary }}</div>{% endif %}
<table class="items"><thead><tr><th>{{ L.description }}</th><th class="num">{{ L.qty }}</th><th class="num">{{ L.unit }}</th>
<th class="num">{{ L.amount }}</th></tr></thead><tbody>
{% for l in lines %}<tr><td>{{ l.description }}</td><td class="num">{{ l.qty }}</td><td class="num">{{ l.unit }}</td>
<td class="num">{{ l.amount }}</td></tr>{% endfor %}
</tbody></table>
<table class="totals">
<tr><td>{{ L.subtotal }}</td><td class="right">{{ subtotal }}</td></tr>
<tr><td>{{ tax_line_label }}</td><td class="right">{{ tax }}</td></tr>
<tr class="grand"><td>{{ L.total }} ({{ currency }})</td><td class="right">{{ total }}</td></tr>
</table>
{% if alert %}<div class="alert">{{ alert }}</div>{% endif %}
<div style="margin-top:22px" class="small"><b>{{ L.remit }}</b><br>{{ remit }}</div>
{% if note %}<p class="small muted" style="margin-top:14px">{{ note }}</p>{% endif %}
<div class="foot">{{ footer }}</div>
</div></body></html>"""

LABELS_EN = {"number": "Invoice no.", "date": "Invoice date", "due": "Due date", "bill_to": "Bill to",
             "description": "Description", "qty": "Qty", "unit": "Unit price", "amount": "Amount",
             "subtotal": "Subtotal", "total": "Total due", "remit": "Remit to"}
LABELS_EU = {"number": "Facture / Factuur n°", "date": "Date", "due": "Échéance / Vervaldag",
             "bill_to": "Facturé à / Gefactureerd aan", "description": "Description / Omschrijving",
             "qty": "Qté", "unit": "Prix unitaire", "amount": "Montant", "subtotal": "Total HTVA / Totaal excl. btw",
             "total": "Total TVAC / Totaal incl. btw", "remit": "Paiement / Betaling"}


def context(item, vendor):
    d = item["document"]
    key = item.get("storyboard_key")
    style = STYLE_BY_KEY.get(key) or GENERIC[h(item["intake_id"], 3)]
    cur = d["currency"]
    name = d.get("vendor_name") or vendor["name"]
    if vendor:
        street, city_line = address(vendor)
    else:
        street, city_line = "1180 Route 61", "Wentzville, MO 63385"
    initials = "".join(w[0] for w in re.sub(r"[^A-Za-z ]", " ", name).split()[:2]).upper()
    accent = PALETTE[h(name, len(PALETTE))]
    eu = cur == "EUR"
    L = LABELS_EU if eu else LABELS_EN
    lines = [{"description": l["description"], "qty": f"{l['qty']:g}", "unit": money(l["unit_price"], cur),
              "amount": money(l["amount"], cur)} for l in d["lines"]]
    remit = d.get("remit_to") or {}
    if remit.get("type") == "ACH" or remit.get("routing_number"):
        remit_txt = f"ACH — routing {remit.get('routing_number')} · account ending {remit.get('account_last4')}"
    elif remit.get("type") == "SEPA" or eu:
        remit_txt = f"IBAN {remit.get('iban_masked', 'BE•• •••• •••• ' + str(remit.get('account_last4')))}"
    elif remit.get("type") == "NEFT":
        remit_txt = f"NEFT — IFSC {remit.get('ifsc')} · account ending {remit.get('account_last4')}"
    else:
        remit_txt = remit.get("address", "Check payable to supplier")
    ctx = {"style": style, "vendor_name": name, "street": street, "city_line": city_line, "initials": initials,
           "accent": accent, "radius": "50%" if h(name, 2) else "6px",
           "font": "'Helvetica Neue', Arial, sans-serif", "page_extra": "", "title": "INVOICE", "L": L,
           "tax_label": "VAT / BTW" if eu else ("GSTIN" if cur == "INR" else "Federal Tax ID"),
           "tax_id": d.get("vendor_tax_id"), "invoice_num": d["invoice_num"],
           "invoice_date": nice_date(d["invoice_date"], "eu" if eu else "us"),
           "due_date": nice_date(d.get("due_date"), "eu" if eu else "us"), "extra_meta": [],
           "bill_to_name": d["bill_to"]["name"], "bill_to_addr": d["bill_to"]["address"],
           "attention": None, "ship_to": None, "matter": None, "summary": None, "banner": d.get("banner"),
           "lines": lines, "subtotal": money(d["subtotal"], cur), "tax": money(d.get("tax", 0), cur),
           "tax_line_label": d.get("tax_label") or "Tax", "total": money(d["total"], cur), "currency": cur,
           "remit": remit_txt, "alert": None, "note": None,
           "footer": f"{name} · {street}, {city_line} · Terms: {d.get('payment_terms', 'NET30')}"}
    if style == "telecom":
        ctx.update(title="STATEMENT / INVOICE", summary=f"Account {d.get('account_number')} · Billing period "
                   f"Sep 1 – Sep 30, 2026 · 1,212 active lines · Autopay: not enrolled",
                   extra_meta=[("Account", d.get("account_number"))], tax_line_label="Taxes & surcharges (included)")
    elif style == "dell":
        ctx.update(font="Arial, sans-serif", accent="#0b5cab", title="Invoice",
                   extra_meta=[("Order number", d.get("order_number")), ("Customer PO", "—"),
                               ("Ordered by", d.get("ordered_by"))],
                   ship_to=d.get("ship_to"), note="Hardware ships with standard 3-year limited warranty. "
                   "Service contracts are invoiced separately.")
    elif style == "law":
        ctx.update(font="Georgia, 'Times New Roman', serif", accent="#2b2b2b", title="INVOICE",
                   matter=d.get("matter"), matter_desc=d.get("matter_desc"), client_contact=d.get("client_contact"),
                   extra_meta=[("Billing period", "Aug 1 – Sep 30, 2026")] if d.get("matter") else
                   [("Engagement letter", d.get("engagement_letter"))],
                   note="Detailed time entries available on request. Please quote the invoice number with payment.")
    elif style == "saas":
        sp = d.get("service_period", {})
        ctx.update(accent="#3a36db", title="Invoice", extra_meta=[("Order form", d.get("order_form")),
                                                                    ("Subscription term", f"{sp.get('start')} → {sp.get('end')}")],
                   summary="Annual subscription renewal · 125 analyst seats · billed annually in advance")
    elif style == "contractor":
        ctx.update(accent="#b3261e", title="INVOICE", alert=d.get("remit_note"),
                   note="Emergency call-out authorised by site facilities on Oct 9. Payment due within 7 days.")
    elif style == "consult":
        ctx.update(accent="#14532d" if key == "sod" else ctx["accent"],
                   attention=d.get("prepared_for"), extra_meta=[("Engagement", "Finance transformation")]
                   if key == "sod" else [])
    elif style == "eu":
        ctx.update(title="FACTURE / FACTUUR", accent="#0f5257",
                   note="Autoliquidation non applicable. TVA 21% / BTW 21%. Paiement à 30 jours / Betaling binnen 30 dagen.")
    elif style == "scan":
        ctx.update(font="'Courier New', monospace", accent="#333", radius="0",
                   page_extra="transform: rotate(-0.7deg); filter: grayscale(1) contrast(1.08); "
                              "background: repeating-linear-gradient(0deg, #fbfbf7, #fbfbf7 3px, #f3f3ee 4px);",
                   note="Thank you for your business! — Quickfix Plumbing LLC, licensed & insured")
    elif style == "saas_seats":
        sp = d.get("service_period", {})
        ctx.update(accent="#3a36db", title="Invoice", extra_meta=[("Subscription term", f"{sp.get('start')} → {sp.get('end')}")],
                   summary="Monthly seat billing by user entity")
    elif style == "scan_receipt":
        ctx.update(font="'Courier New', monospace", accent="#333", radius="0", title="RECEIPT",
                   page_extra="transform: rotate(-0.5deg); filter: grayscale(1) contrast(1.05);",
                   note="Paid by personal card ending 4471. Please reimburse the employee.")
    elif style == "agency":
        ctx.update(accent="#c2410c", extra_meta=[("Campaign", "Q4 brand campaign")])
    elif style == "utility":
        ctx.update(title="ELECTRIC BILL", summary="Meter 4471-0937 · Service period Sep 1 – Sep 30, 2026 · "
                   "Includes back-billing adjustment for estimated reads Jun–Aug", accent="#0e7490")
    elif style == "generic_b":
        ctx.update(font="'Avenir Next', 'Segoe UI', Arial, sans-serif")
    elif style == "generic_c":
        ctx.update(font="Georgia, serif", title="Tax Invoice" if cur == "INR" else "Invoice")
    return ctx


def main():
    queue = json.loads((SEED / "intake_queue.json").read_text())
    vendors = {v["vendor_id"]: v for v in json.loads((SEED / "vendors.json").read_text())}
    picks = [q for q in queue if q.get("storyboard_key")]
    background = [q for q in queue if not q.get("storyboard_key")]
    background.sort(key=lambda q: h(q["intake_id"], 10_000))
    picks += background[:BACKGROUND_PDFS]
    OUT.mkdir(parents=True, exist_ok=True)
    env = Environment(autoescape=True)
    tmpl = env.from_string(TEMPLATE)
    manifest = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_page()
        shot = browser.new_page(viewport={"width": 816, "height": 1056}, device_scale_factor=2)
        for q in picks:
            v = vendors.get(q.get("vendor_hint"))
            html = tmpl.render(**context(q, v))
            slug = re.sub(r"[^a-z0-9]+", "-", (q["document"].get("vendor_name") or "invoice").lower()).strip("-")
            num = re.sub(r"[^A-Za-z0-9]+", "-", q["document"]["invoice_num"])
            name = f"{q['intake_id']}_{slug}_{num}.pdf"
            shot.set_content(html)
            shot.screenshot(path=str(OUT / name.replace(".pdf", ".png")), full_page=False, scale="device")
            page.set_content(html)
            page.pdf(path=str(OUT / name), format="Letter", print_background=True)
            manifest[q["intake_id"]] = f"pdfs/{name}"
        browser.close()
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"rendered {len(manifest)} PDFs to {OUT}")


if __name__ == "__main__":
    main()
