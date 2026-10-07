# Non-PO Invoice Agent — Brief Review & Implementation Plan

Baseline: *Mastercard_Demo_Brief_NonPO_Invoice_Agent_v0.2* (Ciklum, draft). Demo: Thu 15 Oct 2026, O'Fallon, ~12 min slot. Today: Wed 7 Oct.

---

## 1. Verdict on the brief

The brief is strong: it is built on the VPs' own words, the 8-step non-PO process is correct, the "LLM reads and explains, deterministic engine decides the recommendation" split is exactly right for a finance audience, and the storyboard has the right peak (Dell). Keep the structure. The changes below fix accounting errors an accountant in the room will spot, close gaps between "demo" and "real", and use scale data to make it land.

### 1.1 Errors to fix before build (an accountant will catch these)

| # | Issue | Why it matters | Fix |
|---|---|---|---|
| E1 | **Dell capitalisation doesn't work as written.** Threshold is "$5,000 per item or invoice"; each laptop is $1,845. Under a per-unit policy (the norm), these laptops would be **expensed to 6360 IT Consumables**, not capitalised to 1540. The brief's own CoA includes 6360 "below capitalisation threshold". | Nazeer will notice. It undermines the centrepiece. | Make the policy per-unit with a lower threshold for computer equipment: **$1,000 per unit for IT hardware, $5,000 per unit otherwise** (common in practice). Agent cites the policy row. Keep "agent routes, doesn't decide capitalisation". |
| E2 | **"No real vendor names" vs "Dell Technologies".** | Contradiction in the brief. | Keep Dell (it is Nazeer's example and the name is the hook) but confirm with engagement lead. All other vendors fictional. Invoice PDF must not copy Dell's real invoice design — generic layout, name as text only. |
| E3 | **Timings add to ~13.5 min** (13 for scenes + 0.5 bridge) against a ~12 min slot. | You will be cut off before the closing beat — the part that answers Nazeer and Vinay. | Fold Scene 5 (audit trail) into Scene 2: open the Dell audit trail right after approving it (saves ~1 min). Trim Scene 3 to 2 min. Target 11:30 with slack. |
| E4 | **Telecoms "standing rule" is ambiguous.** Brief says the cost-centre owner's approval confirms receipt, but invoice 1 routes to a director. | Inconsistent rule on screen. | Rule: "recurring category + within 10% of 6-month average → approver's approval doubles as receipt confirmation". Show it as a policy chip. |
| E5 | **Dell tax.** "$18,450 + tax" — tax on capitalised hardware is part of asset cost. | Detail a controller notices. | Use MO sales tax (St. Charles County rate) and code tax into 1540 with the line. |

### 1.2 Improvements (ranked by impact for the time)

1. **Use their scale, not 7 invoices.** The brief has 4k history lines and a 300-line cash file. Vinay said 10–12k settlement lines a day. Run the closing beat over **a full day: 11,400 cash lines** and **~2,500 close-period journal lines**, show it completes in seconds and surfaces the handful that matter. Queue shows "142 non-PO invoices received today — 118 touchless" with the demo invoices as the "needs a human" set. This is the difference between a toy and something that looks like their world.
2. **Make the agent visibly work.** Stream an agent trace on the review screen: *read PDF → matched vendor V1043 → searched 31,204 historic lines → 57 similar → policy: IT hardware requires PO → capitalisation rule → approver resolution → SoD check*, each step timed. This is what "agentic" looks like to a VP; a static result panel looks like a rules engine.
3. **One real, live human-in-the-loop moment.** In Scene 3 the "requester confirms receipt" lands as a real **Microsoft Teams adaptive card** (Power Automate HTTP-trigger flow in a Ciklum tenant) on the narrator's phone; they tap Confirm and the projector unlocks approval. Makes "built on the tools your CoE already uses" literally true without a full Power Platform build. Fallback: SMS/email signed link, same UX.
4. **Add a PO dataset and a new catch.** The brief has no POs. Add a PO register (POs, lines, receipts). New step-1 check: *"this non-PO invoice matches open PO 4500018872 — should be matched, not coded"*. Feeds Meredith's measure ("non-PO spend moved onto POs") and powers a **Procurement view**: repeat non-PO spend by vendor/category → blanket-PO candidates with $ and counts.
5. **Real external checks where free and credible** (public, none touch Mastercard systems):
   - **OFAC SDN sanctions screening** against the live US Treasury list (step 1; brief only talks about it).
   - **EU VIES VAT number validation** for an EU01 supplier (step 2).
   - **ECB FX rates** for the EUR invoice.
   - **ABA routing / IBAN checksum validation** on the bank-change hold (step 7).
6. **Format-accurate system outputs, not fake connections.** The brief rightly says don't claim Coupa/R12 integration. So produce real file formats: Oracle R12 **AP_INVOICES_INTERFACE / AP_INVOICE_LINES_INTERFACE** CSV for approved invoices, R12 **GL_INTERFACE** CSV for the SaaS amortisation and the journal reclass, and a procurement exception report. Real R12 column names are a credibility moment for Nazeer.
7. **Add one EUR invoice for EU01** (8th, background, not narrated unless asked) so multi-entity/currency/VAT is demonstrable on a question rather than "same pattern, more rules".
8. **Optional live wildcard** (toggle, decide at dry run): an unseen invoice emailed to the demo inbox during Q&A, processed live and uncached. Counters "it's staged". Only if dry runs are clean.
9. **Learning loop (F20) as a visible 20-second beat:** override one recommendation, re-run a near-identical background invoice, confidence shifts with "history updated by override, 14:02". Answers "what if it's wrong?".

### 1.3 Keep exactly as written

- LLM never picks the GL account; scores + evidence drive it. Top-3 similar past invoices as evidence.
- Confidence bands (90 / 60). "Recommends", never "decides". Synthetic-data label always visible.
- At least three things go wrong (duplicate, bank change, SoD).
- Q&A section and the "say but don't build" list.

### 1.4 Branding (decided: Mastercard-branded)

Overrides the brief's "Ciklum-styled" line. Guardrails so it stays a demo, not an implied production system:
- Mastercard logo, colours and type in the app chrome; "Demonstration on synthetic data · built by Ciklum" fixed in the header.
- Official logo file only (Mastercard Brand Center SVG), never redrawn; placed at `web/public/brand/mastercard-logo.svg`.
- Vercel URL password-protected — a public Mastercard-branded finance site could read as phishing.
- All branding in `web/src/brand.ts`; a `BRAND=neutral` switch exists in case the engagement lead asks for it to be pulled.

### 1.5 Model provider

Mastercard likely has its own "approved AI" (e.g. Azure OpenAI). LLM calls sit behind a provider interface; Claude used for the demo (native PDF input, structured output). Talk track: "runs on your approved model".

---

## 2. Architecture (Vercel)

Decision: **Option 2 (standalone web app)**, decided now rather than Fri 9 Oct — one week can't absorb Power Platform tenant risk, and the Teams card (1.2 #3) captures most of Option 1's message.

```
mastercard/
  web/                    React + Vite + TS + Plotly.js
    src/brand.ts          all branding: name, logo, colours, fonts, labels
    src/screens/          Intake, Review, Audit, AnomalyLayer, Procurement
  api/                    FastAPI (Vercel Python runtime)
    engine/
      extract.py          Claude PDF -> structured fields (cached by PDF hash)
      vendor.py           fuzzy vendor match, sanctions screen
      recommend.py        GL/CC/entity scoring: vendor freq + text similarity + amount fit
      policy.py           approval matrix, DoA limits, SoD, PO policy, cap threshold, prepaid
      checks.py           duplicate (fuzzy inv no.), amount vs norm, bank change, open-PO match
      explain.py          Claude writes the reason from scores + evidence (cached)
      anomaly.py          same scorer over journal lines; cash-app matcher
      exports.py          R12 AP/GL interface CSVs, procurement report
    integrations/         ofac.py, vies.py, fx.py, teams.py, bank_validate.py
    routes/               REST + SSE stream for the agent trace
  data/
    seed/                 generated JSON, loaded into memory at startup
    pdfs/                 7 demo + 1 EUR + ~40 background invoice PDFs
    cache/                LLM outputs for replay mode
  scripts/
    generate_data.py      seeded generator: reference, history, POs, journals, cash
    render_pdfs.py        HTML templates -> PDF (Playwright), per-vendor layouts
    warm_cache.py         runs extraction/explanations once, writes cache
```

**State.** Reference/history data is static JSON in memory. Mutable demo state (approvals, overrides, audit events, confirmations) must survive across serverless instances → **Neon Postgres** via Vercel Marketplace. "Reset demo" truncates mutable tables.

**Similarity.** TF-IDF vectors precomputed by the generator, shipped as `.npz`; runtime uses numpy only (keeps the Python bundle small; no scikit-learn at runtime).

**Streaming.** Agent trace via SSE. In replay mode, steps emit from cache with realistic pacing (< 10 s per invoice).

**Vercel.** Pro plan (Hobby forbids commercial use). Password-protected URL. Env: `ANTHROPIC_API_KEY`, `DATABASE_URL`, `TEAMS_FLOW_URL`, `DEMO_MODE=live|replay`. Freeze prod Wed 14 Oct evening.

**Venue resilience.**
1. Primary: Vercel URL.
2. Hot spare on the same laptop: `make demo-local` (Vite build + uvicorn + SQLite, replay mode) — identical UI, switch tabs in 5 s.
3. Phone hotspot.
4. Recorded full-flow video.

---

## 3. Data (expanded)

All synthetic, seeded, deterministic. USD except the EU01 EUR invoice.

| Dataset | Brief | Plan | Notes |
|---|---|---|---|
| Legal entities | 3 | 3 | US01, EU01, IN01 with ledger IDs, currencies, addresses |
| Chart of accounts | ~25 | ~60 | Full range incl. accruals, intercompany, clearing; R12 segments Entity-CC-Account-Product-IC-Future |
| Cost centres | ~30 | 45 | Owner → director → VP hierarchy |
| People / approver register | ~40 | 167 | Role, DoA limit, delegate, manager chain; requesters per cost centre |
| Vendor master | ~120 | 405 | Sites, default GL/CC, terms, masked bank, bank-change log, typical range, tax ID, sanctions status |
| Coding history | ~4,000 lines | 27,157 coded lines / 12,340 invoices, Apr 2025 – Sep 2026 | ~1% historic miscodes (most reclassified at close; ~100 still sitting, which the anomaly layer finds) |
| PO register | none | 5,078 POs (1,551 open), receipts | One non-PO intake invoice matches an open PO |
| Policies | 1 table each | same, E1 corrected | Approval matrix, PO policy, cap policy as editable JSON |
| Legal matters | ~15 | 40 | |
| Journal file | ~200 lines | ~4,100 lines / ~960 JEs (accruals, Aug reversals, receipt accruals, amortisation, depreciation, payroll, allocations, IC, revenue, FX, reclasses) | Planted: "Laptop refresh – Q3" $36,900 to 6420; duplicate legal accrual; audit fee to consulting; self-approved weekend JE |
| Cash application | ~300 lines | 11,400 receipts (one day), 2,400 customers, 29.6k AR items | 98.4% auto-applied; 127 exceptions; planted: 30418→30481 misapplication, double application, missed match, amount-only match |
| Intake queue | 7 | 142 | 118 touchless (done), demo set + EUR invoice in review |
| Invoice PDFs | 7 | ~48 | Distinct per-vendor layouts; one slightly skewed "scanned" PDF |

The brief's demo-invoice table stands, with E1/E5 applied to invoice 2 and the EUR invoice added.

---

Brief correction applied in data: J. Ortiz is **Senior Counsel (requester)**, not Legal Ops — Legal Ops (M. Feld) is the first approver, so Ortiz can't be both requester and approver.

Regenerate: `uv run python -m scripts.generate_data` (seeded, ~1 s). Invariants: `uv run pytest tests/test_seed_data.py`.

## 4. Screens

1. **Intake queue** — today's 142 with status chips; "Needs review" filter; KPI strip.
2. **Invoice review** — PDF left; right: extracted fields with source highlights, live agent trace, recommendation + confidence band, reasons, top-3 similar invoices, flags, receipt confirmation, approval chain with SoD/limit checks; Approve / Override (reason required) / Reject.
3. **Audit trail** — per-invoice timeline; export ("SOX evidence").
4. **Anomaly layer** — journal + cash runs with counts, run time, ranked flags with reasons; GL_INTERFACE reclass download.
5. **Procurement & value** — non-PO spend by category, PO-policy breaches, blanket-PO candidates, the brief's five success measures (Plotly).

Projector rules from the brief stand.

---

## 5. Schedule

| Day | Work | Exit criterion |
|---|---|---|
| Wed 7 Oct | Decisions (§6); scaffold; `brand.ts`; Vercel + Neon projects | Empty app live on Vercel behind password |
| Thu 8 Oct | Kick-off. Data generator complete. PDF templates | All seed data generated; 7 demo PDFs render |
| Fri 9 Oct | Extraction (cached), vendor match, recommender, policy, checks; golden tests | API returns correct outcome for all 8 invoices |
| Sat–Sun 10–11 | Buffer / UI start | |
| Mon 12 Oct | Intake + Review, SSE trace. Nazeer call 06:00 CT — fold answers in | Scenes 1–2 run end to end |
| Tue 13 Oct | Controls, audit, anomaly layer, procurement, exports, OFAC/VIES/FX, Teams card, replay mode, local hot spare | Full storyboard runs, live and replay |
| Wed 14 Oct | Finance sense-check; 3 timed dry runs; record video; offline test; prod freeze | Two clean dry runs under 12 min |
| Thu 15 Oct | Demo | |

Testing: pytest golden cases for the 8 demo invoices (account, confidence band, route, flags) plus the two closing-beat flags. A golden failure blocks deploy.

---

## 6. Decisions (7 Oct)

1. **Branding:** Mastercard-branded (see 1.4).
2. **Teams:** no tenant. Replacement: a **requester phone view** — narrator scans a QR code before the demo; the confirm-receipt task appears on their phone as a mobile approval screen (J. Ortiz); tapping Confirm unlocks approval on the projector. Real second device, no third-party dependency.
3. **Dell name:** keep.
4. **Model:** Claude, with "runs on your approved model" talk track.
5. **Live wildcard invoice:** build behind a toggle; decide at dry run.
6. **Brand assets:** Mastercard logo (official SVG) — supplied by Rayford.
