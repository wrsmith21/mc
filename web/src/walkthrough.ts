export type TourStep = {
  id: string
  scene: string
  target: string
  title: string
  body: string
  talk?: string
  path?: string
  invoice?: string // storyboard key; resolved to /invoice/<intake id>
  tab?: 'decision' | 'console' | 'audit' // invoice steps open this tab; the recommendation unless set
  press?: boolean // Next presses the spotlighted button and waits for it to finish, so later steps have data
}

// The workshop storyboard (brief section 3), signed in as Alex Rivera (AP specialist) unless a step says otherwise.
export const TOUR: TourStep[] = [
  { id: 'who', scene: 'Set-up', path: '/', target: 'persona', title: 'Signed in as a real role',
    body: 'Alex Rivera, AP specialist. Every screen shows Alex’s own work, and the server checks every action against Alex’s role. Switching user is logged.',
    talk: '“This is CLEAR: coding, ledger, exceptions, approvals and reconciliation, worked by one agent with a person deciding. Synthetic data, built in a week, on the patterns we would build on your stack.”' },
  { id: 'inbox', scene: 'Set-up', path: '/', target: 'inbox', title: 'This morning’s mailbox, not yet worked',
    body: '102 invoices were worked by the agent as they arrived overnight. 40 more landed this morning and nobody has touched them, not even the agent.' },
  { id: 'mailbox', scene: 'Set-up', path: '/', target: 'run-mailbox', press: true, title: 'Run the agent on the mailbox',
    body: 'Run and continue works all 40. Each invoice runs every control in order and the counter climbs as each one finishes; a few seconds for the lot. If the mailbox is already worked, carry on.' },

  { id: 'tel-new', scene: 'Scene 1 · Routine invoice', invoice: 'telecoms', target: 'run-line', title: 'One invoice, end to end',
    body: 'Northline Communications, $42,310.55. The line says when and how the agent worked it, how long it took and how many tool calls it made.' },
  { id: 'tel-run', scene: 'Scene 1 · Routine invoice', invoice: 'telecoms', target: 'run-agent', title: 'Run it again, live',
    body: 'Re-running shows the agent working: each step and each tool call arrives as it happens. Turn on Presentation pace in the header to slow the display; the label shows the real run time.' },
  { id: 'tel-console', scene: 'Scene 1 · Routine invoice', invoice: 'telecoms', tab: 'console', target: 'console', title: 'Every call is recorded',
    body: 'Supplier match, OFAC screen, VAT, duplicates across 18 months, PO policy, coding from history, receipt rule, payment risk, approval routing. Click any call to see its inputs.' },
  { id: 'tel-rec', scene: 'Scene 1 · Routine invoice', invoice: 'telecoms', target: 'recommendation', title: 'Coded from history, with a calibrated confidence',
    body: 'Telecommunications, infrastructure cost centre. The confidence is calibrated: on the hold-out, recommendations at this level were right that often.',
    talk: '“Nobody keyed anything. Most non-PO invoices look like this, and this is where the hours go today.”' },
  { id: 'tel-model', scene: 'Scene 1 · Routine invoice', invoice: 'telecoms', target: 'model-line', title: 'Measured, not asserted',
    body: 'Raw score, calibrated confidence, model version and a second opinion from a trained challenger. The link goes to how it was measured.' },

  { id: 'dell-default', scene: 'Scene 2 · The Dell laptop', invoice: 'dell', target: 'default-override', title: 'The vendor default would have been wrong',
    body: 'Dell is set up against Repairs & Maintenance because of its service contracts. The lines say laptops, so the agent recommends Computer Hardware.',
    talk: '“Anyone keying this in a hurry takes the default. The agent doesn’t.”' },
  { id: 'dell-evidence', scene: 'Scene 2 · The Dell laptop', invoice: 'dell', target: 'evidence', title: 'Evidence an accountant can check',
    body: 'The closest past invoices, how they were coded and who approved them. 55 of Dell’s 60 invoices went to 1540; three keyed to the default were reclassified at close.' },
  { id: 'dell-cap', scene: 'Scene 2 · The Dell laptop', invoice: 'dell', target: 'treatment', title: 'Routed to Fixed Assets, not decided',
    body: '$1,845 a unit clears the $1,000 per-unit threshold for computer hardware. The agent routes it; Fixed Asset Accounting decides.' },
  { id: 'dell-receipt', scene: 'Scene 2 · The Dell laptop', invoice: 'dell', target: 'receipt', title: 'Receipt already evidenced',
    body: 'Kevin Brandt’s asset-register scan of the ten serial numbers is the evidence of receipt. Nobody is asked to confirm what the system already knows.' },
  { id: 'dell-po', scene: 'Scene 2 · The Dell laptop', invoice: 'dell', target: 'flags', title: 'It should have been a PO',
    body: 'IT hardware needs a purchase order. The invoice is still processed, and the breach is logged for procurement.',
    talk: 'Pause. Ask Nazeer: “Is that the kind of thing your team catches today, and how late?”' },

  { id: 'legal-price', scene: 'Scene 3 · Judgement calls', invoice: 'legal', target: 'price', title: 'Is the price right?',
    body: '118.5 hours by role against the engagement letter, and matter M-2207 at 82% of budget after this invoice.' },
  { id: 'legal-receipt', scene: 'Scene 3 · Judgement calls', invoice: 'legal', target: 'receipt', title: 'No PO, so who confirms the service?',
    body: 'The matter register names Julia Ortiz. She confirms on her phone (scan the code); if she doesn’t, she is reminded, then it escalates, then the firm is asked who ordered.' },
  { id: 'saas', scene: 'Scene 3 · Judgement calls', invoice: 'saas', target: 'treatment', title: 'P2P joined up with R2R',
    body: 'A 12-month subscription booked straight to expense would overstate October. Prepaid, with the amortisation journal drafted as a GL interface file.' },

  { id: 'bank-inv', scene: 'Scene 4 · Controls', invoice: 'bank_change', target: 'investigation', title: 'Held, and investigated',
    body: 'Nearly three times the normal amount, bank details changed two days ago from a look-alike domain. CLEAR checked the bank log and vendor profile with read-only tools and says what to do next; every claim cites the call it came from. The vendor-master team acts on it.' },
  { id: 'dup', scene: 'Scene 4 · Controls', invoice: 'duplicate', target: 'flags', title: 'The same invoice, sent again',
    body: 'Different number format, same amount, date and matter. Held before it reaches a payment run.' },
  { id: 'sod', scene: 'Scene 4 · Controls', invoice: 'sod', target: 'approval', title: 'Nobody approves their own spend',
    body: 'Diana Moreno requested the workshop and would be the default approver. The agent reroutes to her VP; only Grace Okafor can approve, and the server refuses anyone else.' },

  { id: 'close', scene: 'Scene 6 · One engine, three processes', path: '/close?status=All', target: 'laptop-journal', title: 'Nazeer’s laptop, in a manual journal',
    body: 'The same engine reads the September close and finds the laptop refresh in Repairs & Maintenance. It is a case with a drafted reclass: Ben Keller prepares it, Samuel Whitaker approves it, and it posts as a balanced GL_INTERFACE batch.' },
  { id: 'cash', scene: 'Scene 6 · One engine, three processes', path: '/close', target: 'cash-source', title: 'A day of cash application',
    body: '11,400 receipts. It finds the one applied to the wrong customer (transposed digits) and proposes matches for most unapplied cash.',
    talk: '“Vinay, that’s the 1–2% that doesn’t auto-apply today. Nazeer, that’s your horizontal anomaly layer.”' },

  { id: 'model', scene: 'Under the hood', path: '/model', target: 'model-kpis', title: 'What it learned from, and how it was tested',
    body: 'Trained on a year of coded lines, tested on three later months it never saw. Champion against challenger, calibration, where it is weakest. Measured on synthetic data; on yours, the same harness runs first.' },
  { id: 'arch', scene: 'Under the hood', path: '/architecture', target: 'arch-topology', title: 'The agents',
    body: 'A supervisor and six specialists in a fixed order, Claude for reading, explaining and investigating, and every call through a recorded tool. The catalogue below lists each agent’s tools from the running service.' },
  { id: 'arch-aws', scene: 'Under the hood', path: '/architecture', target: 'arch-aws', title: 'On your cloud',
    body: 'The same design on Amazon Bedrock or Azure AI Foundry, inside your network, with numbered data flows and trust boundaries.',
    talk: '“Runs on your approved model, on whichever cloud you already run.”' },
  { id: 'arch-wf', scene: 'Under the hood', path: '/architecture', target: 'arch-workflows', title: 'Each workflow, message by message',
    body: 'Who calls whom, with the endpoint behind each step, the alternative paths and the SLA timers. Press Play.' },
  { id: 'wild', scene: 'Try it', path: '/', target: 'wildcard', title: 'Bring your own invoice',
    body: 'Upload any invoice PDF. CLEAR reads it live, uncached, and the same agent works it in front of you.' },
]

