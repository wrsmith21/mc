// Content for the Architecture & workflows page. Names, flag codes and thresholds mirror backend/ and data/seed/policies.json.

export type Kind = 'rules' | 'history' | 'claude' | 'external'
export const KIND_LABEL: Record<Kind, string> = {
  rules: 'Policy rules', history: 'History scoring', claude: 'Claude', external: 'External check',
}

export type Tile = { name: string; role: string; path?: string; replaces?: string; ai?: boolean }
export type Layer = { layer: string; tiles: Tile[] }
export type Platform = { id: string; title: string; summary: string; layers: Layer[]; notes: string[] }

export const REPO: Platform = {
  id: 'repo',
  title: 'How this demo is built',
  summary:
    'A single-page app and one Python function on Vercel. All reference data is synthetic JSON loaded into memory at start-up; every human action is written to an append-only event log.',
  layers: [
    { layer: 'People', tiles: [
      { name: 'Reviewer workspace', role: 'Queue, invoice review, anomaly layer, value and this page. React 19 + Vite.', path: 'web/src/screens/' },
      { name: 'Requester phone view', role: 'Receipt confirmation opened from a QR code, no app install.', path: 'web/src/screens/Requester.tsx' },
      { name: 'Guided walkthrough', role: 'Spotlight tour of every scene, with talk-track notes.', path: 'web/src/walkthrough.ts' },
    ] },
    { layer: 'Edge', tiles: [
      { name: 'Vercel CDN', role: 'Serves the built app, rewrites /api/* to the Python function, marks every response noindex.', path: 'vercel.json' },
      { name: 'Passcode gate', role: 'Middleware checks an HttpOnly cookie or x-demo-token on every API call except health and login.', path: 'backend/app.py' },
    ] },
    { layer: 'Application', tiles: [
      { name: 'FastAPI', role: 'REST endpoints plus a server-sent event stream that plays the agent run step by step.', path: 'backend/app.py' },
      { name: 'Demo service', role: 'Queue, decisions, approvals, receipt tasks, audit trail, KPIs, exports, live uploads.', path: 'backend/service.py' },
    ] },
    { layer: 'Agent', tiles: [
      { name: 'Invoice agent', role: 'Ten traced steps per invoice, then a status and a reason.', path: 'backend/engine/pipeline.py', ai: true },
      { name: 'Checks', role: 'Supplier match, sanctions, invoice validity, duplicates, payment risk.', path: 'backend/engine/checks.py' },
      { name: 'Policy', role: 'PO policy, open-PO match, requester, receipt rule, approval routing.', path: 'backend/engine/policy.py' },
      { name: 'Recommender', role: 'Scores GL account and cost centre from similar past lines; capitalise or prepay.', path: 'backend/engine/recommend.py' },
      { name: 'Anomaly layer', role: 'The same scoring pointed at journals, the AP subledger and cash application.', path: 'backend/engine/anomaly.py' },
    ] },
    { layer: 'Model', tiles: [
      { name: 'Claude reads', role: 'Reads the invoice PDF into a fixed JSON schema; fields are cross-checked against intake.', path: 'backend/llm.py', ai: true },
      { name: 'Claude explains', role: 'Writes the reviewer-facing reason from the engine’s findings, with a deterministic template as fallback.', path: 'backend/llm.py', ai: true },
      { name: 'Response cache', role: 'Keyed by content hash, so replay mode runs the whole demo with no network.', path: 'data/cache/' },
    ] },
    { layer: 'Data', tiles: [
      { name: 'Reference data', role: '142 queued invoices, 12,340 past invoices (27,157 lines), 405 vendors, 167 people, 45 cost centres.', path: 'data/seed/' },
      { name: 'Close and cash data', role: '4,100 September journal lines, 11,400 cash receipts, 29,608 open AR items.', path: 'data/seed/' },
      { name: 'Event log and state', role: 'SQLite locally, /tmp on Vercel, Postgres when DATABASE_URL is set.', path: 'backend/state.py' },
    ] },
    { layer: 'Outside world', tiles: [
      { name: 'EU VIES', role: 'VAT-number registration check, queried live when the printed number differs from the vendor master.', path: 'backend/integrations/external.py' },
      { name: 'OFAC screen and ECB rates', role: 'Sanctions name screen; daily FX reference rates via Frankfurter, cached.', path: 'backend/integrations/external.py' },
      { name: 'Oracle R12 interface files', role: 'AP invoice, GL amortisation and reclass CSVs in open-interface format.', path: 'backend/engine/exports.py' },
    ] },
  ],
  notes: [
    'Claude never picks the account. The recommender scores it from history, so every recommendation traces back to past invoices.',
    'If the model is unreachable the run still completes: extraction falls back to the intake record, the reason to a template.',
    'The agent can recommend, hold and route. It cannot approve or release a payment.',
  ],
}

