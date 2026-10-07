import random
from datetime import date, timedelta

from .catalog import CATEGORIES
from .reference import HISTORY_START, DEMO_DATE, PO_POLICY

US_CITIES = [("St. Louis", "MO"), ("Kansas City", "MO"), ("Chicago", "IL"), ("Dallas", "TX"), ("Austin", "TX"),
             ("Atlanta", "GA"), ("Charlotte", "NC"), ("Columbus", "OH"), ("Denver", "CO"), ("Minneapolis", "MN"),
             ("New York", "NY"), ("Stamford", "CT"), ("Newark", "NJ"), ("Boston", "MA"), ("Phoenix", "AZ"),
             ("Nashville", "TN"), ("Indianapolis", "IN"), ("Omaha", "NE"), ("Seattle", "WA"), ("Miami", "FL")]
EU_CITIES = [("Brussels", "BE"), ("Waterloo", "BE"), ("Wavre", "BE"), ("Antwerp", "BE"), ("Leuven", "BE")]
IN_CITIES = [("Pune", "MH"), ("Mumbai", "MH")]

ENTITY_CCS = {
    "EU01": {"facilities": "CC5220", "utilities": "CC5220", "catering": "CC5220", "marketing": "CC6140",
             "translation": "CC6140", "legal": "CC5130"},
    "IN01": {"facilities": "CC5230", "utilities": "CC5230", "catering": "CC5230", "contract_labour": "CC7170",
             "it_services": "CC4470"},
}

TERMS = [("NET30", 30, 0.55), ("NET45", 45, 0.2), ("NET60", 60, 0.15), ("2/10 NET30", 30, 0.1)]


def _aba(rng):
    # ABA routing number with a valid 3-7-1 checksum
    while True:
        d = [rng.randint(0, 9) for _ in range(8)]
        d[0] = rng.choice([0, 1, 2, 3])
        s = 3 * (d[0] + d[3] + d[6]) + 7 * (d[1] + d[4] + d[7]) + (d[2] + d[5])
        check = (10 - s % 10) % 10
        return "".join(map(str, d)) + str(check)


def _be_iban(rng):
    bank = f"{rng.randint(0, 999):03d}"
    acct = f"{rng.randint(0, 9_999_999):07d}"
    nat_check = int(bank + acct) % 97 or 97
    bban = f"{bank}{acct}{nat_check:02d}"
    numeric = int(bban + "1114" + "00")  # B=11, E=14
    check = 98 - numeric % 97
    return f"BE{check:02d}{bban}"


def _be_vat(rng):
    base = rng.randint(9_000_000, 9_999_999)
    first8 = int(f"0{base}")
    return f"BE0{base}{97 - first8 % 97:02d}"


def _ein(rng):
    return f"{rng.randint(10, 98)}-{rng.randint(1_000_000, 9_999_999)}"


def _gstin(rng):
    letters = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    pan = "".join(rng.choice(letters) for _ in range(5)) + f"{rng.randint(1000, 9999)}" + rng.choice(letters)
    return f"27{pan}1Z{rng.randint(1, 9)}"


def _bank(rng, currency):
    if currency == "USD":
        acct = f"{rng.randint(10**9, 10**10 - 1)}"
        return {"type": "ACH", "routing_number": _aba(rng), "account_last4": acct[-4:]}
    if currency == "EUR":
        iban = _be_iban(rng)
        return {"type": "SEPA", "iban_masked": f"{iban[:4]} •••• •••• {iban[-4:]}", "iban": iban,
                "account_last4": iban[-4:]}
    acct = f"{rng.randint(10**11, 10**12 - 1)}"
    return {"type": "NEFT", "ifsc": f"HDFC0{rng.randint(100000, 999999)}", "account_last4": acct[-4:]}


