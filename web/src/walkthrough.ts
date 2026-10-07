export type TourStep = {
  id: string
  scene: string
  target: string
  title: string
  body: string
  talk?: string
  path?: string
  invoice?: string // storyboard key; resolved to /invoice/<intake id>
}

export const TOUR: TourStep[] = [
  { id: 'shell', scene: 'Set-up', path: '/', target: 'topbar', title: 'The AP team’s non-PO workspace',
    body: 'One place for every invoice that arrived without a purchase order. Switch who you are acting as to see each role: AP specialist, requester, approver, controller.',
    talk: '“This is synthetic data, built in a week, not a production system.”' },
  { id: 'kpis', scene: 'Set-up', path: '/', target: 'kpis', title: 'Today, before anyone has touched it',
    body: '142 non-PO invoices read overnight. Most are routine and fast-tracked within policy; the rest need a person, and each says why.' },
  { id: 'queue', scene: 'Set-up', path: '/', target: 'queue-table', title: 'The queue a reviewer works',
    body: 'Recommended coding, confidence and the flags that need attention, per invoice. The orange edge marks the workshop scenarios.' },

  { id: 'tel-doc', scene: 'Scene 1 · Routine invoice', invoice: 'telecoms', target: 'document', title: 'The invoice, as it arrived',
    body: 'A telecoms statement emailed to the AP inbox. Claude reads the PDF; the extracted fields are cross-checked against what is printed.' },
  { id: 'tel-run', scene: 'Scene 1 · Routine invoice', invoice: 'telecoms', target: 'run-agent', title: 'Run the agent live',
    body: 'Press to watch the agent work the invoice step by step. Every check is timed and logged.' },
  { id: 'tel-rail', scene: 'Scene 1 · Routine invoice', invoice: 'telecoms', target: 'process-rail', title: 'The whole non-PO process, not just coding',
    body: 'Supplier and sanctions screen, validity, duplicates, PO policy, coding, receipt, payment risk and approval routing, in the order a good process runs them.' },
  { id: 'tel-rec', scene: 'Scene 1 · Routine invoice', invoice: 'telecoms', target: 'recommendation', title: 'Coded from 18 months of history',
    body: 'Telecommunications, infrastructure cost centre, high confidence. The language model writes the reason; a scoring engine you can audit picks the account.',
    talk: '“Nobody keyed anything. Most non-PO invoices look like this, and this is where the hours go today.”' },
  { id: 'tel-route', scene: 'Scene 1 · Routine invoice', invoice: 'telecoms', target: 'approval', title: 'Routed by your approval matrix',
    body: 'Over $10k, so it goes to the cost-centre director, whose limit is checked. A standing rule covers receipt for recurring telecoms within 10% of normal.' },

  { id: 'dell-default', scene: 'Scene 2 · The Dell laptop', invoice: 'dell', target: 'default-override', title: 'The vendor default would have been wrong',
    body: 'Dell is set up against Repairs & Maintenance because of its service contracts. The line items say laptops, so the agent recommends Computer Hardware.',
    talk: '“Anyone keying this in a hurry takes the default. The agent doesn’t.”' },
  { id: 'dell-evidence', scene: 'Scene 2 · The Dell laptop', invoice: 'dell', target: 'evidence', title: 'Evidence an accountant can check',
    body: 'The closest past invoices, who approved them and how they were coded. 55 of Dell’s 60 invoices went to 1540; three that were keyed to the default had to be reclassified at close.' },
  { id: 'dell-reason', scene: 'Scene 2 · The Dell laptop', invoice: 'dell', target: 'reason', title: 'The reason, in plain English',
    body: 'Written from the engine’s findings, with the numbers that back it. Finance audiences don’t trust black boxes.' },
  { id: 'dell-cap', scene: 'Scene 2 · The Dell laptop', invoice: 'dell', target: 'treatment', title: 'Routed to Fixed Assets, not decided',
    body: '$1,845 a unit clears the $1,000 per-unit threshold for computer hardware. The agent routes it; Fixed Asset Accounting makes the capitalisation call.' },
  { id: 'dell-po', scene: 'Scene 2 · The Dell laptop', invoice: 'dell', target: 'flags', title: 'It should have been a PO',
    body: 'IT hardware needs a purchase order. The invoice is still processed, and the breach is logged for procurement, so non-PO volume shrinks at source.',
    talk: 'Pause. Ask Nazeer: “Is that the kind of thing your team catches today, and how late?”' },
  { id: 'dell-audit', scene: 'Scene 2 · Governance', invoice: 'dell', target: 'audit-tab', title: 'Every step is evidence',
    body: 'What the agent read, recommended and why, who confirmed receipt, who approved, and what changed, with timestamps. SOX evidence as a by-product.' },

  { id: 'legal-receipt', scene: 'Scene 3 · Judgement calls', invoice: 'legal', target: 'receipt', title: 'No PO, so who confirms the service?',
    body: 'The agent reads matter M-2207 from the invoice, finds the requesting lawyer in the matter register and asks her to confirm. Scan the code to confirm on a phone; approval unlocks.' },
  { id: 'legal-route', scene: 'Scene 3 · Judgement calls', invoice: 'legal', target: 'approval', title: 'Legal Operations first, because the rules say so',
    body: 'Category rules come before the amount tier. The agent applies your matrix; it does not invent one.' },
  { id: 'saas', scene: 'Scene 3 · Judgement calls', invoice: 'saas', target: 'treatment', title: 'P2P joined up with R2R',
    body: 'A 12-month subscription booked straight to expense would overstate October. The agent recommends prepaid and drafts the monthly amortisation as a standard GL interface file.' },

  { id: 'dup', scene: 'Scene 4 · Controls', invoice: 'duplicate', target: 'flags', title: 'The same invoice, sent again',
    body: 'Different number format, same amount, date and service period. Held as a likely duplicate before it reaches a payment run.' },
  { id: 'bank', scene: 'Scene 4 · Controls', invoice: 'bank_change', target: 'flags', title: 'The classic fraud pattern',
    body: 'Nearly three times the normal amount, bank details changed two days ago without a call-back, a look-alike sender domain and shortened terms. Held for vendor master review.' },
  { id: 'sod', scene: 'Scene 4 · Controls', invoice: 'sod', target: 'approval', title: 'Nobody approves their own spend',
    body: 'The requester is also the default approver for this cost centre and amount. The agent reroutes to her VP and says why.' },
  { id: 'vat', scene: 'Same pattern, more rules', invoice: 'eu_vat', target: 'flags', title: 'Tax validity, checked live',
    body: 'The VAT number on this Belgian invoice differs from the vendor master. The agent queries the EU VIES register in real time: not registered, so input VAT is at risk.' },
  { id: 'openpo', scene: 'Same pattern, more rules', invoice: 'open_po', target: 'flags', title: 'A non-PO invoice that has a PO',
    body: 'It matches an open purchase order exactly. It is sent to three-way match instead of being coded twice.' },
  { id: 'learn', scene: 'Learning loop', invoice: 'learning_1', target: 'actions', title: 'Corrections become history',
    body: 'Override the cost centre with a reason. The next invoice like it, from the same supplier, picks up the correction and its confidence rises.' },

  { id: 'journal', scene: 'Scene 6 · One engine, three processes', path: '/anomalies', target: 'laptop-journal', title: 'Nazeer’s laptop, in a manual journal',
    body: 'The same engine reads 4,000+ September close journal lines and finds the laptop refresh posted to Repairs & Maintenance, with a reclass ready to upload.' },
  { id: 'cash', scene: 'Scene 6 · One engine, three processes', path: '/anomalies', target: 'cash-source', title: 'A day of cash application',
    body: '11,400 settlement receipts. It finds the receipt applied to the wrong customer (transposed digits) and proposes matches for most of the exceptions.',
    talk: '“Vinay, that’s the 1–2% that doesn’t auto-apply today. Nazeer, that’s your horizontal anomaly layer.”' },
  { id: 'trend', scene: 'Value', path: '/insights', target: 'spend-trend', title: 'Shrink the problem, not just speed it up',
    body: 'How much AP spend arrives without a PO, month by month, and how much of it was in categories that require one.' },
  { id: 'blanket', scene: 'Value', path: '/insights', target: 'blanket-po', title: 'Where to put a blanket PO',
    body: 'Suppliers billing almost every month without a PO. Each is a candidate for a blanket PO or a standing approval rule.' },
  { id: 'wild', scene: 'Try it', path: '/', target: 'wildcard', title: 'Bring your own invoice',
    body: 'Upload any invoice PDF. Claude reads it live, uncached, and the same agent works it in front of you.' },
]
