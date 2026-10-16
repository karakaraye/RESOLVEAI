"use client";

import type { ComplaintDetail, ComplaintSummary, Finding, Priority, TimelineEvent, TransactionRecord } from "./api/types";

const STORAGE_KEY = "resolveiq-demo-complaints";
const EVENT_NAME = "resolveiq-complaints-updated";

export type IngestComplaintInput = {
  customerName: string;
  customerReference: string;
  customerPhone?: string;
  customerEmail?: string;
  accountNumber?: string;
  channel: string;
  categoryCode: string;
  categoryLabel: string;
  priority: Priority;
  summary: string;
  narrative: string;
  transactionReference?: string;
  amount?: string;
  sendAcknowledgement?: boolean;
};

// Seed dataset representing the official hackathon demonstration cases
const seedComplaints: ComplaintDetail[] = [
  {
    id: "c-001-atm-dispense",
    reference: "CMP-2026-0001",
    receivedAt: new Date(Date.now() - 3600000 * 2).toISOString(),
    customerReference: "CUST-NGN-084920",
    summary: "Dispenser timeout at ATM terminal 04. Account debited 50,000 NGN without cash dispense.",
    category: { code: "CARDS_ATM", label: "Cards & ATM Terminals" },
    priority: "HIGH",
    status: "NEW",
    assignedOperator: undefined,
    dueAt: new Date(Date.now() + 3600000 * 22).toISOString(),
    overdue: false,
    allowedActions: ["ASSIGN", "FORWARD", "ADD_NOTE", "SET_FOLLOW_UP", "RECORD_OUTCOME"],
    narrative: "Customer attempted a cash withdrawal of 50,000 NGN at Victoria Island Branch Terminal 04. The terminal displayed a hardware timeout error message. The customer's account was immediately debited via SMS alert, but no banknotes were dispensed from the cassette.",
    sourceChannel: "Mobile Banking App",
    sourceReference: "EVT-ATM-99401",
    source: { name: "Interswitch Core Gateway", status: "AVAILABLE", lastUpdatedAt: new Date().toISOString() },
    transactions: [
      {
        reference: "TXN-REF-894021",
        sourceSystem: "Apex Core Banking Switch Journal",
        amount: { value: "50000", currency: "NGN" },
        occurredAt: new Date(Date.now() - 3600000 * 2.5).toISOString(),
        statusLabel: "FAILED_DISPENSE (Cassette Jam)",
        status: "AVAILABLE",
        lastUpdatedAt: new Date().toISOString(),
        matchEvidence: "ATM Hardware Journal confirms switch micro-sensor timeout on dispense cassette 2.",
      },
    ],
    related: [
      { id: "rel-inc-01", kind: "INCIDENT", reference: "INC-ATM-TIMEOUT", title: "Victoria Island Terminal 04 Hardware Jam Cluster", relation: "Identical terminal and error code" },
      { id: "c-002", kind: "COMPLAINT", reference: "CMP-2026-0007", title: "ATM cash retraction at Terminal 04", relation: "Same terminal within 3h" },
    ],
    findings: {
      availability: "AVAILABLE",
      category: "CARDS_ATM",
      possibleCause: "Hardware dispenser micro-switch timeout during note counting sequence.",
      confidence: 0.94,
      recommendedNextStep: "Forward to ATM Operations & Field Engineering (TEAM-ATM-OPS) for cassette inspection.",
      facts: [
        "Core ledger debited 50,000 NGN at 14:22:10 UTC.",
        "Terminal 04 switch journal recorded code ERR_CASSETTE_TIMEOUT at 14:22:38 UTC.",
        "No reversal record found in subsequent settlement cycle.",
      ],
      hypotheses: [
        "Unconfirmed dispense due to physical note jam before shutter gate opened.",
      ],
      evidence: [
        "Switch Journal Session ID #894021-VI-04.",
        "SHA-256 Digest: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855.",
      ],
    },
    notes: [
      { id: "n-1", author: "ResolveAI Ingestion Engine", createdAt: new Date(Date.now() - 3600000 * 2).toISOString(), text: "Customer complaint registered via mobile banking in-app dispute form. Automated acknowledgement dispatched." },
    ],
    handoffs: [],
    timeline: [
      { id: "tl-1", at: new Date(Date.now() - 3600000 * 2).toISOString(), kind: "RECEIVED", title: "Complaint received via Mobile Banking App", detail: "Payload hash verified. Source reference EVT-ATM-99401", actor: "Channel Ingestion Service" },
      { id: "tl-2", at: new Date(Date.now() - 3600000 * 1.99).toISOString(), kind: "COMMUNICATION_SENT", title: "Customer regulatory acknowledgement queued", detail: "SMS sent to +234 801 *** 4567. Delivery status: DELIVERED", actor: "Transactional Outbox" },
      { id: "tl-3", at: new Date(Date.now() - 3600000 * 1.95).toISOString(), kind: "AI_ANALYSIS", title: "Deterministic AI incident correlation completed", detail: "Correlated to Active Incident INC-ATM-TIMEOUT (Confidence: 94%)", actor: "ResolveAI Intelligence Engine" },
    ],
  },
  {
    id: "c-002-nip-transfer",
    reference: "CMP-2026-0002",
    receivedAt: new Date(Date.now() - 3600000 * 5).toISOString(),
    customerReference: "CUST-NGN-092144",
    summary: "Instant NIP outbound transfer debited but recipient bank never credited.",
    category: { code: "TRANSFERS", label: "Interbank & Wire Transfers" },
    priority: "HIGH",
    status: "IN_PROGRESS",
    assignedOperator: { id: "u-1", displayName: "Jessica Henderson" },
    dueAt: new Date(Date.now() + 3600000 * 19).toISOString(),
    overdue: false,
    allowedActions: ["ASSIGN", "FORWARD", "ADD_NOTE", "SET_FOLLOW_UP", "RECORD_OUTCOME"],
    narrative: "Customer transferred 150,000 NGN to GTBank account 0129849201 via Internet Banking. Sender account was debited immediately, but beneficiary has not received credit after 6 hours. Session ID indicates NIP Switch Gateway timeout.",
    sourceChannel: "Internet Banking",
    sourceReference: "EVT-NIP-10294",
    source: { name: "NIBSS Instant Payment Gateway", status: "AVAILABLE", lastUpdatedAt: new Date().toISOString() },
    transactions: [
      {
        reference: "TXN-NIP-830219",
        sourceSystem: "NIBSS Interbank Clearing Journal",
        amount: { value: "150000", currency: "NGN" },
        occurredAt: new Date(Date.now() - 3600000 * 5.2).toISOString(),
        statusLabel: "STATUS_91 (Switch Inoperative / Gateway Timeout)",
        status: "AVAILABLE",
        lastUpdatedAt: new Date().toISOString(),
        matchEvidence: "NIBSS session response code 91 indicates gateway timeout before beneficiary acknowledgement.",
      },
    ],
    related: [
      { id: "rel-inc-02", kind: "INCIDENT", reference: "INC-NIP-OUTAGE", title: "Interbank Clearing Gateway Intermittent Timeouts", relation: "Same clearing gateway window" },
    ],
    findings: {
      availability: "AVAILABLE",
      category: "TRANSFERS",
      possibleCause: "Interbank switch timeout during final credit leg.",
      confidence: 0.91,
      recommendedNextStep: "Forward to Interbank Settlements Desk (TEAM-NIP-SETTLE) for manual query with NIBSS.",
      facts: ["Sender debit confirmed.", "Switch response 91 received at 09:14 UTC."],
      hypotheses: ["Funds caught in settlement clearing buffer."],
      evidence: ["NIBSS Outward Gateway Log #830219."],
    },
    notes: [
      { id: "n-2", author: "Jessica Henderson", createdAt: new Date(Date.now() - 3600000 * 3).toISOString(), text: "Verified outward debit with operations ledger. Generating NIBSS TSQ query." },
    ],
    handoffs: [],
    timeline: [
      { id: "tl-4", at: new Date(Date.now() - 3600000 * 5).toISOString(), kind: "RECEIVED", title: "Complaint received via Internet Banking", actor: "Channel Ingestion Service" },
      { id: "tl-5", at: new Date(Date.now() - 3600000 * 4.5).toISOString(), kind: "ASSIGNED", title: "Assigned to Jessica Henderson", actor: "Supervisor" },
    ],
  },
  {
    id: "c-003-pos-fraud",
    reference: "CMP-2026-0003",
    receivedAt: new Date(Date.now() - 3600000 * 8).toISOString(),
    customerReference: "CUST-NGN-073119",
    summary: "Suspicious unauthorized POS debit card charges at retail merchant.",
    category: { code: "FRAUD_SECURITY", label: "Fraud & Account Security" },
    priority: "CRITICAL",
    status: "FORWARDED",
    assignedOperator: { id: "u-1", displayName: "Jessica Henderson" },
    dueAt: new Date(Date.now() + 3600000 * 4).toISOString(),
    overdue: false,
    allowedActions: ["ASSIGN", "ADD_NOTE", "SET_FOLLOW_UP", "RECORD_OUTCOME"],
    narrative: "Customer reported three consecutive debits of 28,500 NGN (total 85,500 NGN) at an unfamiliar merchant in Ikeja while customer was in Abuja with physical card in possession.",
    sourceChannel: "Contact Centre / Call",
    sourceReference: "EVT-CC-77312",
    source: { name: "Card Authorization Processor", status: "AVAILABLE", lastUpdatedAt: new Date().toISOString() },
    transactions: [
      {
        reference: "TXN-POS-449102",
        sourceSystem: "Mastercard POS Authorisation Stream",
        amount: { value: "85500", currency: "NGN" },
        occurredAt: new Date(Date.now() - 3600000 * 8.5).toISOString(),
        statusLabel: "APPROVED_FALLBACK_MAGSTRIPE",
        status: "AVAILABLE",
        lastUpdatedAt: new Date().toISOString(),
        matchEvidence: "Transaction authenticated via fallback magnetic stripe read rather than EMV chip, triggering high-risk fraud rule.",
      },
    ],
    related: [],
    findings: {
      availability: "AVAILABLE",
      category: "FRAUD_SECURITY",
      possibleCause: "Card cloning via compromised magnetic stripe skimmer.",
      confidence: 0.98,
      recommendedNextStep: "Card hotlisted immediately; forward to Fraud & Risk Operations.",
      facts: ["Card status: BLOCKED.", "Velocity: 3 swipes in 4 minutes."],
      hypotheses: ["Counterfeit magnetic stripe clone."],
      evidence: ["Terminal ID #POS-IKJ-99201 Magstripe Fallback flag."],
    },
    notes: [
      { id: "n-3", author: "Jessica Henderson", createdAt: new Date(Date.now() - 3600000 * 6).toISOString(), text: "Customer card has been permanently blocked. Case forwarded to Fraud & Risk Desk." },
    ],
    handoffs: [
      {
        id: "h-1",
        team: { id: "team-fraud", name: "Fraud & Risk Operations" },
        channel: "Secure Internal Queue",
        state: "DELIVERED",
        createdAt: new Date(Date.now() - 3600000 * 6).toISOString(),
        createdBy: "Jessica Henderson",
        lastUpdatedAt: new Date(Date.now() - 3600000 * 5.5).toISOString(),
        attempts: [{ at: new Date(Date.now() - 3600000 * 6).toISOString(), channel: "Secure Internal Queue", outcome: "Delivered to Fraud Queue" }],
        retryAllowed: false,
      },
    ],
    timeline: [
      { id: "tl-6", at: new Date(Date.now() - 3600000 * 8).toISOString(), kind: "RECEIVED", title: "Complaint logged via Contact Centre", actor: "Call Agent" },
      { id: "tl-7", at: new Date(Date.now() - 3600000 * 7.8).toISOString(), kind: "CARD_BLOCKED", title: "Card hotlisted immediately", actor: "Automated Safety Rule" },
      { id: "tl-8", at: new Date(Date.now() - 3600000 * 6).toISOString(), kind: "FORWARDED", title: "Forwarded to Fraud & Risk Operations", actor: "Jessica Henderson" },
    ],
  },
];

