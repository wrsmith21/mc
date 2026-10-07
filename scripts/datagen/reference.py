from datetime import date

DEMO_DATE = date(2026, 10, 15)
HISTORY_START = date(2025, 4, 1)
HISTORY_END = date(2026, 9, 30)

ENTITIES = [
    {"code": "US01", "name": "US Operating Entity", "ledger_id": 2021, "org_id": 101, "currency": "USD",
     "country": "US", "city": "O'Fallon, MO", "tax_regime": "US sales & use tax"},
    {"code": "EU01", "name": "European Entity", "ledger_id": 2041, "org_id": 201, "currency": "EUR",
     "country": "BE", "city": "Waterloo, Belgium", "tax_regime": "EU VAT"},
    {"code": "IN01", "name": "India GBSC Entity", "ledger_id": 2061, "org_id": 301, "currency": "INR",
     "country": "IN", "city": "Pune, India", "tax_regime": "GST"},
]

# R12 accounting flexfield: Entity.CostCentre.Account.Product.Intercompany.Future
SEGMENT_STRUCTURE = ["entity", "cost_centre", "account", "product", "intercompany", "future"]

CHART_OF_ACCOUNTS = [
    ("1010", "Cash – Operating Accounts", "Asset", "BS"),
    ("1020", "Cash – Settlement Accounts", "Asset", "BS"),
    ("1210", "Accounts Receivable – Trade", "Asset", "BS"),
    ("1220", "Accounts Receivable – Intercompany", "Asset", "BS"),
    ("1230", "Unapplied Cash", "Asset", "BS"),
    ("1310", "Prepaid Expenses", "Asset", "BS"),
    ("1320", "Prepaid Insurance", "Asset", "BS"),
    ("1410", "Input VAT / GST Recoverable", "Asset", "BS"),
    ("1520", "Leasehold Improvements", "Fixed asset", "BS"),
    ("1530", "Network Equipment", "Fixed asset", "BS"),
    ("1540", "Computer Hardware", "Fixed asset", "BS"),
    ("1545", "Servers & Storage", "Fixed asset", "BS"),
    ("1550", "Furniture & Fixtures", "Fixed asset", "BS"),
    ("1560", "Capitalised Software", "Fixed asset", "BS"),
    ("1580", "Assets Under Construction", "Fixed asset", "BS"),
    ("1590", "Accumulated Depreciation", "Contra asset", "BS"),
    ("1810", "Right-of-Use Assets", "Asset", "BS"),
    ("2110", "Accounts Payable – Trade", "Liability", "BS"),
    ("2120", "Accounts Payable – Intercompany", "Liability", "BS"),
    ("2130", "GR/IR Clearing", "Liability", "BS"),
    ("2150", "Accrued Liabilities", "Liability", "BS"),
    ("2160", "Accrued Payroll & Bonus", "Liability", "BS"),
    ("2210", "Sales Tax Payable", "Liability", "BS"),
    ("2220", "Use Tax Payable", "Liability", "BS"),
    ("2230", "VAT / GST Payable", "Liability", "BS"),
    ("2310", "Deferred Revenue", "Liability", "BS"),
    ("2410", "Customer Settlement Obligations", "Liability", "BS"),
    ("2810", "Lease Liabilities", "Liability", "BS"),
    ("4010", "Transaction Processing Revenue", "Revenue", "PL"),
    ("4020", "Cross-Border Revenue", "Revenue", "PL"),
    ("4110", "Value-Added Services Revenue", "Revenue", "PL"),
    ("4910", "Intercompany Service Revenue", "Revenue", "PL"),
    ("6110", "Salaries & Wages", "Expense", "PL"),
    ("6120", "Bonus & Incentives", "Expense", "PL"),
    ("6310", "Telecommunications", "Expense", "PL"),
    ("6340", "Cloud & Hosting Services", "Expense", "PL"),
    ("6350", "Software Subscriptions", "Expense", "PL"),
    ("6360", "IT Consumables (below capitalisation threshold)", "Expense", "PL"),
    ("6370", "Market Data Services", "Expense", "PL"),
    ("6420", "Repairs & Maintenance", "Expense", "PL"),
    ("6430", "Facilities Services", "Expense", "PL"),
    ("6440", "Utilities", "Expense", "PL"),
    ("6450", "Security Services", "Expense", "PL"),
    ("6460", "Office Supplies", "Expense", "PL"),
    ("6470", "Postage & Courier", "Expense", "PL"),
    ("6480", "Printing & Reprographics", "Expense", "PL"),
    ("6510", "Professional Fees – Consulting", "Expense", "PL"),
    ("6520", "Professional Fees – Audit & Tax", "Expense", "PL"),
    ("6530", "Contract Labour", "Expense", "PL"),
    ("6540", "Research & Advisory Subscriptions", "Expense", "PL"),
    ("6550", "Translation Services", "Expense", "PL"),
    ("6610", "Legal Fees", "Expense", "PL"),
    ("6710", "Travel & Entertainment", "Expense", "PL"),
    ("6720", "Meals & Catering", "Expense", "PL"),
    ("6810", "Marketing Services", "Expense", "PL"),
    ("6820", "Events & Sponsorships", "Expense", "PL"),
    ("6910", "Training", "Expense", "PL"),
    ("6920", "Recruitment Fees", "Expense", "PL"),
    ("6930", "Dues & Memberships", "Expense", "PL"),
    ("6940", "Insurance", "Expense", "PL"),
    ("7010", "Depreciation", "Expense", "PL"),
    ("7020", "Amortisation", "Expense", "PL"),
    ("7110", "Bank Charges", "Expense", "PL"),
    ("7210", "Foreign Exchange Gain / Loss", "Expense", "PL"),
    ("7910", "Intercompany Service Charges", "Expense", "PL"),
]