const MAILBOX: TourStep = {
  id: 'mailbox', scene: 'Set-up', path: '/', target: 'run-mailbox', press: true, title: 'Work this morning’s mailbox',
  body: '40 invoices arrived this morning and nobody has touched them. Run and continue lets the agent work all of them; if the mailbox is already worked, carry on.',
}

// 1. Non-PO invoice: the Dell laptops, end to end, as Alex Rivera (AP specialist).
const NON_PO: TourStep[] = [
  MAILBOX,
  { id: 'np-head', scene: 'The invoice', invoice: 'dell', target: 'invoice-head', title: 'Ten laptops, no purchase order',
    body: 'Dell Technologies, $20,009.03, emailed to the AP inbox. With no PO there is nothing to match against: coding, receipt and approver all have to be worked out.' },
  { id: 'np-run', scene: 'The invoice', invoice: 'dell', target: 'run-line', title: 'Worked in seconds, every call recorded',
    body: 'When the agent ran, how long it took and how many tool calls it made. Re-run it to watch each check arrive live.' },
  { id: 'np-override', scene: 'Coding', invoice: 'dell', target: 'default-override', title: 'The vendor default would have been wrong',
    body: 'Dell is set up against 6420 Repairs & Maintenance because of its service contracts. The lines say laptops, so the agent recommends 1540 Computer Hardware.',
    talk: '“Anyone keying this in a hurry takes the default. The agent doesn’t.”' },
  { id: 'np-evidence', scene: 'Coding', invoice: 'dell', target: 'evidence', title: 'Evidence an accountant can check',
    body: 'The closest past invoices, how they were coded and who approved them. 55 of Dell’s 60 invoices went to 1540; three keyed to the default were reclassified at month-end.' },
  { id: 'np-cap', scene: 'Treatment', invoice: 'dell', target: 'treatment', title: 'Routed to Fixed Assets, not decided',
    body: '$1,845 a unit clears the $1,000 per-unit threshold for computer hardware. The agent routes it; Fixed Asset Accounting makes the capitalisation call.' },
  { id: 'np-po', scene: 'Controls', invoice: 'dell', target: 'flags', title: 'It should have been a PO',
    body: 'IT hardware needs a purchase order. The invoice is still processed, and the breach is logged for procurement so non-PO volume shrinks at source.',
    talk: 'Pause. Ask: “Is that the kind of thing your team catches today, and how late?”' },
  { id: 'np-receipt', scene: 'Receipt', invoice: 'dell', target: 'receipt', title: 'Receipt already evidenced',
    body: 'The asset-register scan of the ten serial numbers is the evidence of receipt. Nobody is asked to confirm what the system already knows.' },
  { id: 'np-approval', scene: 'Approval', invoice: 'dell', target: 'approval', title: 'Routed by your approval matrix',
    body: 'IT Procurement and Fixed Asset Accounting first, because category rules come before the amount tier, then the director, whose limit is checked.' },
  { id: 'np-audit', scene: 'Governance', invoice: 'dell', tab: 'audit', target: 'audit', title: 'Every step is evidence',
    body: 'What the agent read, recommended and why, who confirmed receipt and who approved, with timestamps. SOX evidence as a by-product.',
    talk: '“The agent recommends; your people decide.”' },
]

