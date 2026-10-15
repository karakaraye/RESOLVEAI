// Wire types for the RESOLVEIQ API (/api/v1). Documented in docs/api-contract.md; the API is the source of truth
// for permissions and state transitions, the browser only renders what the server allows.

export type Priority = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export type ComplaintStatus =
  | "NEW"
  | "NEEDS_ACTION"
  | "IN_PROGRESS"
  | "FORWARDED"
  | "AWAITING_VERIFICATION"
  | "RESOLVED"
  | "REOPENED";

export type HandoffState =
  | "PREPARED"
  | "RETRY_SCHEDULED"
  | "FALLBACK_IN_PROGRESS"
  | "SEND_FAILED"
  | "SENT"
  | "DELIVERY_UNCONFIRMED"
  | "DELIVERED"
  | "ACKNOWLEDGED"
  | "ACCEPTED"
  | "AWAITING_RESPONSE"
  | "RESPONDED"
  | "OVERDUE"
  | "CLOSED";

export type SourceStatus = "AVAILABLE" | "STALE" | "UNAVAILABLE" | "UNKNOWN";

export type ComplaintAction =
  | "ASSIGN"
  | "FORWARD"
  | "ADD_NOTE"
  | "SET_FOLLOW_UP"
  | "RECORD_OUTCOME"
  | "VERIFY_OUTCOME"
  | "REOPEN";

export type Page<T> = { items: T[]; total: number; page: number; pageSize: number };

export type Session = {
  user: { id: string; displayName: string; email: string; department?: string; roleLabel: string };
  tenant: { id: string; name: string; timeZone: string; support?: { label: string; contact: string; hours?: string } };
  permissions: string[];
  session: { identityProvider: string; signedInAt: string; expiresAt?: string; signOutAffectsOtherSessions?: boolean };
};

export type Category = { code: string; label: string };

export type Person = { id: string; displayName: string };

export type ComplaintSummary = {
  id: string;
  reference: string;
  receivedAt: string;
  customerReference: string;
  summary: string;
  category?: Category;
  priority: Priority;
  status: ComplaintStatus;
  assignedOperator?: Person;
  assignedAt?: string;
  dueAt?: string;
  overdue: boolean;
  allowedActions: ComplaintAction[];
};

export type SourceFact = { name: string; status: SourceStatus; lastUpdatedAt?: string };

export type TransactionRecord = {
  reference: string;
  sourceSystem: string;
  amount?: { value: string; currency: string };
  occurredAt?: string;
  statusLabel?: string;
  status: SourceStatus;
  lastUpdatedAt?: string;
  conflict?: string;
  matchEvidence?: string;
};

export type RelatedRecord = { id: string; kind: "COMPLAINT" | "INCIDENT"; reference: string; title: string; relation: string };

export type Finding = {
  availability: "AVAILABLE" | "UNAVAILABLE" | "LOW_CONFIDENCE";
  category?: string;
  possibleCause?: string;
  confidence?: number;
  recommendedNextStep?: string;
  facts: string[];
  hypotheses: string[];
  evidence: string[];
};

export type Handoff = {
  id: string;
  team: { id: string; name: string };
  recipient?: string;
  channel: string;
  state: HandoffState;
  createdAt: string;
  createdBy: string;
  lastUpdatedAt: string;
  responseDueAt?: string;
  response?: { receivedAt: string; summary: string };
  attempts: { at: string; channel: string; outcome: string }[];
  retryAllowed: boolean;
};

export type TimelineEvent = { id: string; at: string; kind: string; title: string; detail?: string; actor?: string };

export type Note = { id: string; author: string; createdAt: string; text: string };

export type Resolution = {
  outcome: string;
  evidence?: string;
  reportedAt: string;
  reportedBy: string;
  verification: "AWAITING" | "VERIFIED" | "REJECTED";
  verifiedAt?: string;
  verifiedBy?: string;
};

export type ComplaintDetail = ComplaintSummary & {
  narrative: string;
  sourceChannel: string;
  sourceReference: string;
  source: SourceFact;
  transactions: TransactionRecord[];
  related: RelatedRecord[];
  findings: Finding;
  notes: Note[];
  handoffs: Handoff[];
  resolution?: Resolution;
  reopenReason?: string;
  timeline: TimelineEvent[];
};

