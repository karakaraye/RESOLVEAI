// Test-only fixtures for mocked API responses. Fictional values; never imported by the application.
import type { Page, Route } from "@playwright/test";
import type {
  ComplaintDetail, ComplaintSummary, DataSource, ForwardingOptions, Handoff, HandoffSummary, NotificationPage, ReportResult, Session, WorkspaceSummary,
} from "../src/lib/api/types";

export const API = "http://api.biirs.test/api/v1";
const now = Date.now();
const iso = (hoursAgo: number) => new Date(now - hoursAgo * 3600_000).toISOString();

export const session: Session = {
  user: { id: "u-1", displayName: "Test Operator", email: "operator@bank.test", department: "Customer Care", roleLabel: "Operator" },
  tenant: { id: "t-1", name: "Test Bank", timeZone: "Africa/Lagos", support: { label: "Test Bank BIIRS desk", contact: "biirs-support@bank.test", hours: "Mon–Fri 08:00–18:00" } },
  permissions: ["complaints.read"],
  session: { identityProvider: "Test Identity", signedInAt: iso(2), expiresAt: iso(-6), signOutAffectsOtherSessions: false },
};

const issues = ["Transfer not received", "Card declined repeatedly", "Incorrect charge on statement", "Cannot access mobile app", "Account not credited after deposit", "ATM cash not dispensed"];
const categories = [{ code: "TRANSFER", label: "Transfer" }, { code: "CARD", label: "Card" }, { code: "CHARGES", label: "Charges" }, { code: "MOBILE", label: "Mobile banking" }, { code: "ACCOUNT", label: "Account" }, { code: "ATM", label: "ATM" }];
const statuses = ["NEW", "NEEDS_ACTION", "IN_PROGRESS", "FORWARDED", "AWAITING_VERIFICATION", "RESOLVED", "REOPENED"] as const;
const priorities = ["HIGH", "MEDIUM", "CRITICAL", "LOW"] as const;

export const complaints: ComplaintSummary[] = Array.from({ length: 32 }, (_, i) => ({
  id: `c-${1000 + i}`,
  reference: `TST-${1045 - i}`,
  receivedAt: iso(i * 5 + 1),
  customerReference: `•••• ${String(1234 + i * 7).slice(-4)}`,
  summary: issues[i % issues.length],
  category: categories[i % categories.length],
  priority: priorities[i % priorities.length],
  status: statuses[i % statuses.length],
  assignedOperator: i % 3 === 0 ? undefined : { id: "u-1", displayName: "Test Operator" },
  assignedAt: iso(i * 5),
  dueAt: i % 4 === 0 ? undefined : iso(-24 + i * 3),
  overdue: i % 5 === 1,
  allowedActions: statuses[i % statuses.length] === "RESOLVED" ? ["ADD_NOTE", "REOPEN"] : statuses[i % statuses.length] === "AWAITING_VERIFICATION" ? ["ADD_NOTE", "VERIFY_OUTCOME"] : ["ASSIGN", "FORWARD", "ADD_NOTE", "SET_FOLLOW_UP", "RECORD_OUTCOME"],
}));

const handoff = (state: Handoff["state"], hoursAgo: number, extra: Partial<Handoff> = {}): Handoff => ({
  id: `h-${state}-${hoursAgo}`, team: { id: "team-settle", name: "Settlements team" }, recipient: "Duty lead", channel: "Bank case-management queue", state,
  createdAt: iso(hoursAgo), createdBy: "Test Operator", lastUpdatedAt: iso(hoursAgo - 1), responseDueAt: iso(hoursAgo - 24),
  attempts: [{ at: iso(hoursAgo), channel: "Case-management queue", outcome: state === "SEND_FAILED" ? "Rejected: queue unavailable" : "Submitted" }],
  retryAllowed: state === "SEND_FAILED", ...extra,
});

export const detail: ComplaintDetail = {
  ...complaints[1],
  status: "NEEDS_ACTION",
  allowedActions: ["ASSIGN", "FORWARD", "ADD_NOTE", "SET_FOLLOW_UP", "RECORD_OUTCOME"],
  narrative: "Customer reports a transfer sent on Monday morning has not reached the recipient. The amount left their account. They contacted the branch and were told to wait 24 hours, which has now passed.",
  sourceChannel: "Contact centre",
  sourceReference: "CC-TEST-55821",
  source: { name: "Contact centre feed", status: "AVAILABLE", lastUpdatedAt: iso(0.5) },
  transactions: [
    { reference: "TXN-TEST-90311", sourceSystem: "Core banking", amount: { value: "45,000.00", currency: "NGN" }, occurredAt: iso(30), statusLabel: "Debited", status: "STALE", lastUpdatedAt: iso(9), conflict: "core banking shows debited; switch shows pending", matchEvidence: "Same account, amount and time window as the complaint" },
  ],
  related: [{ id: "c-1007", kind: "COMPLAINT", reference: "TST-1038", title: "Transfer not received", relation: "Possible duplicate" }, { id: "inc-1", kind: "INCIDENT", reference: "INC-TEST-7", title: "Interbank transfers delayed", relation: "Possibly part of" }],
  findings: { availability: "AVAILABLE", category: "Transfer", possibleCause: "Interbank switch delay", confidence: 0.62, recommendedNextStep: "The settlements team handles switch delays; forwarding is suggested.", facts: ["The debit is recorded in core banking."], hypotheses: ["The transfer is held at the interbank switch.", "Related to INC-TEST-7, which has 14 linked complaints."], evidence: ["Switch status: pending (updated 9 hours ago)"] },
  notes: [{ id: "n1", author: "Test Operator", createdAt: iso(3), text: "Called the customer to confirm the amount and time." }],
  handoffs: [handoff("SEND_FAILED", 6)],
  timeline: [
    { id: "e1", at: iso(28), kind: "RECEIVED", title: "Complaint received", detail: "Contact centre" },
    { id: "e2", at: iso(20), kind: "ASSIGNED", title: "Assigned to Test Operator", actor: "Routing rules" },
    { id: "e3", at: iso(6), kind: "HANDOFF", title: "Forwarding failed", detail: "All approved channels failed; added to exception queue" },
  ],
};

