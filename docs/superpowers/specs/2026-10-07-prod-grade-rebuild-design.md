# Non-PO Invoice Agent: production-grade rebuild — design

Date: 7 Oct 2026 · Owner: Rayford Smith · Deadline: freeze Wed 14 Oct evening, workshop Thu 15 Oct (O'Fallon)
Baseline: v0.2 brief (`~/Downloads/Mastercard_Demo_Brief_NonPO_Invoice_Agent_v0.2.docx`), `docs/PLAN.md`, current code at `48e49be`.

## 1. Intent

**Outcome.** A DEV-grade application Rayford can demo to Mastercard GBSC Finance (Meredith/P2P, Nazeer/R2R, Vinay/Cash App, Ashlie/SVP) without hedging: every screen does what it appears to do, every number is measured, every action is permissioned and audited.

**What Rayford said.** The current build feels surface-level and POC. "Run agent" is ambiguous (has it already run?). The anomaly layer can't be acted on. There is no visible data-science layer (what it is trained on, how much). Architecture and operational workflows lack detail; workflows must be sequence diagrams (vertical bar per component, arrows back and forth). Agents need to be revisited in detail. Scope: everything, by 15 Oct.

**Decisions taken.** Hybrid agent runtime (deterministic specialists always run; Claude investigates exceptions with read-only tools). Champion/challenger coding model with time-based back-test and calibration. All seven work areas by 15 Oct, with a cut order (section 10).

**Success criteria.**
1. Pressing "Run agent" on a new invoice executes the agents for real; the screen shows recorded tool calls with real timings, and nothing is replayed with artificial sleeps.
2. Every confidence figure is a calibrated probability backed by a back-test shown on the Model & data page.
3. Every anomaly finding can be worked to an exported, SoD-approved correction or a dismissal with reason.
4. Each of the brief's 8 process steps is built, not only talked about.
5. A person can only perform actions their role permits; the server enforces it.
6. Architecture, agent catalogue and 12 operational sequence diagrams are rendered from data that matches the code.
7. Two clean timed dry runs on Wed 14 Oct; all tests green in CI.

**Constraints kept from the brief.** Agent recommends, a person approves (autonomy level 1). LLM never picks the GL account. Synthetic data only, labelled. Standard R12 open-interface files, no screen-scraping. Accuracy figures are "measured on synthetic data", never product claims. Mastercard branding per the 7 Oct decisions.

## 2. Agent runtime (`backend/agents/`)

### 2.1 Structure

```
backend/agents/
  base.py          Tool, ToolCall, Finding, AgentStep, Run dataclasses; ToolRegistry
  registry.py      registers every tool with name, description, input/output JSON schema
  supervisor.py    runs specialists in fixed order, merges findings, decides status, triggers investigator
  intake.py        Intake & extraction agent
  supplier.py      Supplier & validity agent (incl. routing exclusions, tax)
  price.py         Price agent (new): rate card, engagement letter, matter budget, amount vs norm
  coding.py        Coding & treatment agent (model inference, splits, capitalise, prepaid, cut-off accrual)
  risk.py          Payment risk agent (incl. terms, early-pay discount)
  approval.py      Approval & receipt agent (requester, receipt rule, SLA timers, routing)
  investigator.py  Claude tool-use loop over read-only tools, exceptions only
  anomaly.py       Anomaly sweep agent (journals, AP subledger, cash) producing cases
```

Existing `engine/checks.py`, `engine/policy.py`, `engine/recommend.py`, `engine/anomaly.py` and `integrations/external.py` become tool implementations behind the registry. Their logic is retained; signatures are wrapped, not rewritten.

### 2.2 Tool contract

```python
@dataclass
class Tool:
    name: str            # e.g. "vendor.resolve"
    agent: str           # owning agent
    description: str
    input_schema: dict   # JSON schema
    output_schema: dict
    read_only: bool      # investigator may only call read_only tools
    fn: Callable[[dict], dict]
```

Every invocation produces a `ToolCall {id, tool, args, result_summary, ms, source: live|cache|computed, error?}` appended to the current `AgentStep`. Schemas have the same shape as Bedrock action-group and Foundry OpenAPI tool definitions; `/api/agents` serves the registry for the architecture page.

### 2.3 Run record

```
Run {
  run_id, intake_id, trigger: batch|manual|upload|rerun, actor, started_at, finished_at, ms,
  policy_version, coding_model: {id, version}, llm_model,
  steps: [AgentStep {agent, label, process_step, status, detail, facts[], tool_calls[], findings[], ms}],
  findings[], status, status_after_receipt, explanation, explanation_meta,
  investigation?: {summary, evidence[{text, tool_call_id}], next_action, confidence, tool_calls[]},
  tokens: {input, output}, cost_usd, previous_run_id?, diff?: [{field, before, after, cause}]
}
```

Persisted in a new `runs` table (SQLite locally, Postgres on Vercel). Invoice detail returns the latest run; run history is listed per invoice.

### 2.4 Intake states and "Run agent"

- Demo start state: the overnight batch (trigger `batch`, 15 Oct 02:00) has run on all invoices received before 14 Oct 18:00. Invoices received after that, including all storyboard invoices, are **New — not yet worked** and have no run.
- Opening a New invoice shows the PDF and "Not yet worked by the agent"; the rail is empty.
- "Run agent" creates a run and streams events **as they are produced** (supervisor callback per tool call and step) over SSE. The server never sleeps.
- **Presentation pace** (header toggle, on during the walkthrough): the client paces the display of events it has already received; a label reads "Display slowed for presentation · actual run 142 ms".
- Opening an already-worked invoice shows the latest run with its time and trigger ("Worked by overnight batch at 02:00"). The button reads "Re-run agent"; the result panel shows the diff against the previous run with its cause (receipt confirmed, correction learned, policy v3 → v4).
- GET invoice no longer re-executes the agents; it reads the latest run plus current overlays (decision, receipt task). Learned corrections and policy changes take effect on the next run, and the UI says so ("A correction for this supplier was learned after this run — re-run to apply").

### 2.5 Investigator (Claude, exceptions only)

- Triggers: status HELD, NEEDS_CODING, VENDOR_ONBOARDING, or an anomaly case opened.
- Read-only tools: `vendor.profile`, `vendor.bank_change_log`, `history.vendor_invoices`, `history.similar_lines`, `invoice.compare`, `po.open_for_vendor`, `policy.approval_matrix`, `people.directory`, `ar.open_items_for_customer` (cash cases), `journal.entry` (journal cases).
- Loop: Claude Messages API with tool use, at most 8 tool calls and 45 s; structured final output `{summary, evidence[{text, tool_call_id}], next_action ∈ fixed enum per case type, confidence}` validated by JSON schema; invalid output falls back to a deterministic summary built from the findings.
- Cannot write, change status or call tools that are not read-only. Every call is logged in the run.
- Cached per (case inputs hash, model, prompt version) for replay mode; live in live mode.

### 2.6 Agent console (invoice screen)

Run header (run id, trigger, actor, time, total ms, policy and model versions, tokens and cost) → one section per agent in process order → expandable tool calls (args, result summary, ms, live/cache) → investigator thread (each tool call and the evidence that cites it). Replaces the current ProcessRail detail; the rail stays as the summary.

## 3. Data-science layer

### 3.1 Training and back-test (`scripts/train.py`, scikit-learn dev-only)

- Dataset: coding-history lines; label = final (corrected) GL account; a second head for cost centre.
- Time split: train Apr 2025 – Apr 2026; calibration May – Jun 2026; test Jul – Sep 2026. No leakage: the champion's history index is built from training months only.
- Champion: current similarity engine (TF-IDF vote + vendor frequency + amount fit).
- Challenger: multinomial logistic regression on word 1–2-gram and char 3–5-gram TF-IDF of the description, one-hot vendor and vendor category, entity, log amount, log unit price.
- Calibration: isotonic regression per model on the calibration window.
- Metrics on test: top-1 (first-time-right), top-3, macro-F1, per-category accuracy, cost-centre accuracy, accuracy and coverage per confidence band, expected calibration error and reliability curve, top confusion pairs, **reclasses avoided** (historic miscoded test lines where the model predicts the corrected account), learning-loop lift (replay corrections month by month and re-score).
- Band thresholds: fast-track = lowest calibrated confidence where test precision ≥ 98%; review floor = where precision ≥ 80%. Written to policy as proposed values for an admin to accept.
- Production model selected by test first-time-right; tie-break on calibration error.
- Artifacts in `data/model/`: `model_card.json`, `metrics.json`, `challenger_weights.npz` (coefficients, vocabularies, idf), `calibration.json`, `dataset_manifest.json`. Runtime inference uses numpy only.

### 3.2 Runtime

Each recommendation records model id and version, calibrated confidence, raw score, top contributing features (top tokens with weights, vendor prior, amount fit), and alternatives with probabilities. Evidence (similar past invoices) stays.

### 3.3 Model & data page (`/model`)

Dataset inventory (every seed dataset: rows, date range, entities, how generated, which agent uses it) · method · champion vs challenger table · reliability chart · accuracy by band and by category · confusion pairs · reclasses avoided · learning-loop lift · monitoring plan (override rate, weekly confidence PSI, accuracy on corrections; retrain trigger: override rate > 8% for 2 weeks or PSI > 0.2) · model card (intended use, out of scope, limitations, owner, approval, data-use statement). Every figure labelled "measured on synthetic data".

## 4. Anomaly cases and controller workspace

### 4.1 Case model

`Case {case_id, source: journals|ap_ledger|cash, type, finding, amount, currency, entity, period, owner, status, sla_due, created_at, proposed_fix?, decision_log[], investigation?}`

Status flow: Open → In review → Fix proposed → Pending approval → Approved → Exported; or Dismissed (reason: valid as posted | already corrected | below materiality | false positive).

### 4.2 Fixes

| Case type | Fix drafted by agent | Approver | Output |
|---|---|---|---|
| Miscoded journal / AP line | Reclass JE (Dr suggested, Cr original), open period, reference to source | Controller | GL_INTERFACE batch |
| Duplicate accrual | Reversal JE | Controller | GL_INTERFACE batch |
| Self-approved JE | Retrospective review record, or escalation to SOX control owner | Controller | Review evidence |
| Misapplied cash | Unapply + reapply pair | Cash application lead | Receipt reapplication file (CSV) |
| Unapplied receipt with match | Apply to proposed AR invoice (bulk when confidence ≥ 0.95) | Cash application lead | Receipt application file |

SoD: approver ≠ preparer and ≠ original JE preparer. GL batch control totals: Dr = Cr, line count, value; export is refused if unbalanced.

### 4.3 Feedback

A confirmed miscode becomes a corrected history line (feeds the next training run and the runtime index). A dismissal "valid as posted" becomes a suppression rule `{vendor | account | description key}` that the next sweep honours.

### 4.4 Close dashboard (`/close`)

Open cases and value at risk by source, ageing against SLA, reclasses approved and exported, materiality filter, workload per owner.

## 5. Process depth (8 steps)

| Step | Built |
|---|---|
| 1 | Intercompany vendor → IC route; employee reimbursement → Concur route; vendor onboarding queue (KYC/W-9, sanctions, bank verification tasks) |
| 2 | Use-tax accrual when taxable goods are invoiced without tax (MO, St. Charles County rate); EU VAT and mandatory fields retained |
| 3 | Receipt SLA: reminder at 3 business days, escalate to cost-centre owner at 5, back to supplier for a named contact if unclaimed; labelled admin "advance clock" |
| 4 | Line splits across cost centres and entities; cut-off accrual + reversal when a service period straddles a closed month-end; GL date and open-period logic |
| 5 | Rate cards and engagement letters (law firms, consultancies): rate vs card by role, hours vs cap, matter budget remaining; the Hartwell invoice gets timekeeper lines (PDF re-rendered and re-extracted) |
| 6 | Existing routing retained; delegates; permissions enforce next-in-chain |
| 7 | Due date from terms; early-pay discount capture; payment-run hold flag; vendor-master review queue with a call-back task that releases the hold |
| 8 | AP interface batch with control totals; blanket-PO and standing-rule requests raised from insights as procurement tasks |

Seed additions (`scripts/datagen/`): rate cards, engagement letters, matter budgets, two split invoices, one cut-off invoice, one untaxed taxable invoice, one intercompany and one employee-reimbursement invoice, discount-terms vendors, close calendar. Seed invariants extended in `tests/test_seed_data.py`.

## 6. Roles and governance

- **Sign-in:** the site passcode stays as the outer gate; then choose a named person from the directory. Server session `{person_id, roles[]}`; "Switch user" in the header is logged as an audit event.
- **Permissions (server-enforced):** AP specialist (accept/override/reject, request receipt), Requester (confirm own receipt tasks), Approver (approve when next in chain or delegate), GL accountant (prepare reclass), Controller (approve reclass, close dashboard), Cash application lead (approve cash fixes), Procurement (PO-policy cases, blanket-PO requests), Vendor master (call-back, onboarding), Admin (policy edit, clock, reset). Anything else returns 403 with a plain message naming the role needed.
- **Role inboxes:** each role lands on "My work" with SLA and age.
- **Policy admin (`/policies`):** approval matrix, DoA limits, PO policy, capitalisation thresholds, risk thresholds, confidence bands. Each save is a new version with who, when and why; runs record the version they used.
- **Audit:** global log (`/audit`) filterable by actor, type, date and object. **SOX evidence pack** per invoice: printable HTML with the PDF image, extraction, run record with tool calls, decisions, approvals and export.

## 7. Architecture, agents and workflows views

- Rendered by data-driven SVG components (no new dependency): `ContainerDiagram`, `AgentTopology`, `SequenceDiagram`.
- **Container diagrams** for as-built, Bedrock and Foundry: numbered labelled flows, trust boundaries (Mastercard network, cloud tenant, model endpoint), data classification per flow.
- **Agent topology:** supervisor, specialists, tools, investigator, stores and human checkpoints, connected by arrows.
- **Agent catalogue** from `/api/agents`: purpose, trigger, inputs, tools with signatures, decisions and outputs, flags, guardrails, failure modes and fallback, human checkpoint, metrics (from runs), and a real recorded tool-call example.
- **SequenceDiagram:** lifelines with activation bars, solid request and dashed return arrows, alt/opt/loop frames, SLA timers, control notes; a play/step control highlights each message with its description and endpoint or function. Twelve workflows: intake and run; exception investigation; receipt with escalation; approval routing (DoA/SoD/delegate); AP posting to R12; payment-risk hold → call-back; month-end anomaly → reclass → GL_INTERFACE; cash misapplication → reapply; PO compliance → blanket PO; prepaid/capitalise/cut-off accrual; learning loop and retrain; live upload. Each has an operational panel: trigger, SLA, RACI, SOX control points, KPIs, exception paths, systems of record.
- Phone width: diagrams scroll horizontally inside their frame; operational panels stack.

## 8. Hardening

- Neon Postgres via `DATABASE_URL` for all mutable state (runs, decisions, cases, policies, sessions, audit).
- Operations page (`/operations`): runs per day, p50/p95 latency per agent, Claude tokens and cost, cache hit rate, failures, investigator calls.
- Cold start under 4 s: lazy-load journals, cash and AR on the first anomaly request; ship precomputed indices; Vercel cron warm ping.
- Tests: unit per tool; storyboard golden cases; permission matrix; model-metric regression (first-time-right must not drop more than 1 point); Playwright e2e of the storyboard; GitHub Actions on push.
- Walkthrough rewritten per module with talk track; `docs/RUNBOOK.md` updated; investigator outputs cached so replay mode covers everything.
- Storyboard keeps the brief's six scenes in about 12 minutes; new modules serve Q&A and deep-dive follow-ups.

## 9. Error handling

- Tool failure → ToolCall marked error, step status `warn`, run continues; if the tool is a control (sanctions, duplicate, bank change) the invoice is held with "Check could not complete: <tool>".
- Claude unavailable → extraction falls back to the intake record, the reason to the template, the investigator to a deterministic summary; the UI shows the source.
- Permission denied → 403 naming the role needed; audit event.
- Unbalanced GL batch → export refused with the control totals shown.
- Stale run (policy or correction changed since) → banner with a re-run action.

## 10. Schedule and cut order

| Day | Build | Exit |
|---|---|---|
| Wed 7–Thu 8 | Agent runtime, registry, runs, New intake, console; seed additions | Storyboard invoices run for real with recorded tool calls |
| Fri 9 | Train, back-test, calibrate, Model & data page; investigator | Metrics on screen; holds investigated |
| Sat 10–Sun 11 | Cases and close dashboard; sign-in, permissions, inboxes | Reclass prepared → approved → exported with SoD |
| Mon 12 | Process depth (section 5); Nazeer call 06:00 CT | Golden test per new rule |
| Tue 13 | Diagrams, sequence diagrams, catalogue; policy admin; audit and SOX pack; Neon; Operations | Every view on real data |
| Wed 14 | e2e, CI, walkthrough, cache warm, cold start, 3 dry runs, freeze | Two clean dry runs |

Cut order if behind: policy edit → view-only; Operations page; splits; use-tax. Nothing on the storyboard path is cut.

## 11. Out of scope

Real SSO or IdP integration; real R12, Coupa or Teams connections; real payment runs; multi-tenant; a mobile app beyond the requester view.