DEMO_VENDORS = [
    {"vendor_id": "V1043", "name": "Dell Technologies", "category": "it_hardware", "default_gl": "6420",
     "default_cc": "CC4410", "entity": "US01", "currency": "USD", "city": ("Round Rock", "TX"),
     "invoice_format": "dell", "terms": "NET45",
     "note": "Default GL set to 6420 when the hardware service-contract relationship was onboarded (2019)."},
    {"vendor_id": "V1102", "name": "Northline Communications", "category": "telecoms", "default_gl": "6310",
     "default_cc": "CC4420", "entity": "US01", "currency": "USD", "city": ("Kansas City", "MO"),
     "invoice_format": "northline", "terms": "NET30"},
    {"vendor_id": "V2007", "name": "Hartwell & Pryce LLP", "category": "legal", "default_gl": "6610",
     "default_cc": "CC5100", "entity": "US01", "currency": "USD", "city": ("Chicago", "IL"),
     "invoice_format": "plain4", "terms": "NET30"},
    {"vendor_id": "V3015", "name": "Cloudline Analytics", "category": "saas", "default_gl": "6350",
     "default_cc": "CC9130", "entity": "US01", "currency": "USD", "city": ("Austin", "TX"),
     "invoice_format": "cla", "terms": "NET30"},
    {"vendor_id": "V4120", "name": "Summit Facility Services", "category": "facilities", "default_gl": "6430",
     "default_cc": "CC5200", "entity": "US01", "currency": "USD", "city": ("St. Louis", "MO"),
     "invoice_format": "sfs", "terms": "NET30"},
    {"vendor_id": "V5031", "name": "Brightpath Advisory", "category": "consulting", "default_gl": "6510",
     "default_cc": "CC7100", "entity": "US01", "currency": "USD", "city": ("St. Louis", "MO"),
     "invoice_format": "bpa", "terms": "NET30"},
    {"vendor_id": "V6208", "name": "Wavre Workplace Solutions SRL", "category": "facilities",
     "default_gl": "6430", "default_cc": "CC5220", "entity": "EU01", "currency": "EUR",
     "city": ("Wavre", "BE"), "invoice_format": "wws", "terms": "NET30"},
]

DEMO_EMAILS = {'V1043': 'us_invoices@dell-billing.example',
               'V1102': 'billing@northlinecomms.example',
               'V2007': 'accounts@hartwellpryce.example',
               'V3015': 'billing@cloudline-analytics.example',
               'V4120': 'accounts@summitfacility.example',
               'V5031': 'finance@brightpathadvisory.example',
               'V6208': 'facturation@wavreworkplace.example'}

INVOICE_FORMATS = ["INV-{yyyy}-{seq:05d}", "{seq:07d}", "{pfx}-{seq:05d}", "{pfx}{yy}{seq:04d}",
                   "{seq:06d}", "INV{seq:06d}", "{pfx}/{yy}/{seq:04d}"]


def _prefix(name):
    letters = [w[0] for w in name.replace("&", "").split() if w and w[0].isalpha()]
    return "".join(letters[:3]).upper() or "INV"