export const AWS: Platform = {
  id: 'aws',
  title: 'Proposed on Amazon Bedrock',
  summary:
    'The engine code moves unchanged into a container. Each group of steps becomes a Bedrock collaborator agent whose tools are the existing Python checks, so the rules stay deterministic and auditable.',
  layers: [
    { layer: 'People', tiles: [
      { name: 'CloudFront + S3', role: 'Hosts the reviewer workspace.', replaces: 'Vercel CDN' },
      { name: 'Amazon Cognito', role: 'Federated to the corporate identity provider over SAML; roles decide what each persona sees.', replaces: 'Passcode gate' },
      { name: 'Amazon SES', role: 'Receives the AP mailbox and sends receipt-confirmation links to requesters.', replaces: 'QR phone view' },
    ] },
    { layer: 'Edge', tiles: [
      { name: 'AWS WAF + API Gateway', role: 'Rate limits, request validation, private VPC link to the service.' },
    ] },
    { layer: 'Application', tiles: [
      { name: 'ECS on Fargate', role: 'Runs the FastAPI service unchanged, including the live run stream.', replaces: 'Vercel Python function' },
      { name: 'AWS Step Functions', role: 'Waits on people: receipt confirmation and each approval resume the run through task tokens.' },
    ] },
    { layer: 'Agent', tiles: [
      { name: 'Bedrock Agents supervisor', role: 'Plans each invoice’s run, calls collaborators, applies the status precedence.', replaces: 'Agent.process', ai: true },
      { name: 'Bedrock collaborator agents', role: 'Intake, supplier and validity, coding and treatment, payment risk, approval and receipt, anomaly sweep.', ai: true },
      { name: 'Action groups on Lambda', role: 'Checks, Policy and Recommender exposed as typed tools.', replaces: 'Direct Python calls' },
      { name: 'Bedrock AgentCore Runtime', role: 'Alternative first step: host the current Python orchestrator as it is, with managed identity and session isolation.' },
    ] },
    { layer: 'Model', tiles: [
      { name: 'Claude on Amazon Bedrock', role: 'Same extraction schema and reason prompt, served in-region.', replaces: 'Anthropic API', ai: true },
      { name: 'Bedrock Guardrails', role: 'PII redaction, denied topics and a contextual grounding check on every reason.' },
      { name: 'Bedrock Knowledge Bases', role: 'Delegation of authority, PO policy and the AP manual as sources the reason can cite.' },
      { name: 'Amazon Textract', role: 'Fallback OCR for poor-quality scans before the model reads them.' },
    ] },
    { layer: 'Data', tiles: [
      { name: 'S3 with Object Lock', role: 'Invoice PDFs and model invocation logs, retained for audit.', replaces: 'data/pdfs' },
      { name: 'Aurora PostgreSQL', role: 'Event log, decisions, receipt tasks, learned corrections.', replaces: 'SQLite or Neon' },
      { name: 'OpenSearch Serverless', role: 'History similarity index at full ledger volume.', replaces: 'In-memory history' },
    ] },
    { layer: 'Outside world', tiles: [
      { name: 'EventBridge Scheduler', role: 'Month-end journal sweep and the daily cash-application run.' },
      { name: 'PrivateLink or Direct Connect', role: 'Oracle EBS open-interface upload and vendor master reads.', replaces: 'CSV download' },
      { name: 'Secrets Manager, KMS, CloudWatch, CloudTrail', role: 'Keys, encryption, tracing and an immutable record of who did what.' },
    ] },
  ],
  notes: [
    'Lowest-risk path: start on AgentCore Runtime with the current orchestrator, then split into collaborator agents once the tools are stable.',
    'Step Functions holds the human waits, so an invoice can sit with a requester for days without a running process.',
  ],
}