# (code, name, entity, function)
COST_CENTRES = [
    ("CC4410", "IT End-User Services", "US01", "IT"),
    ("CC4420", "Infrastructure", "US01", "IT"),
    ("CC4430", "Cloud Platforms", "US01", "IT"),
    ("CC4440", "Cyber Security", "US01", "IT"),
    ("CC4450", "Enterprise Applications", "US01", "IT"),
    ("CC4460", "Data Platforms", "US01", "IT"),
    ("CC4470", "IT Service Desk – Pune", "IN01", "IT"),
    ("CC4480", "Network Engineering", "US01", "IT"),
    ("CC4490", "IT Asset Management", "US01", "IT"),
    ("CC5100", "Legal", "US01", "Legal"),
    ("CC5110", "Legal Operations", "US01", "Legal"),
    ("CC5120", "Regulatory Compliance", "US01", "Legal"),
    ("CC5130", "Privacy Office – Europe", "EU01", "Legal"),
    ("CC5200", "Facilities – O'Fallon Campus", "US01", "Facilities"),
    ("CC5210", "Facilities – New York", "US01", "Facilities"),
    ("CC5220", "Facilities – Waterloo", "EU01", "Facilities"),
    ("CC5230", "Facilities – Pune", "IN01", "Facilities"),
    ("CC5240", "Corporate Security", "US01", "Facilities"),
    ("CC5250", "Workplace Services", "US01", "Facilities"),
    ("CC6100", "Brand Marketing", "US01", "Marketing"),
    ("CC6110", "Digital Marketing", "US01", "Marketing"),
    ("CC6120", "Events & Sponsorships", "US01", "Marketing"),
    ("CC6130", "Partner Marketing", "US01", "Marketing"),
    ("CC6140", "Marketing – Europe", "EU01", "Marketing"),
    ("CC7100", "Finance GBSC", "US01", "Finance"),
    ("CC7110", "Accounts Payable", "US01", "Finance"),
    ("CC7120", "Treasury", "US01", "Finance"),
    ("CC7130", "Tax", "US01", "Finance"),
    ("CC7140", "FP&A", "US01", "Finance"),
    ("CC7150", "Controllership", "US01", "Finance"),
    ("CC7160", "Internal Audit", "US01", "Finance"),
    ("CC7170", "GBSC Pune Operations", "IN01", "Finance"),
    ("CC7180", "Procurement", "US01", "Finance"),
    ("CC8100", "HR Operations", "US01", "HR"),
    ("CC8110", "Talent Acquisition", "US01", "HR"),
    ("CC8120", "Learning & Development", "US01", "HR"),
    ("CC8130", "Total Rewards", "US01", "HR"),
    ("CC9100", "Network Operations", "US01", "Operations"),
    ("CC9110", "Product Development", "US01", "Operations"),
    ("CC9120", "Customer Delivery", "US01", "Operations"),
    ("CC9130", "Data & Analytics", "US01", "Operations"),
    ("CC9140", "Fraud & Risk Solutions", "US01", "Operations"),
    ("CC9150", "Product Engineering – Europe", "EU01", "Operations"),
    ("CC9160", "Engineering – Pune", "IN01", "Operations"),
    ("CC9900", "Corporate Office", "US01", "Executive"),
]