// 2. Cash application: a day of settlement receipts and the one applied to the wrong customer.
const CASH: TourStep[] = [
  { id: 'ca-day', scene: 'The day', path: '/close?source=cash', target: 'cash-source', title: 'A day of settlement cash',
    body: '11,400 receipts from 14 October. 98.4% were auto-applied by the existing rules; the agent checks those too, and works the exceptions the rules left behind.' },
  { id: 'ca-cases', scene: 'The day', path: '/close?source=cash', target: 'case-table', title: 'Every finding is a case',
    body: 'Cash applied to the wrong customer, a receipt applied to an invoice already paid, and proposed matches for most unapplied receipts. Each has an owner, an SLA and a drafted fix.',
    talk: '“This is the 1–2% that doesn’t auto-apply today.”' },
  { id: 'ca-what', scene: 'The misapplied receipt', path: '/close?type=MISAPPLIED', target: 'case-summary', title: 'Right money, wrong customer',
    body: 'Lakeshore Federal Credit Union (30418) paid $48,220 and quoted their invoice 9100231877. A clerk applied it to 30481, Lakeside Community Bank: transposed digits.' },
  { id: 'ca-fix', scene: 'The misapplied receipt', path: '/close?type=MISAPPLIED', target: 'case-fix', title: 'The fix, drafted',
    body: 'Unapply from 30481, re-apply to 30418 against the invoice the remittance names. Nothing moves until a person approves it.' },
  { id: 'ca-inv', scene: 'The misapplied receipt', path: '/close?type=MISAPPLIED', target: 'case-investigation', title: 'Investigated, read-only',
    body: 'CLEAR checks the remittance, the payer’s aliases and both customers’ open items, and cites each call. It reads; it cannot act.' },
  { id: 'ca-decide', scene: 'The misapplied receipt', path: '/close?type=MISAPPLIED', target: 'case-decide', title: 'Maker and checker',
    body: 'Hana Zhang prepares the re-application, Priya Nair approves it, and approved fixes export as a re-application file. The preparer can’t approve their own work.' },
  { id: 'ca-same', scene: 'One engine', path: '/close?source=cash', target: 'close-sources', title: 'The same engine as AP and the close',
    body: 'The checks that code invoices also read the close journals and the AP subledger. Built once, used three times.' },
]