export const AZURE: Platform = {
  id: 'azure',
  title: 'Proposed on Azure AI Foundry',
  summary:
    'The same agent split on Microsoft’s stack. It fits best where identity, mail and approvals already run on Microsoft 365.',
  layers: [
    { layer: 'People', tiles: [
      { name: 'Azure Static Web Apps', role: 'Hosts the reviewer workspace.', replaces: 'Vercel CDN' },
      { name: 'Microsoft Entra ID', role: 'Single sign-on; app roles map to AP specialist, approver and controller.', replaces: 'Passcode gate' },
      { name: 'Teams and Outlook actionable messages', role: 'Requesters confirm receipt and approvers approve where they already work.', replaces: 'QR phone view' },
    ] },
    { layer: 'Edge', tiles: [
      { name: 'Front Door + WAF, API Management', role: 'Global entry, request policies, private link to the service.' },
    ] },
    { layer: 'Application', tiles: [
      { name: 'Azure Container Apps', role: 'Runs the FastAPI service unchanged, including the live run stream.', replaces: 'Vercel Python function' },
      { name: 'Durable Functions', role: 'Long-running waits for receipt and each approval.' },
    ] },
    { layer: 'Agent', tiles: [
      { name: 'Foundry Agent Service orchestrator', role: 'Plans each invoice’s run and calls the connected agents.', replaces: 'Agent.process', ai: true },
      { name: 'Connected agents', role: 'Intake, supplier and validity, coding and treatment, payment risk, approval and receipt, anomaly sweep.', ai: true },
      { name: 'OpenAPI tools on Azure Functions', role: 'Checks, Policy and Recommender exposed as typed tools.', replaces: 'Direct Python calls' },
    ] },
    { layer: 'Model', tiles: [
      { name: 'Claude in Azure AI Foundry', role: 'Same extraction schema and reason prompt; Azure OpenAI available as a second model.', replaces: 'Anthropic API', ai: true },
      { name: 'Azure AI Content Safety', role: 'Prompt shields against instructions hidden in supplier documents; groundedness detection.' },
      { name: 'Azure AI Search', role: 'Policy grounding for reasons, and the history similarity index.' },
      { name: 'Document Intelligence', role: 'Prebuilt invoice model as a fallback for poor-quality scans.' },
    ] },
    { layer: 'Data', tiles: [
      { name: 'Immutable Blob Storage', role: 'Invoice PDFs and run traces under a retention policy.', replaces: 'data/pdfs' },
      { name: 'Azure Database for PostgreSQL', role: 'Event log, decisions, receipt tasks, learned corrections.', replaces: 'SQLite or Neon' },
    ] },
    { layer: 'Outside world', tiles: [
      { name: 'Logic Apps', role: 'Watches the AP mailbox and schedules the month-end sweep and daily cash run.' },
      { name: 'ExpressRoute or on-premises data gateway', role: 'Oracle EBS open-interface upload and vendor master reads.', replaces: 'CSV download' },
      { name: 'Key Vault, Managed Identity, Azure Monitor, Purview', role: 'Secrets, keyless access, tracing, data lineage.' },
    ] },
  ],
  notes: [
    'Teams approvals replace the QR phone view once a Mastercard tenant is available.',
    'Foundry tracing records every tool call per run, giving audit the same evidence the demo’s trail shows.',
  ],
}