def build_vendors(rng: random.Random):
    vendors = []
    used_ids = {v["vendor_id"] for v in DEMO_VENDORS}
    used_names = {v["name"] for v in DEMO_VENDORS}
    po_required = {r["category"]: r["min"] for r in PO_POLICY["required"]}

    def base_record(vid, name, cat_key, entity, currency, city, default_gl, default_cc, terms, fmt):
        cat = CATEGORIES[cat_key]
        created = HISTORY_START - timedelta(days=rng.randint(200, 3600))
        tax_id = _ein(rng) if currency == "USD" else (_be_vat(rng) if currency == "EUR" else _gstin(rng))
        return {
            "vendor_id": vid, "name": name, "category": cat_key, "category_label": cat["label"],
            "status": "ACTIVE", "entity": entity, "currency": currency,
            "site_code": f"{city[0][:3].upper()}-{currency}", "city": city[0], "region": city[1],
            "tax_id": tax_id, "default_gl": default_gl, "default_cc": default_cc,
            "payment_terms": terms, "invoice_format": fmt, "bank": _bank(rng, currency),
            "bank_change_log": [], "created_date": created.isoformat(),
            "sanctions_screened": (DEMO_DATE - timedelta(days=rng.randint(1, 85))).isoformat(),
            "po_required_category": cat_key in po_required,
            "remit_email": f"ar@{''.join(ch for ch in name.lower() if ch.isalnum())[:18]}.example",
        }

    for d in DEMO_VENDORS:
        v = base_record(d["vendor_id"], d["name"], d["category"], d["entity"], d["currency"], d["city"],
                        d["default_gl"], d["default_cc"], d["terms"], d["invoice_format"])
        if d.get("note"):
            v["master_note"] = d["note"]
        v["remit_email"] = DEMO_EMAILS[d["vendor_id"]]
        if d["vendor_id"] == "V6208":
            v["tax_id"] = "BE0939924852"  # checksum-valid, confirmed not registered on VIES
        vendors.append(v)

    for cat_key, cat in CATEGORIES.items():
        prefixes, suffixes = cat["names"]
        combos = [f"{p} {s}" for p in prefixes for s in suffixes]
        rng.shuffle(combos)
        count = cat["vendor_count"] - sum(1 for d in DEMO_VENDORS if d["category"] == cat_key)
        made = 0
        for name in combos:
            if made >= count:
                break
            if name in used_names:
                continue
            used_names.add(name)
            vid = None
            while vid is None or vid in used_ids:
                vid = f"V{rng.randint(1000, 9899)}"
            used_ids.add(vid)
            r = rng.random()
            if cat_key in ("utilities", "facilities", "catering", "translation", "marketing") and r < 0.18:
                entity, currency, city = "EU01", "EUR", rng.choice(EU_CITIES)
            elif cat_key in ("contract_labour", "facilities", "utilities", "it_services", "catering") and r > 0.88:
                entity, currency, city = "IN01", "INR", rng.choice(IN_CITIES)
            else:
                entity, currency, city = "US01", "USD", rng.choice(US_CITIES)
            ccs = [c for c, _ in cat["ccs"]]
            weights = [w for _, w in cat["ccs"]]
            default_cc = ENTITY_CCS.get(entity, {}).get(cat_key) or rng.choices(ccs, weights)[0]
            terms = rng.choices([t[0] for t in TERMS], [t[2] for t in TERMS])[0]
            fmt = rng.choice(INVOICE_FORMATS).replace("{pfx}", _prefix(name))
            v = base_record(vid, name, cat_key, entity, currency, city, cat["gl"], default_cc, terms, fmt)
            vendors.append(v)
            made += 1

    # Bank-detail changes across the history window (realistic background rate ~6%).
    demo_ids = {d["vendor_id"] for d in DEMO_VENDORS}
    changers = rng.sample([v for v in vendors if v["vendor_id"] not in demo_ids], k=int(len(vendors) * 0.06))
    for v in changers:
        when = HISTORY_START + timedelta(days=rng.randint(10, 520))
        old = v["bank"]["account_last4"]
        v["bank"] = _bank(rng, v["currency"])
        v["bank_change_log"].append({"date": when.isoformat(), "changed_by": "E30655",
                                     "old_last4": old, "new_last4": v["bank"]["account_last4"],
                                     "request_channel": rng.choice(["Supplier portal", "Email", "Letter"]),
                                     "callback_verified": True})

    # Two recent, properly verified bank changes so the Summit hold is about the missing call-back, not just recency.
    recent = [v for v in vendors if v["category"] in ("it_services", "courier") and not v["bank_change_log"]][:2]
    for i, v in enumerate(recent):
        old = v["bank"]["account_last4"]
        v["bank"] = _bank(rng, v["currency"])
        v["bank_change_log"].append({"date": (DEMO_DATE - timedelta(days=9 + i * 6)).isoformat(),
                                     "changed_by": "E30655", "old_last4": old,
                                     "new_last4": v["bank"]["account_last4"],
                                     "request_channel": "Supplier portal", "callback_verified": True})

    summit = next(v for v in vendors if v["vendor_id"] == "V4120")
    old = summit["bank"]["account_last4"]
    summit["bank"] = _bank(rng, "USD")
    summit["bank_change_log"].append({"date": date(2026, 10, 12).isoformat(), "changed_by": "E30655",
                                      "old_last4": old, "new_last4": summit["bank"]["account_last4"],
                                      "request_channel": "Email from accounts@summitfaci1ity.example",
                                      "callback_verified": False})
    return vendors