const summary: WorkspaceSummary = {
  counts: { new: 6, needsAttention: 5, inProgress: 9, awaitingVerification: 3, overdue: 2, resolvedVerified: 14, totalAssigned: 18 },
  nextActions: [{ kind: "REVIEW_NEW", count: 6 }, { kind: "OVERDUE", count: 2 }, { kind: "FOLLOW_UP_RESPONSE", count: 4 }, { kind: "VERIFY_RESOLUTION", count: 1, complaintId: "c-1004" }, { kind: "DEADLINE_APPROACHING", count: 3 }],
  generatedAt: iso(0),
};

const forwarding: ForwardingOptions = {
  recommendedTeamId: "team-settle",
  teams: [{ id: "team-settle", name: "Settlements team", recipients: ["Duty lead", "Reconciliation desk"], channel: "Bank case-management queue", responseDueHours: 24 }, { id: "team-cards", name: "Card operations", recipients: [], channel: "Secure email", responseDueHours: 48 }],
  shareableSummary: "TST-1044 · Transfer not received. Customer reports a debited transfer has not reached the recipient after 24 hours. Transaction TXN-TEST-90311.",
  sharedFields: ["Complaint reference", "Issue summary", "Transaction reference", "Masked customer reference"],
};

const handoffs: HandoffSummary[] = [
  { ...handoff("AWAITING_RESPONSE", 30), complaint: complaints[3] },
  { ...handoff("DELIVERY_UNCONFIRMED", 12, { team: { id: "team-cards", name: "Card operations" }, recipient: undefined }), complaint: complaints[8] },
  { ...handoff("SEND_FAILED", 6), complaint: complaints[1] },
  { ...handoff("RESPONDED", 60, { response: { receivedAt: iso(40), summary: "Reversal processed." } }), complaint: complaints[10] },
  { ...handoff("OVERDUE", 90), complaint: complaints[17] },
];

const series = Array.from({ length: 30 }, (_, i) => ({ date: new Date(now - (29 - i) * 86400_000).toISOString().slice(0, 10), value: i === 12 ? null : 8 + ((i * 7) % 11) + Math.round(i / 3) }));
export const report = (type: string): ReportResult => ({
  type: type.toUpperCase().replaceAll("-", "_") as ReportResult["type"],
  period: { from: series[0].date, to: series.at(-1)!.date },
  coverage: { complete: type !== "team-response-times", note: type === "team-response-times" ? "Two receiving channels don’t report acknowledgement times." : undefined, sources: [{ name: "Contact centre feed", status: "AVAILABLE", lastUpdatedAt: iso(0.5) }, { name: "Core banking", status: "STALE", lastUpdatedAt: iso(9) }] },
  definitions: [{ term: "Verified resolved", meaning: "Outcome confirmed by an authorised verifier." }, { term: "Received", meaning: "Time the complaint entered the bank’s channel." }],
  metrics: [{ key: "total", label: "Complaints received", value: 412, filter: "received=30d" }, { key: "open", label: "Still open", value: 61, filter: "status=IN_PROGRESS" }, { key: "verified", label: "Verified resolved", value: 296, filter: "status=RESOLVED" }, { key: "time", label: "Median time to verify", value: type === "overview" ? 31.5 : null, unit: "hours" }],
  series: type === "complaint-volumes" || type === "overview" ? { label: "Complaints received", points: series } : undefined,
  rows: type === "complaint-volumes" ? undefined : {
    heading: type === "overview" ? "Cases by status" : "Most frequent issues", valueLabel: "complaints",
    items: type === "overview"
      ? [{ label: "IN_PROGRESS", value: 61, filter: "status=IN_PROGRESS" }, { label: "NEW", value: 24, filter: "status=NEW" }, { label: "AWAITING_VERIFICATION", value: 19, filter: "status=AWAITING_VERIFICATION" }, { label: "NEEDS_ACTION", value: 12, filter: "status=NEEDS_ACTION" }]
      : issues.map((label, i) => ({ label, value: 120 - i * 17, secondary: categories[i].label, filter: `category=${categories[i].code}` })),
  },
  generatedAt: iso(0.1),
});