export const MAPPING: { concern: string; repo: string; aws: string; azure: string }[] = [
  { concern: 'Front end', repo: 'Vercel CDN', aws: 'CloudFront + S3', azure: 'Static Web Apps' },
  { concern: 'Sign-in', repo: 'Shared passcode', aws: 'Cognito + corporate IdP', azure: 'Entra ID' },
  { concern: 'API service', repo: 'Vercel Python function', aws: 'ECS on Fargate', azure: 'Container Apps' },
  { concern: 'Agent orchestration', repo: 'Agent.process in Python', aws: 'Bedrock Agents supervisor', azure: 'Foundry Agent Service' },
  { concern: 'Agent tools', repo: 'Checks, Policy, Recommender', aws: 'Action groups on Lambda', azure: 'OpenAPI tools on Functions' },
  { concern: 'Model', repo: 'Claude via Anthropic API', aws: 'Claude on Bedrock', azure: 'Claude in Foundry' },
  { concern: 'Safety', repo: 'Schema output, template fallback', aws: 'Bedrock Guardrails', azure: 'AI Content Safety' },
  { concern: 'Policy grounding', repo: 'policies.json', aws: 'Bedrock Knowledge Bases', azure: 'AI Search' },
  { concern: 'Scan fallback', repo: 'Intake record', aws: 'Textract', azure: 'Document Intelligence' },
  { concern: 'Documents', repo: 'data/pdfs', aws: 'S3 with Object Lock', azure: 'Immutable Blob Storage' },
  { concern: 'State and audit log', repo: 'SQLite or Neon Postgres', aws: 'Aurora PostgreSQL', azure: 'Azure Database for PostgreSQL' },
  { concern: 'Waiting on people', repo: 'Receipt task in state', aws: 'Step Functions task tokens', azure: 'Durable Functions' },
  { concern: 'Schedules', repo: 'Computed on request', aws: 'EventBridge Scheduler', azure: 'Logic Apps' },
  { concern: 'Invoice intake', repo: 'Seeded queue and live upload', aws: 'SES inbound to S3', azure: 'Logic Apps mailbox trigger' },
  { concern: 'ERP', repo: 'Oracle R12 CSV download', aws: 'PrivateLink to Oracle EBS', azure: 'ExpressRoute to Oracle EBS' },
  { concern: 'Secrets and tracing', repo: 'Vercel env, function logs', aws: 'Secrets Manager, CloudWatch, CloudTrail', azure: 'Key Vault, Azure Monitor' },
]

// ---------- agent flow ----------

export type Flag = { code: string; severity: 'hold' | 'warn' | 'info' }
export type AgentStep = { key: string; question: string; does: string; kinds: Kind[]; flags: Flag[]; path: string }

export const AS_BUILT: AgentStep[] = [
  { key: 'intake', question: 'Received', kinds: ['rules'], flags: [], path: 'pipeline.py',
    does: 'Logs the channel, sender and received time, and converts the amount to USD at the month’s rate.' },
  { key: 'read', question: 'Read the invoice', kinds: ['claude'], flags: [], path: 'llm.extract_pdf',
    does: 'Claude reads the PDF into a fixed schema. Supplier, number, date, currency, total and line count are compared with the intake record.' },
  { key: 'supplier', question: 'Should this be here?', kinds: ['rules', 'external'], flags: [{ code: 'UNKNOWN_SUPPLIER', severity: 'hold' }, { code: 'SANCTIONS', severity: 'hold' }], path: 'checks.resolve_vendor, checks.sanctions',
    does: 'Matches the supplier to the vendor master by name, corroborated by tax ID, and screens the name against OFAC.' },
  { key: 'validity', question: 'Is the invoice valid?', kinds: ['rules', 'external', 'history'], flags: [{ code: 'VAT_INVALID', severity: 'hold' }, { code: 'DUPLICATE', severity: 'hold' }], path: 'checks.validity, checks.duplicates',
    does: 'Checks mandatory fields, billed-to entity, currency and the VAT number (EU VIES when it differs from the master), then looks for the same invoice within 45 days under any number format.' },
  { key: 'po', question: 'Should it have been a PO?', kinds: ['rules'], flags: [{ code: 'OPEN_PO_MATCH', severity: 'hold' }, { code: 'PO_POLICY', severity: 'warn' }], path: 'policy.open_po_match, policy.po_policy',
    does: 'Sends it to three-way match if an open PO fits. Otherwise applies PO policy, such as IT hardware at any amount or consulting over $25k, and logs any breach for procurement.' },
  { key: 'coding', question: 'What is it, where does it go?', kinds: ['history'], flags: [{ code: 'DEFAULT_OVERRIDE', severity: 'info' }], path: 'recommend.recommend_line',
    does: 'Scores GL account and cost centre from similar past lines, weighting the same supplier highest, and flags when the vendor default would have been wrong.' },
  { key: 'treatment', question: 'Capitalise or prepay?', kinds: ['rules', 'history'], flags: [{ code: 'CAPITALISE', severity: 'info' }, { code: 'PREPAID', severity: 'info' }], path: 'recommend.recommend_line',
    does: 'Routes per-unit costs over the asset-class threshold to Fixed Assets, and books multi-month service periods to prepaid with an amortisation schedule.' },
  { key: 'receipt', question: 'Who asked, did we get it?', kinds: ['rules', 'history'], flags: [], path: 'policy.identify_requester, policy.receipt_requirement',
    does: 'Finds the requester from the legal matter register, a name on the invoice or supplier history. It asks them to confirm receipt unless a standing rule covers it: recurring service within 10% of the 6-month average.' },
  { key: 'risk', question: 'Is it safe to pay?', kinds: ['rules', 'history'], flags: [{ code: 'PAYMENT_RISK', severity: 'hold' }], path: 'checks.payment_risk',
    does: 'Looks for an amount 2.5× the supplier’s normal, bank details changed within 30 days without a call-back, a remit-to mismatch, a look-alike sender domain and shortened terms.' },
  { key: 'approval', question: 'Who can approve it?', kinds: ['rules'], flags: [{ code: 'SOD_REROUTE', severity: 'warn' }], path: 'policy.route',
    does: 'Applies category rules first, then the amount tier: cost-centre owner under $10k, director to $100k, VP above. Skips anyone below their limit, the requester and anyone out of office.' },
]