function readStorage(): ComplaintDetail[] {
  if (typeof window === "undefined") return seedComplaints;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(seedComplaints));
      return seedComplaints;
    }
    const parsed = JSON.parse(raw) as ComplaintDetail[];
    return parsed.length > 0 ? parsed : seedComplaints;
  } catch {
    return seedComplaints;
  }
}

function writeStorage(items: ComplaintDetail[]) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
    window.dispatchEvent(new Event(EVENT_NAME));
  } catch {
    // Storage quota or blocked
  }
}

export const demoStore = {
  getAll(): ComplaintDetail[] {
    return readStorage();
  },

  getSummaries(): ComplaintSummary[] {
    return readStorage().map((c) => ({
      id: c.id,
      reference: c.reference,
      receivedAt: c.receivedAt,
      customerReference: c.customerReference,
      summary: c.summary,
      category: c.category,
      priority: c.priority,
      status: c.status,
      assignedOperator: c.assignedOperator,
      assignedAt: c.assignedAt,
      dueAt: c.dueAt,
      overdue: c.overdue,
      allowedActions: c.allowedActions,
    }));
  },

  getById(idOrRef: string): ComplaintDetail | undefined {
    const items = readStorage();
    const query = idOrRef.toLowerCase().trim();
    return items.find((c) => c.id.toLowerCase() === query || c.reference.toLowerCase() === query);
  },

  ingest(input: IngestComplaintInput): ComplaintDetail {
    const items = readStorage();
    const now = new Date();
    const year = now.getFullYear();
    const count = items.length + 1;
    const refSequence = String(count).padStart(4, "0");
    const reference = `CMP-${year}-${refSequence}`;
    const id = `cmp-${crypto.randomUUID ? crypto.randomUUID() : Date.now()}`;

    // SLA calculation based on regulatory priority
    const slaHours: Record<Priority, number> = {
      CRITICAL: 12,
      HIGH: 24,
      MEDIUM: 48,
      LOW: 72,
    };
    const dueAt = new Date(now.getTime() + slaHours[input.priority] * 3600000).toISOString();

    const timeline: TimelineEvent[] = [
      {
        id: `tl-${Date.now()}-1`,
        at: now.toISOString(),
        kind: "RECEIVED",
        title: `Complaint received via ${input.channel}`,
        detail: `External source payload verified. Logged as ${reference}.`,
        actor: "Channel Ingestion Gateway",
      },
    ];

    if (input.sendAcknowledgement !== false) {
      timeline.push({
        id: `tl-${Date.now()}-2`,
        at: new Date(now.getTime() + 500).toISOString(),
        kind: "COMMUNICATION_SENT",
        title: "Automated regulatory acknowledgement queued",
        detail: `Sent SMS & Email notification to ${input.customerPhone || input.customerEmail || "customer contact"}. Audit digest registered.`,
        actor: "Transactional Outbox",
      });
    }

    // AI Semantic Correlation findings
    const aiFindings: Finding = {
      availability: "AVAILABLE",
      category: input.categoryCode,
      possibleCause: `Potential ${input.categoryLabel.toLowerCase()} settlement delay or channel timeout.`,
      confidence: 0.92,
      recommendedNextStep: input.priority === "CRITICAL"
        ? "Priority escalation: immediate team routing required within 1 hour SLA."
        : "Initial triage complete. Assign case manager or inspect journal evidence.",
      facts: [
        `Channel: ${input.channel}`,
        `Customer reference: ${input.customerReference}`,
        input.amount ? `Disputed value: ${input.amount} NGN` : "Amount not specified",
        `Regulatory SLA deadline: ${slaHours[input.priority]} hours`,
      ],
      hypotheses: [
        "System ledger anomaly pending core banking switch confirmation.",
      ],
      evidence: [
        `Ingestion event payload registered at ${now.toLocaleTimeString()}`,
        input.transactionReference ? `Linked transaction journal: ${input.transactionReference}` : "Pending journal reconciliation",
      ],
    };

    const transactions: TransactionRecord[] = input.transactionReference ? [
      {
        reference: input.transactionReference,
        sourceSystem: `${input.channel} Core Journal`,
        amount: input.amount ? { value: input.amount.replace(/[^0-9.]/g, ""), currency: "NGN" } : undefined,
        occurredAt: now.toISOString(),
        statusLabel: "PENDING_INVESTIGATION",
        status: "AVAILABLE",
        lastUpdatedAt: now.toISOString(),
        matchEvidence: `Linked via live complaint submission by operator.`,
      },
    ] : [];

    const newComplaint: ComplaintDetail = {
      id,
      reference,
      receivedAt: now.toISOString(),
      customerReference: input.customerReference || `CUST-NGN-${Math.floor(100000 + Math.random() * 900000)}`,
      summary: input.summary,
      category: { code: input.categoryCode, label: input.categoryLabel },
      priority: input.priority,
      status: "NEW",
      assignedOperator: undefined,
      dueAt,
      overdue: false,
      allowedActions: ["ASSIGN", "FORWARD", "ADD_NOTE", "SET_FOLLOW_UP", "RECORD_OUTCOME"],
      narrative: input.narrative,
      sourceChannel: input.channel,
      sourceReference: `EVT-DEMO-${Math.floor(10000 + Math.random() * 90000)}`,
      source: { name: `${input.channel} Feed`, status: "AVAILABLE", lastUpdatedAt: now.toISOString() },
      transactions,
      related: [],
      findings: aiFindings,
      notes: [
        {
          id: `note-${Date.now()}`,
          author: "Live Hackathon Intake",
          createdAt: now.toISOString(),
          text: `Complaint submitted during live demonstration. Customer: ${input.customerName}.`,
        },
      ],
      handoffs: [],
      timeline,
    };

    const updated = [newComplaint, ...items];
    writeStorage(updated);
    return newComplaint;
  },

  resetToDefault() {
    writeStorage(seedComplaints);
  },
};
