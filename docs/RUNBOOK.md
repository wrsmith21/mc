# Demo runbook — CLEAR (15 Oct 2026)

CLEAR: Coding, Ledger, Exceptions, Approvals, Reconciliation. The agent that works non-PO invoices end to end,
then sweeps the close journals, the AP subledger and cash application for the same mistakes.

## Run it locally

```bash
uv sync && pnpm --dir web install
cp .env.example .env            # add ANTHROPIC_API_KEY for live mode, DEMO_PASSWORD for the passcode screen
uv run --env-file .env uvicorn backend.app:app --port 8001
pnpm --dir web dev              # http://localhost:5174
```

Ports: API 8001, web 5174. `.claude/launch.json` entries `api` and `web` start the same two servers.
Delete `data/state.db` (or press Reset demo) to return to the morning of 15 October.

## Rebuild after changes

| Changed | Run | Why |
|---|---|---|
| Data generators | `uv run python -m scripts.generate_data` then `uv run python -m scripts.render_pdfs` | Seeded; PDFs + previews use local Chrome |
| History or the recommender | `uv run python -m scripts.train` | Back-test, calibration, model card in `data/model/` |
| Any agent logic, prompt or data | `uv run --env-file .env python -m scripts.precompute` | Overnight batch + warms every Claude call the demo can make |
| Anything | `uv run pytest` and `pnpm --dir web build` | CI runs the same; a failure blocks deploy |

`tests/test_engine.py::test_every_invoice_opens_from_cache` fails if a logic change was pushed without re-running
precompute: that would mean live model calls on first open.

## Modes

| Setting | Effect |
|---|---|
| `DEMO_MODE=live` + key | Claude reads PDFs, writes reasons and investigates exceptions; cached after first call |
| `DEMO_MODE=replay` | Cached Claude output only; deterministic fallbacks when not cached; works offline |
| `DEMO_OFFLINE=1` | Also skips VIES, OFAC refresh and FX calls (cached answers shown with their date) |
| `DEMO_PASSWORD` | Passcode screen in front of the hosted URL; also signs the session cookie |
| `DATABASE_URL` | Neon Postgres for shared state across Vercel instances (required for a multi-person room) |
| `ENABLE_WILDCARD=0` | Hides "Process a new invoice…" |
| `VITE_BRAND=neutral` (build time) | Removes client marks |

## People to sign in as

| Person | Role | Use for |
|---|---|---|
| Alex Rivera | AP specialist | Driving the storyboard: run the mailbox, decide, re-run |
| Julia Ortiz | Requester | Confirms the legal invoice on the phone view |
| Grace Okafor | VP, approver | SoD reroute approval |
| Nadia Petrova | Vendor master | Call-back on the Summit bank change; onboard Quickfix Plumbing |
| Ben Keller | GL accountant | Prepares the laptop-journal reclass |
| Samuel Whitaker | Controller | Approves and posts the reclass batch |
| Hana Zhang / Priya Nair | Cash application / lead | Re-apply the misapplied receipt |
| Sofia Lindgren | Procurement | Blanket-PO requests |
| Tessa Mendes | Admin | Policies, demo clock (advance 24h for SLA escalations), reset |

## Before the session (Wed 14 Oct)

1. Open the site 5 minutes before; the sign-in screen warms the service. Sign in as Alex Rivera.
2. Reset demo. My work shows 40 invoices in this morning's mailbox.
3. Narrator's phone: scan the QR on the legal invoice (opens Julia Ortiz's task).
4. Presentation pace on (header) if the room needs time to read the console.
5. Run the walkthrough once end to end; record the backup video.
6. Hot spare: local servers in replay mode on the same laptop; phone hotspot as a third path.

## Storyboard map

| Scene | Invoice | What happens |
|---|---|---|
| Set-up | Morning mailbox (40) | Run the agent on all; rows flip as each finishes |
| 1 | Northline Communications INV-2026-0917 | Fast-track 6310 / CC4420 at calibrated ~99%; standing receipt rule; console shows ~30 tool calls |
| 2 | Dell Technologies 7781452 | 6420 default overridden to 1540; asset-register scan evidences receipt; Fixed Assets routing; PO-policy breach |
| 3 | Hartwell & Pryce 0098 | Timekeeper rates match EL-V2007-2025; M-2207 at 82% of budget; Julia Ortiz confirms on her phone; Legal Ops → Director |
| 3 | Cloudline Analytics CLA-2026-114 | Prepaid 1310, 12 × $10,000 to 6350; signed order form evidences receipt |
| 4 | Hartwell & Pryce INV-0098 | Held: duplicate; investigator explains |
| 4 | Summit Facility Services SFS-55120 | Held: 2.6× norm, bank change 2 days ago from a look-alike domain; investigator recommends; vendor master call-back (fraud → rejected) |
| 4 | Brightpath Advisory BPA-3391 | SoD: Diana Moreno is requester → Grace Okafor; SOW-BPA-0926 fixed fee matches |
| Extra | Wavre Workplace Solutions | VAT not on EU VIES (live) |
| Extra | Halden Consulting | Matches open PO → three-way match |
| Extra | Rate-variance law firm | Senior associate billed $720 against a $650 card |
| Extra | Training (split), analytics seats (entity split), tax advisory (unaccrued September), access points (use tax), 2/10 vendors (discount), IC recharge and reimbursement (routed out), Quickfix Plumbing (onboarding) | Each step of the 8-step process, built |
| Learning | Deskright chargers (two invoices) | Override cost centre on the first; the second's earlier run is marked stale; re-run picks it up |
| 6 | Close | Laptop journal 6420 → 1540 prepared by Ben Keller, approved by Samuel Whitaker, posted as GL_INTERFACE; cash misapplied to 30481 → 30418 |
| Under the hood | Model and data, Architecture | Back-test, calibration, model card; container diagrams, agent catalogue, 12 sequence workflows |