export const WRAP_UP = {
  question: 'Decide and explain',
  does: 'Sets the status by precedence, then Claude writes the reason from the findings, with a template as fallback.',
  path: 'pipeline.decide, llm.explain',
}

export const OUTCOMES: { status: string; label: string; when: string }[] = [
  { status: 'MATCH_TO_PO', label: 'Match to PO', when: 'An open PO matches' },
  { status: 'HELD', label: 'Held', when: 'Any hold: unknown supplier, sanctions, VAT, duplicate, payment risk' },
  { status: 'AWAITING_CONFIRMATION', label: 'Awaiting confirmation', when: 'Receipt needed and not yet confirmed' },
  { status: 'NEEDS_CODING', label: 'Needs coding', when: 'Confidence below 60%' },
  { status: 'FAST_TRACK', label: 'Fast-track', when: 'Confidence 90% or more, no warnings, nothing to capitalise or prepay' },
  { status: 'RECOMMENDED', label: 'Recommended', when: 'Everything else: a person reviews the recommendation' },
]

export type Specialist = { name: string; job: string; tools: string[]; raises: string[]; guardrail: string; human?: string; scheduled?: boolean }

export const SUPERVISOR = {
  name: 'Supervisor',
  job: 'Plans each invoice’s run, calls the specialists, merges their flags, applies the status precedence and asks the model for the reason.',
  guardrail: 'Can recommend, hold and route. Cannot approve, change vendor master data or release payment.',
}

export const SPECIALISTS: Specialist[] = [
  { name: 'Intake and extraction', job: 'Turns an email or upload into a structured invoice.',
    tools: ['extract_pdf', 'field agreement', 'fx_rate'], raises: [],
    guardrail: 'Schema-constrained output; any field disagreement goes to a person.' },
  { name: 'Supplier and validity', job: 'Decides whether the invoice belongs in AP at all.',
    tools: ['resolve_vendor', 'sanctions', 'vies_check', 'duplicates', 'open_po_match', 'po_policy'],
    raises: ['UNKNOWN_SUPPLIER', 'SANCTIONS', 'VAT_INVALID', 'DUPLICATE', 'OPEN_PO_MATCH', 'PO_POLICY'],
    guardrail: 'Holds stand for the run; only a person releases them.' },
  { name: 'Coding and treatment', job: 'Recommends account, cost centre and accounting treatment.',
    tools: ['recommend_line', 'recommend_cc', 'vendor_default_contrast', 'learned corrections'],
    raises: ['DEFAULT_OVERRIDE', 'CAPITALISE', 'PREPAID'],
    guardrail: 'Every recommendation carries its evidence lines and confidence.', human: 'AP specialist accepts or overrides; overrides become history.' },
  { name: 'Payment risk', job: 'Looks for fraud and error patterns before money moves.',
    tools: ['payment_risk', 'comparable_median', 'aba_valid', 'iban_valid'], raises: ['PAYMENT_RISK'],
    guardrail: 'High-severity signals always hold and are never cleared automatically.', human: 'Vendor master team verifies by call-back.' },
  { name: 'Approval and receipt', job: 'Finds who asked for it, who confirms it and who can approve it.',
    tools: ['identify_requester', 'receipt_requirement', 'route'], raises: ['SOD_REROUTE'],
    guardrail: 'The approval matrix is data, not prompt; the agent cannot invent an approver.', human: 'Requester confirms receipt; approvers sign in order.' },
  { name: 'Anomaly sweep', job: 'Runs the same coding engine over journals, the AP subledger and cash application.',
    tools: ['scan_journals', 'scan_ap_ledger', 'scan_cash', 'gl_reclass'], raises: [],
    guardrail: 'Proposes reclasses and matches; posts nothing.', human: 'Controller reviews and uploads the reclass file.', scheduled: true },
]