export type NextActionKind =
  | "REVIEW_NEW"
  | "COMPLETE_INFORMATION"
  | "INVESTIGATE"
  | "FORWARD"
  | "FOLLOW_UP_RESPONSE"
  | "DEADLINE_APPROACHING"
  | "OVERDUE"
  | "REVIEW_RESPONSE"
  | "VERIFY_RESOLUTION"
  | "REVIEW_REOPENED"
  | "EXCEPTION";

export type NextAction = { kind: NextActionKind; count: number; complaintId?: string };

export type WorkspaceSummary = {
  counts: { new: number; needsAttention: number; inProgress: number; awaitingVerification: number; overdue: number; resolvedVerified: number; totalAssigned?: number };
  nextActions: NextAction[];
  generatedAt: string;
};

export type HandoffSummary = Handoff & { complaint: Pick<ComplaintSummary, "id" | "reference" | "customerReference" | "summary"> };

export type HandoffCounts = { total: number; awaitingResponse: number; responded: number; overdue: number; failed: number };

export type ReportType =
  | "OVERVIEW"
  | "COMPLAINT_VOLUMES"
  | "RECURRING_ISSUES"
  | "RESOLUTION_PERFORMANCE"
  | "TEAM_RESPONSE_TIMES"
  | "OVERDUE_CASES"
  | "INCIDENT_TRENDS";

export type ReportMetric = { key: string; label: string; value: number | null; unit?: "count" | "hours" | "percent"; filter?: string };
export type ReportRow = { label: string; value: number | null; secondary?: string; filter?: string };

export type ReportResult = {
  type: ReportType;
  period: { from: string; to: string };
  coverage: { complete: boolean; note?: string; sources: SourceFact[] };
  definitions: { term: string; meaning: string }[];
  metrics: ReportMetric[];
  series?: { label: string; points: { date: string; value: number | null }[] };
  rows?: { heading: string; valueLabel: string; items: ReportRow[] };
  generatedAt: string;
};

export type NotificationItem = {
  id: string;
  kind: string;
  title: string;
  occurredAt: string;
  read: boolean;
  complaint?: { id: string; reference: string };
};

export type NotificationPage = Page<NotificationItem> & { unreadCount: number };

export type NotificationPreference = { key: string; label: string; description: string; enabled: boolean };

export type ForwardingOptions = {
  recommendedTeamId?: string;
  teams: { id: string; name: string; recipients: string[]; channel: string; responseDueHours?: number }[];
  shareableSummary: string;
  sharedFields: string[];
};

export type Assignee = { id: string; displayName: string; team?: string; openCases?: number };

export type DataSource = { id: string; name: string; kind: string; status: SourceStatus; lastUpdatedAt?: string; note?: string };

export type CommunicationDeliveryAttempt = {
  id: string;
  attempt_number: number;
  channel: string;
  provider: string;
  status: string;
  provider_reference: string;
  latency_ms: number;
  error_detail: string;
  attempted_at: string;
};

export type CommunicationEventItem = {
  id: string;
  event_type: string;
  title: string;
  detail: string;
  actor: string;
  timestamp: string;
};

export type CustomerCommunicationItem = {
  id: string;
  complaint_id: string;
  complaint_reference: string;
  customer_reference: string;
  category: string;
  category_label: string;
  channel: string;
  masked_destination: string;
  subject: string;
  rendered_content: string;
  status: "PENDING" | "QUEUED" | "SENDING" | "SENT" | "DELIVERY_UNCONFIRMED" | "DELIVERED" | "FAILED" | "CANCELLED";
  trigger_event: string;
  verification_reference: string;
  provider: string;
  provider_message_id?: string;
  error_message?: string;
  retry_count: number;
  max_retries: number;
  queued_at: string;
  sent_at?: string;
  delivered_at?: string;
  cancelled_at?: string;
  cancellation_reason?: string;
  delivery_attempts: CommunicationDeliveryAttempt[];
  events: CommunicationEventItem[];
  created_at: string;
  updated_at: string;
};

export type CommunicationComplianceReport = {
  tenant: string;
  reportType: string;
  totalCount: number;
  generatedAt: string;
  regulatoryNotice: string;
  records: {
    id: string;
    complaintReference: string;
    customerReference: string;
    category: string;
    channel: string;
    maskedDestination: string;
    status: string;
    triggerEvent: string;
    verificationReference: string;
    templateCode: string;
    templateVersion: number;
    provider: string;
    providerMessageId?: string;
    retryCount: number;
    queuedAt?: string;
    deliveredAt?: string;
    cancelledAt?: string;
    cancellationReason?: string;
    errorMessage?: string;
    deliveryAttemptsCount: number;
  }[];
};
