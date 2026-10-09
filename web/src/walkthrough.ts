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
    body: 'Nearly three times the normal amount, bank details changed two days ago from a look-alike domain. Claude checked the bank log and vendor profile with read-only tools and says what to do next; every claim cites the call it came from. The vendor-master team acts on it.' },
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
    body: 'Upload any invoice PDF. Claude reads it live, uncached, and the same agent works it in front of you.' },
]