// ---------- operational workflows ----------

export type Actor = 'AP specialist' | 'Agent' | 'Requester' | 'Approver' | 'Controller' | 'Procurement' | 'Oracle EBS'
export type WStep = { actor: Actor; text: string; api?: string }
export type Workflow = { id: string; name: string; purpose: string; trigger: string; outcome: string; steps: WStep[] }

export const WORKFLOWS: Workflow[] = [
  { id: 'intake', name: 'Intake and agent run', purpose: 'Every non-PO invoice is read and worked before anyone opens it.',
    trigger: 'An invoice arrives in the AP mailbox or the overnight batch', outcome: 'A status, a recommendation and a reason for each invoice',
    steps: [
      { actor: 'Agent', text: 'Reads the PDF and cross-checks the fields against the intake record', api: 'llm.extract_pdf' },
      { actor: 'Agent', text: 'Runs supplier, validity, PO, coding, treatment, receipt, risk and approval steps', api: 'GET /api/invoices/{id}/run' },
      { actor: 'Agent', text: 'Sets the status by precedence and writes the reason', api: 'llm.explain' },
      { actor: 'AP specialist', text: 'Works the queue: fast-tracked items ready, holds explained', api: 'GET /api/queue' },
    ] },
  { id: 'review', name: 'Review and decision', purpose: 'A person stays in charge of every coding decision.',
    trigger: 'An invoice is Recommended, Needs coding or Fast-track', outcome: 'Submitted for approval, or rejected with a reason',
    steps: [
      { actor: 'AP specialist', text: 'Checks the recommendation, evidence lines and flags', api: 'GET /api/invoices/{id}' },
      { actor: 'AP specialist', text: 'Accepts, overrides with a reason, or rejects with a reason', api: 'POST /api/invoices/{id}/decision' },
      { actor: 'Agent', text: 'On an override, stores the correction so the next similar line picks it up' },
      { actor: 'Agent', text: 'Builds the approval chain and records the submission in the audit trail', api: 'GET /api/invoices/{id}/audit' },
    ] },
  { id: 'receipt', name: 'Receipt confirmation', purpose: 'No PO means no goods receipt, so the requester’s confirmation is the evidence.',
    trigger: 'Receipt is required and no standing rule applies', outcome: 'Receipt confirmed and the invoice becomes approvable',
    steps: [
      { actor: 'Agent', text: 'Identifies the requester from the legal matter, a name on the invoice or history' },
      { actor: 'Agent', text: 'Creates a receipt task with the invoice and the evidence for the match', api: 'POST /api/invoices/{id}/receipt/request' },
      { actor: 'Requester', text: 'Opens the task on a phone and confirms, with an optional note', api: 'POST /api/invoices/{id}/receipt/confirm' },
      { actor: 'Agent', text: 'Re-evaluates: Awaiting confirmation moves to the post-receipt status' },
    ] },
  { id: 'approval', name: 'Approval routing', purpose: 'The approval matrix applied the same way every time.',
    trigger: 'An invoice is submitted for approval', outcome: 'Approved and written to the AP interface batch',
    steps: [
      { actor: 'Agent', text: 'Applies category rules, such as Legal Operations first for legal fees, then the amount tier' },
      { actor: 'Agent', text: 'Skips anyone below their limit, the requester and anyone out of office' },
      { actor: 'Approver', text: 'Each approver signs in order; out-of-turn approvals are refused', api: 'POST /api/invoices/{id}/approve' },
      { actor: 'Agent', text: 'On the final approval, adds the invoice to the AP open-interface batch' },
      { actor: 'Oracle EBS', text: 'Imports AP_INVOICES_INTERFACE and AP_INVOICE_LINES_INTERFACE', api: 'GET /api/exports/ap-interface/{part}' },
    ] },
  { id: 'controls', name: 'Holds and controls', purpose: 'Stop the bad invoice before the payment run, and say why.',
    trigger: 'Any hold raised during the run', outcome: 'Held with a named next action; nothing reaches approval',
    steps: [
      { actor: 'Agent', text: 'Raises the hold: duplicate, VAT invalid, sanctions, unknown supplier or payment risk' },
      { actor: 'Agent', text: 'Blocks submission: a held invoice cannot be accepted or overridden', api: 'POST /api/invoices/{id}/decision' },
      { actor: 'AP specialist', text: 'Follows the next action: vendor onboarding, call-back or three-way match' },
      { actor: 'AP specialist', text: 'Rejects with a reason once the outcome is known' },
    ] },
  { id: 'anomaly', name: 'Month-end anomaly sweep', purpose: 'Catch miscoding wherever it was keyed, not only in AP.',
    trigger: 'Month-end close, or the daily cash-application run', outcome: 'A reclass file and proposed cash matches',
    steps: [
      { actor: 'Agent', text: 'Scans manual and spreadsheet journals against how similar lines are usually coded', api: 'GET /api/anomalies' },
      { actor: 'Agent', text: 'Scans the AP subledger for lines coded away from their usual account' },
      { actor: 'Agent', text: 'Matches unapplied cash to open AR, including transposed customer references' },
      { actor: 'Controller', text: 'Reviews the findings and downloads the GL reclass file', api: 'GET /api/exports/reclass' },
      { actor: 'Oracle EBS', text: 'Imports the reclass through GL_INTERFACE' },
    ] },
  { id: 'value', name: 'PO compliance and value', purpose: 'Shrink non-PO volume at source, not just process it faster.',
    trigger: 'A PO-policy breach is logged as each invoice is processed', outcome: 'Procurement report and blanket-PO candidates',
    steps: [
      { actor: 'Agent', text: 'Logs each invoice that should have had a PO, with the rule it broke' },
      { actor: 'Agent', text: 'Aggregates 18 months of spend with and without a PO, by category and supplier', api: 'GET /api/insights/procurement' },
      { actor: 'Procurement', text: 'Downloads the PO-policy report and chooses blanket-PO candidates', api: 'GET /api/exports/procurement' },
    ] },
  { id: 'treatment', name: 'Prepaid and capitalisation', purpose: 'Join P2P to R2R so the period’s numbers are right.',
    trigger: 'A multi-month service period, or a per-unit cost over the asset threshold', outcome: 'An amortisation journal, or a Fixed Assets referral',
    steps: [
      { actor: 'Agent', text: 'Books multi-month services to prepaid and drafts the monthly amortisation', api: 'GET /api/exports/amortisation/{id}' },
      { actor: 'Agent', text: 'Routes hardware over the per-unit threshold to Fixed Asset Accounting' },
      { actor: 'Controller', text: 'Confirms the treatment and posts the amortisation journal' },
      { actor: 'Oracle EBS', text: 'Imports the journal through GL_INTERFACE' },
    ] },
  { id: 'wildcard', name: 'Live upload', purpose: 'Prove it on an invoice nobody prepared.',
    trigger: 'Someone in the room uploads any invoice PDF', outcome: 'The new invoice worked end to end, live',
    steps: [
      { actor: 'AP specialist', text: 'Uploads a PDF under 8 MB', api: 'POST /api/wildcard' },
      { actor: 'Agent', text: 'Claude reads it live, bypassing the cache', api: 'llm.extract_pdf' },
      { actor: 'Agent', text: 'Runs the same ten steps and streams them to the screen', api: 'GET /api/invoices/{id}/run' },
      { actor: 'AP specialist', text: 'Reviews and decides as for any other invoice' },
    ] },
]

export const ACTORS: Actor[] = ['AP specialist', 'Agent', 'Requester', 'Approver', 'Controller', 'Procurement', 'Oracle EBS']