# Directors cover groups of cost centres; VPs cover a function.
DIRECTOR_GROUPS = {
    "IT – Workplace Technology": ["CC4410", "CC4470", "CC4490"],
    "IT – Infrastructure & Cloud": ["CC4420", "CC4430", "CC4480"],
    "IT – Security & Applications": ["CC4440", "CC4450", "CC4460"],
    "Legal": ["CC5100", "CC5110"],
    "Compliance & Privacy": ["CC5120", "CC5130"],
    "Real Estate & Facilities": ["CC5200", "CC5210", "CC5220", "CC5230", "CC5250"],
    "Corporate Security": ["CC5240"],
    "Marketing": ["CC6100", "CC6110", "CC6130", "CC6140"],
    "Events": ["CC6120"],
    "Finance GBSC": ["CC7100", "CC7110", "CC7170"],
    "Treasury & Tax": ["CC7120", "CC7130"],
    "Controllership & FP&A": ["CC7140", "CC7150", "CC7160", "CC7180"],
    "People": ["CC8100", "CC8110", "CC8120", "CC8130"],
    "Network & Delivery": ["CC9100", "CC9120"],
    "Product & Data": ["CC9110", "CC9130", "CC9140"],
    "Engineering International": ["CC9150", "CC9160"],
    "Office of the CEO": ["CC9900"],
}

VP_FUNCTIONS = {
    "IT": "VP, Technology Operations",
    "Legal": "VP & Deputy General Counsel",
    "Facilities": "VP, Global Real Estate",
    "Marketing": "VP, Marketing",
    "Finance": "VP, Finance Operations",
    "HR": "VP, People",
    "Operations": "VP, Network & Product Operations",
    "Executive": "Chief of Staff",
}

APPROVAL_LIMITS = {"Manager": 10_000, "Director": 100_000, "VP": 1_000_000, "SVP": None}

APPROVAL_MATRIX = {
    "tiers": [
        {"min": 0, "max": 10_000, "approver": "cost_centre_owner", "label": "Under $10k: cost-centre owner"},
        {"min": 10_000, "max": 100_000, "approver": "director", "label": "$10k–$100k: director"},
        {"min": 100_000, "max": None, "approver": "vp", "label": "Over $100k: VP"},
    ],
    "category_overrides": [
        {"category": "legal", "min": 0, "first_approver": ["legal_ops"],
         "label": "Legal fees (any amount): Legal Operations reviews first"},
        {"category": "it_hardware", "min": 5_000, "first_approver": ["it_procurement", "fixed_assets"],
         "label": "IT hardware over $5k: IT Procurement and Fixed Asset Accounting"},
    ],
    "separation_of_duties": "Requester can never approve their own spend; route to the next eligible approver up the chain.",
}

