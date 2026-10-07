# Demo runbook — Non-PO Invoice Agent (15 Oct 2026)

## Run it locally

```bash
uv sync && pnpm --dir web install
cp .env.example .env            # add ANTHROPIC_API_KEY for live mode
uv run --env-file .env uvicorn backend.app:app --port 8001
pnpm --dir web dev              # http://localhost:5174
```

Ports: API 8001, web 5174. The `.claude/launch.json` entries `api` and `web` start the same two servers.

## Rebuild the data (only if the generators change)

```bash
uv run python -m scripts.generate_data      # seeded, ~1 s
uv run python -m scripts.render_pdfs        # 48 invoice PDFs + PNG previews (uses local Chrome)
uv run --env-file .env python -m scripts.precompute   # live: warms Claude extraction + reasons for storyboard invoices
uv run pytest                               # 20 checks; any failure blocks deploy
```

Run `precompute` with a key once before the demo: storyboard extractions and reasons are then cached, so replay
mode shows Claude's real output even with no network.

## Modes

| Setting | Effect |
|---|---|
| `DEMO_MODE=live` + key | Claude reads PDFs and writes reasons; cached after first run |
| `DEMO_MODE=replay` | Cached Claude output only; deterministic; works offline |
| `DEMO_OFFLINE=1` | Also skips VIES, OFAC refresh and FX calls (cached answers shown with their date) |
| `DEMO_PASSWORD` | Passcode screen in front of the hosted URL |
| `ENABLE_WILDCARD=0` | Hides "Process a new invoice…" |
| `VITE_BRAND=neutral` (build time) | Removes client marks |

## Before the session (Wed 14 Oct)

1. `Reset demo` in the app; open the queue on the **Workshop scenarios** filter.
2. Narrator's phone: open `/requester?person=E31188` (Julia Ortiz) or scan the QR on the legal invoice.
3. Run the walkthrough end to end once (28 steps, arrow keys work).
4. Record the backup video of the full flow.
5. Hot spare: the local servers above, in replay mode, on the same laptop. Phone hotspot as a third path.

## Storyboard map

| Scene | Invoice | What happens |
|---|---|---|
| 1 | Northline Communications INV-2026-0917 | Fast-track, 6310 / CC4420, standing receipt rule |
| 2 | Dell Technologies 7781452 | 6420 default overridden to 1540, Fixed Assets routing, PO-policy breach |
| 3 | Hartwell & Pryce 0098 | Matter register → Julia Ortiz confirms on her phone → Legal Ops → Director |
| 3 | Cloudline Analytics CLA-2026-114 | Prepaid 1310, 12 × $10,000 to 6350, GL_INTERFACE file |
| 4 | Hartwell & Pryce INV-0098 | Held: duplicate |
| 4 | Summit Facility Services SFS-55120 | Held: 2.6× norm, unverified bank change, look-alike domain, 7-day terms |
| 4 | Brightpath Advisory BPA-3391 | SoD: Diana Moreno is requester → Grace Okafor (VP) |
| Extra | Wavre Workplace Solutions WWS/2026/0412 | Held: VAT number not on EU VIES (checked live) |
| Extra | Halden Consulting | Matches open PO → three-way match |
| Learning | Deskright chargers (two invoices) | Override cost centre on the first; the second picks it up |
| 6 | Anomaly layer | Laptop refresh journal 6420 → 1540; cash misapplied to 30481 instead of 30418 |