// 3. Procure to pay: keeping spend on purchase orders.
const P2P: TourStep[] = [
  MAILBOX,
  { id: 'pp-head', scene: 'A PO that already exists', invoice: 'open_po', target: 'invoice-head', title: 'An invoice with no PO number',
    body: 'Halden Consulting, $48,000, for phase 2 of a controls design review. The supplier didn’t quote a PO, so it landed in the non-PO queue.' },
  { id: 'pp-match', scene: 'A PO that already exists', invoice: 'open_po', target: 'flags', title: 'Matched to the open PO',
    body: 'An approved PO for exactly this work is open. The agent sends the invoice to three-way match instead of coding and approving it a second time.',
    talk: '“The cheapest non-PO invoice is the one that turns out to have a PO.”' },
  { id: 'pp-breach', scene: 'Spend that should have been a PO', invoice: 'po_breach_marketing', target: 'flags', title: 'Over the PO threshold, without a PO',
    body: 'A $68,150 agency invoice. Marketing over $50k needs a PO: the invoice is still processed, and the breach goes on the procurement report.' },
  { id: 'pp-cats', scene: 'Shrinking the problem', path: '/insights', target: 'category-breach', title: 'Where non-PO spend should have been on a PO',
    body: '18 months of AP spend by category, with the part in categories your policy says need a purchase order.' },
  { id: 'pp-blanket', scene: 'Shrinking the problem', path: '/insights', target: 'blanket-po', title: 'Turn repeat spend into a blanket PO',
    body: 'Suppliers billing almost every month without a PO. One click sends procurement a request for a blanket PO or a standing approval rule.',
    talk: '“Fewer non-PO invoices, not just faster ones.”' },
  { id: 'pp-ledger', scene: 'Cleaning up what already posted', path: '/close?source=ap_ledger', target: 'ap-source', title: 'Miscodes already in the AP subledger',
    body: 'Past invoices coded differently from every similar line, never reclassified. Each is a case with a drafted reclass for the GL team.' },
]

export type Tour = { id: string; title: string; summary: string; steps: TourStep[] }

export const TOURS: Tour[] = [
  { id: 'non-po', title: 'Non-PO invoice', summary: 'Dell laptops, from the mailbox to an approved, audited posting.', steps: NON_PO },
  { id: 'cash', title: 'Cash application', summary: 'A day of settlement receipts and the one applied to the wrong customer.', steps: CASH },
  { id: 'p2p', title: 'Procure to pay', summary: 'Keeping spend on purchase orders, and cleaning up what already posted.', steps: P2P },
  { id: 'storyboard', title: 'Full workshop storyboard', summary: 'Every scene in order, including under the hood.', steps: TOUR },
]