const notifications: NotificationPage = {
  items: [
    { id: "nt1", kind: "ASSIGNED", title: "TST-1044 was assigned to you", occurredAt: iso(0.3), read: false, complaint: { id: "c-1001", reference: "TST-1044" } },
    { id: "nt2", kind: "RESPONSE", title: "Settlements team responded on TST-1035", occurredAt: iso(2), read: false, complaint: { id: "c-1010", reference: "TST-1035" } },
    { id: "nt3", kind: "DEADLINE", title: "TST-1040 is due in 4 hours", occurredAt: iso(5), read: true, complaint: { id: "c-1005", reference: "TST-1040" } },
  ],
  total: 3, page: 1, pageSize: 25, unreadCount: 2,
};

const dataSources: DataSource[] = [
  { id: "s1", name: "Contact centre feed", kind: "Complaint intake", status: "AVAILABLE", lastUpdatedAt: iso(0.5) },
  { id: "s2", name: "Core banking", kind: "Transactions", status: "STALE", lastUpdatedAt: iso(9), note: "Updates are delayed; transaction details may be out of date." },
];

type Handler = (route: Route, url: URL, body: unknown) => unknown;
export type Overrides = Record<string, Handler | object | number>;

// Routes every API call to fixtures. Overrides are keyed "METHOD /path" (path relative to /api/v1).
export async function mockApi(page: Page, overrides: Overrides = {}) {
  const calls: { method: string; path: string; body: unknown; headers: Record<string, string> }[] = [];
  await page.route(`${API}/**`, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace("/api/v1", "");
    const body = request.postData() ? JSON.parse(request.postData()!) : undefined;
    calls.push({ method: request.method(), path, body, headers: request.headers() });
    const key = `${request.method()} ${path}`;
    const override = overrides[key];
    if (typeof override === "number") return route.fulfill({ status: override, json: { message: `Test failure ${override}` } });
    if (typeof override === "function") {
      const result = await override(route, url, body);
      if (result === undefined) return;
      return route.fulfill({ json: result });
    }
    if (override) return route.fulfill({ json: override });
    return route.fulfill(defaultResponse(request.method(), path, url));
  });
  return calls;
}

function defaultResponse(method: string, path: string, url: URL) {
  if (method !== "GET") return { status: path.endsWith("/handoffs") ? 200 : 204, json: path.endsWith("/handoffs") ? handoff("SENT", 0) : undefined };
  if (path === "/session") return { json: session };
  if (path === "/reference/categories") return { json: categories };
  if (path === "/workspace/summary") return { json: summary };
  if (path === "/complaints") {
    const scope = url.searchParams.get("scope");
    const status = url.searchParams.get("status");
    const q = url.searchParams.get("q")?.toLowerCase();
    let items = complaints.filter((c) => (scope !== "mine" || c.assignedOperator) && (!status || c.status === status) && (!q || `${c.reference} ${c.summary}`.toLowerCase().includes(q)));
    const total = items.length;
    const pageSize = Number(url.searchParams.get("pageSize") ?? 25);
    const page = Number(url.searchParams.get("page") ?? 1);
    items = items.slice((page - 1) * pageSize, page * pageSize);
    return { json: { items, total, page, pageSize } };
  }
  if (/^\/complaints\/[^/]+$/.test(path)) return path.endsWith("missing") ? { status: 404, json: { message: "Not found" } } : { json: { ...detail, id: path.split("/")[2] } };
  if (path.endsWith("/eligible-assignees")) return { json: [{ id: "u-1", displayName: "Test Operator", team: "Customer Care", openCases: 18 }, { id: "u-2", displayName: "Second Operator", team: "Customer Care", openCases: 9 }] };
  if (path.endsWith("/forwarding-options")) return { json: forwarding };
  if (path === "/handoffs") return { json: { items: handoffs, total: handoffs.length, page: 1, pageSize: 25 } };
  if (path === "/handoffs/summary") return { json: { total: 41, awaitingResponse: 9, responded: 27, overdue: 3, failed: 2 } };
  if (path.startsWith("/reports/")) return { json: report(path.split("/")[2]) };
  if (path === "/notifications") return { json: url.searchParams.get("unread") ? { ...notifications, items: notifications.items.filter((n) => !n.read), total: 2 } : notifications };
  if (path === "/me/notification-preferences") return { json: [{ key: "assigned", label: "Cases assigned to me", description: "When a complaint is assigned to you", enabled: true }, { key: "responses", label: "Team responses", description: "When a receiving team replies to a handoff", enabled: true }, { key: "deadlines", label: "Approaching deadlines", description: "24 hours before a case is due", enabled: false }] };
  if (path === "/data-sources") return { json: dataSources };
  return { status: 404, json: { message: "No fixture" } };
}
