# Production-grade rebuild — implementation plan

> Executed natively by Claude in one session (Rayford's choice: "you're building for me"). Task-ordered, not day-by-day. Each task ends with green tests and a commit.

**Goal:** Implement `docs/superpowers/specs/2026-10-07-prod-grade-rebuild-design.md`.
**Architecture:** FastAPI backend gains `backend/agents/` (tool registry, specialists, supervisor, investigator), run records, cases, sessions/permissions and policy versions on the existing state store; React front end gains run console, Model & data, Close, Inbox, Policies, Audit, Operations and diagram components.
**Tech stack:** Python 3.12, FastAPI, numpy, rapidfuzz, anthropic SDK; scikit-learn dev-only (training); React 19 + Vite + TS, Plotly; SQLite locally / Neon Postgres on Vercel; pytest, Playwright.
**Spec:** `docs/superpowers/specs/2026-10-07-prod-grade-rebuild-design.md`

## Global constraints

- Agent recommends; a person approves. The LLM never picks the GL account.
- No artificial sleeps on the server; presentation pace is client-side and labelled.
- Every accuracy figure is labelled "measured on synthetic data".
- No scikit-learn at runtime (numpy inference only).
- Standard R12 open-interface CSV formats only.
- All branding stays in `web/src/brand.ts`.
- Storyboard golden tests block deploy.

## Review focus

1. Re-running an invoice after a reviewer decision must not overwrite the decision or duplicate audit events → Task 2.
2. A user acting outside their role (approving out of turn, approving their own reclass) gets 403 and an audit event, never a silent success → Task 7.
3. Investigator returning invalid JSON or exceeding the tool budget falls back to the deterministic summary, never crashes the run → Task 4.
4. An unbalanced GL batch refuses export → Task 6.
5. A policy change after a run marks the run stale rather than silently changing displayed results → Task 7.

---

### Task 1: Seed data for the full process
**Files:** `scripts/datagen/intake.py`, `scripts/datagen/vendors.py`, `scripts/datagen/reference.py`, new `scripts/datagen/contracts.py`, `scripts/generate_data.py`, `tests/test_seed_data.py`; regenerated `data/seed/*.json`, `data/pdfs/*`.
- Storyboard invoices except `legal` and `learning_1` arrive in the 15 Oct morning mailbox (06:05–08:40); bank-change date shifts so it stays "2 days ago"; duplicate stays ≥ 9 days after `legal`.
- `receipt_evidence.json`: asset-register scans and signed order forms.
- `contracts.json`: rate cards and engagement letters for law firms and consultancies; Hartwell invoice gets timekeeper lines.
- New intake invoices: two split, one cut-off, one untaxed taxable goods, one intercompany, one employee reimbursement; discount-terms vendors; close calendar.
- Tests: invariants for each addition.

### Task 2: Agent runtime and run records
**Files:** new `backend/agents/{__init__,base,tools,specialists,supervisor}.py`; `backend/state.py`; `backend/service.py`; `backend/app.py`; `backend/engine/pipeline.py` (logic moves into specialists); `scripts/precompute.py`; tests `tests/test_agents.py`, `tests/test_engine.py`.
- Produces: `Supervisor.run(item, trigger, actor, on_event=None) -> dict` (result + `run`); `ToolRegistry.call(name, args) -> dict`; `service.latest(intake_id)`; runs stored under `run:{intake_id}:{n}` and `runlatest:{intake_id}`.
- Result keeps today's keys plus `run`. Status `NEW` for invoices without a run; GET never executes agents; `/run` streams real events; re-run diff.
- Tests: tool calls recorded per step; NEW until run; re-run after decision keeps decision; diff cause when receipt confirmed.

### Task 3: Process depth
**Files:** `backend/agents/specialists.py`, `backend/engine/policy.py`, `backend/engine/checks.py`, `backend/service.py`, `tests/test_process.py`.
- Routing exclusions, use-tax accrual, receipt evidence + SLA escalation with demo clock, splits, cut-off accrual, rate-card checks, terms/discount/payment hold, vendor-master and onboarding queues, blanket-PO requests.

### Task 4: Investigator
**Files:** `backend/agents/investigator.py`, `backend/llm.py`, `tests/test_investigator.py`.

### Task 5: Data-science layer
**Files:** `scripts/train.py`, `data/model/*`, `backend/model.py`, `backend/engine/recommend.py`, `backend/app.py`, `web/src/screens/Model.tsx`, `tests/test_model.py`.

### Task 6: Anomaly cases and close
**Files:** `backend/cases.py`, `backend/engine/exports.py`, `backend/service.py`, `backend/app.py`, `web/src/screens/Close.tsx`, `web/src/screens/Anomalies.tsx`, `tests/test_cases.py`.

### Task 7: Roles, permissions, policies, audit
**Files:** `backend/auth.py`, `backend/policies.py`, `backend/app.py`, `web/src/screens/{SignIn,Inbox,Policies,Audit}.tsx`, `web/src/App.tsx`, `tests/test_permissions.py`.

### Task 8: Invoice screen rebuild
**Files:** `web/src/screens/Review.tsx`, `web/src/components/RunConsole.tsx`, `web/src/api.ts`.

### Task 9: Architecture, agents, workflows
**Files:** `backend/app.py` (`/api/agents`), `web/src/components/{ContainerDiagram,AgentTopology,SequenceDiagram}.tsx`, `web/src/architecture.ts`, `web/src/workflows.ts`, `web/src/screens/Architecture.tsx`.

### Task 10: Hardening and release
**Files:** `backend/store.py`, `vercel.json`, `.github/workflows/ci.yml`, `web/e2e/*`, `web/src/screens/Operations.tsx`, `web/src/walkthrough.ts`, `docs/RUNBOOK.md`.

---

## Progress (updated 7 Oct, late)

Done and committed: Task 1 (seed), 2 (runtime), 3 (process depth), 4 (investigator), 5 (DS: train.py, model.py, metrics; history noise on a separate RNG), 6 (cases), 7 (roles, policies, audit, SOX pack), 8 (front-end rebuild: SignIn, Inbox, Review + RunConsole, Close, Model, Policies, Audit, Operations; App shell). 79 tests pass; `test_every_invoice_opens_from_cache` waits for the final live precompute.

Remaining:
- Task 9: Architecture page rebuild — `/api/agents` catalogue (tools grouped by agent), container diagrams with numbered flows + trust boundaries (as-built, Bedrock, Foundry), agent topology, 12 operational sequence diagrams (lifelines, request/return arrows, alt/opt/loop frames, timers, notes) with step-through and operational panels (trigger, SLA, RACI, SOX controls, KPIs, exceptions, systems).
- Task 10: Neon shared state on Vercel; cold start (lazy-load journals/cash/AR already cached_property; warm cron in vercel.json); GitHub Actions CI (pytest + tsc + lint); Playwright e2e of storyboard; walkthrough rewrite for new flow (sign-in, mailbox, console, Close, Model); RUNBOOK; live precompute (`uv run --env-file .env python -m scripts.precompute`) then deploy.
- Precompute must also warm investigations (storyboard holds) and should run after all logic changes.