CAPITALISATION_POLICY = {
    "basis": "per_unit",
    "rules": [
        {"asset_class": "Computer Hardware", "account": "1540", "threshold_per_unit": 1_000,
         "expense_account_below": "6360", "useful_life_months": 36},
        {"asset_class": "Servers & Storage", "account": "1545", "threshold_per_unit": 5_000,
         "expense_account_below": "6360", "useful_life_months": 60},
        {"asset_class": "Network Equipment", "account": "1530", "threshold_per_unit": 5_000,
         "expense_account_below": "6360", "useful_life_months": 60},
        {"asset_class": "Furniture & Fixtures", "account": "1550", "threshold_per_unit": 5_000,
         "expense_account_below": "6460", "useful_life_months": 84},
    ],
    "tax_treatment": "Non-recoverable sales tax and freight are capitalised with the asset.",
    "owner": "Fixed Asset Accounting decides capitalisation; the agent only routes.",
}

PO_POLICY = {
    "required": [
        {"category": "it_hardware", "min": 0, "label": "IT hardware – any amount"},
        {"category": "furniture", "min": 0, "label": "Furniture & fit-out – any amount"},
        {"category": "consulting", "min": 25_000, "label": "Consulting & professional services over $25k"},
        {"category": "contract_labour", "min": 25_000, "label": "Contract labour over $25k"},
        {"category": "marketing", "min": 50_000, "label": "Marketing services over $50k"},
        {"category": "events", "min": 50_000, "label": "Events & sponsorships over $50k"},
    ],
    "exempt": ["telecoms", "utilities", "legal", "saas", "insurance", "memberships", "market_data",
               "audit_tax", "courier"],
    "exempt_label": "Utilities, telecoms, legal, insurance, memberships and subscription renewals under contract",
}

PREPAID_POLICY = {
    "min_service_months": 2,
    "min_amount": 10_000,
    "prepaid_account": "1310",
    "insurance_prepaid_account": "1320",
    "label": "Service periods over one month and $10k+ are prepaid and amortised straight-line monthly.",
}

RISK_POLICY = {
    "amount_vs_norm_multiple": 2.5,
    "bank_change_window_days": 30,
    "duplicate_window_days": 45,
    "confidence_bands": {"fast_track": 0.90, "review": 0.60},
    "standing_receipt_rule": "Recurring service categories billed monthly, within 10% of the 6-month average: "
                             "the approver's approval doubles as receipt confirmation.",
    "standing_receipt_categories": ["telecoms", "utilities", "cloud", "saas", "facilities", "security",
                                    "it_services", "courier", "catering", "market_data", "office_supplies",
                                    "contract_labour"],
    "standing_receipt_tolerance": 0.10,
}

FX_MONTHLY = {
    # month -> (USD per EUR, INR per USD); month-end rates used for history translation
    "2025-04": (1.1376, 85.48), "2025-05": (1.1347, 85.58), "2025-06": (1.1787, 85.75),
    "2025-07": (1.1415, 87.56), "2025-08": (1.1686, 88.10), "2025-09": (1.1741, 88.79),
    "2025-10": (1.1534, 88.77), "2025-11": (1.1599, 89.46), "2025-12": (1.1711, 89.88),
    "2026-01": (1.1632, 90.21), "2026-02": (1.1548, 90.06), "2026-03": (1.1489, 90.65),
    "2026-04": (1.1527, 91.02), "2026-05": (1.1605, 90.88), "2026-06": (1.1683, 91.34),
    "2026-07": (1.1592, 91.71), "2026-08": (1.1648, 91.95), "2026-09": (1.1704, 92.18),
    "2026-10": (1.1689, 92.30),
}


def to_usd(amount: float, currency: str, month: str) -> float:
    eur_usd, usd_inr = FX_MONTHLY[month]
    if currency == "USD":
        return round(amount, 2)
    if currency == "EUR":
        return round(amount * eur_usd, 2)
    return round(amount / usd_inr, 2)
