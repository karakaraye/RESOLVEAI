import type { ComplaintAction, ComplaintStatus, HandoffState, NextActionKind, Priority, ReportType, SourceStatus } from "./api/types";

export type Tone = "neutral" | "info" | "accent" | "warning" | "danger" | "success" | "verify";

export const statusMeta: Record<ComplaintStatus, { label: string; tone: Tone }> = {
  NEW: { label: "New", tone: "info" },
  NEEDS_ACTION: { label: "Needs action", tone: "warning" },
  IN_PROGRESS: { label: "In progress", tone: "accent" },
  FORWARDED: { label: "Forwarded", tone: "neutral" },
  AWAITING_VERIFICATION: { label: "Awaiting verification", tone: "verify" },
  RESOLVED: { label: "Resolved", tone: "success" },
  REOPENED: { label: "Reopened", tone: "warning" },
};
export const statusOrder = Object.keys(statusMeta) as ComplaintStatus[];

export const priorityMeta: Record<Priority, { label: string; tone: Tone }> = {
  CRITICAL: { label: "Critical", tone: "danger" },
  HIGH: { label: "High", tone: "danger" },
  MEDIUM: { label: "Medium", tone: "warning" },
  LOW: { label: "Low", tone: "neutral" },
};
export const priorityOrder = Object.keys(priorityMeta) as Priority[];

// Each handoff state is distinct: submitted is not delivered, delivered is not acknowledged, and so on.
export const handoffMeta: Record<HandoffState, { label: string; tone: Tone; meaning: string }> = {
  PREPARED: { label: "Prepared", tone: "neutral", meaning: "The handoff is being prepared. Nothing has been sent." },
  RETRY_SCHEDULED: { label: "Retry scheduled", tone: "warning", meaning: "The send is being retried. It is not complete." },
  FALLBACK_IN_PROGRESS: { label: "Trying approved fallback", tone: "warning", meaning: "The first channel failed; RESOLVEIQ is trying the next approved channel." },
  SEND_FAILED: { label: "Send failed", tone: "danger", meaning: "Every approved channel failed. The complaint was not handed off." },
  SENT: { label: "Sent", tone: "info", meaning: "Submitted through the approved channel. Receipt is not confirmed yet." },
  DELIVERY_UNCONFIRMED: { label: "Sent · delivery unconfirmed", tone: "warning", meaning: "Submission happened but the channel has not confirmed delivery." },
  DELIVERED: { label: "Delivered", tone: "info", meaning: "The receiving channel confirmed delivery." },
  ACKNOWLEDGED: { label: "Acknowledged", tone: "accent", meaning: "The receiving team or system confirmed receipt." },
  ACCEPTED: { label: "Accepted", tone: "accent", meaning: "The receiving team accepted responsibility." },
  AWAITING_RESPONSE: { label: "Awaiting response", tone: "neutral", meaning: "No response from the receiving team has been recorded." },
  RESPONDED: { label: "Responded", tone: "success", meaning: "A response from the receiving team has been recorded." },
  OVERDUE: { label: "Overdue", tone: "danger", meaning: "The response deadline passed without the expected outcome." },
  CLOSED: { label: "Closed", tone: "success", meaning: "The handoff's work is complete." },
};
export const handoffOrder = Object.keys(handoffMeta) as HandoffState[];

export const sourceMeta: Record<SourceStatus, { label: string; tone: Tone }> = {
  AVAILABLE: { label: "Current", tone: "success" },
  STALE: { label: "Stale", tone: "warning" },
  UNAVAILABLE: { label: "Unavailable", tone: "danger" },
  UNKNOWN: { label: "Unknown", tone: "neutral" },
};

export const actionLabels: Record<ComplaintAction, string> = {
  ASSIGN: "Assign or reassign",
  FORWARD: "Forward to team",
  ADD_NOTE: "Add note",
  SET_FOLLOW_UP: "Set follow-up",
  RECORD_OUTCOME: "Record outcome",
  VERIFY_OUTCOME: "Verify outcome",
  REOPEN: "Reopen case",
};
export const actionOrder = Object.keys(actionLabels) as ComplaintAction[];
export const actionParam = (action: ComplaintAction) => action.toLowerCase().replaceAll("_", "-");
export const actionFromParam = (value: string | null) => actionOrder.find((action) => actionParam(action) === value);

// Where each Home "next action" leads. Destinations are list filters or a specific complaint section.
export const nextActionMeta: Record<NextActionKind, { label: string; detail: string; href: (complaintId?: string) => string; tone: Tone }> = {
  OVERDUE: { label: "Address overdue cases", detail: "Past their deadline", href: () => "/my-cases?due=overdue", tone: "danger" },
  EXCEPTION: { label: "Resolve exceptions", detail: "No eligible team or every send failed", href: () => "/forwarded?state=SEND_FAILED", tone: "danger" },
  REVIEW_NEW: { label: "Review new complaints", detail: "Awaiting first review", href: () => "/complaints?status=NEW", tone: "info" },
  DEADLINE_APPROACHING: { label: "Review approaching deadlines", detail: "Due within 24 hours", href: () => "/my-cases?due=soon", tone: "warning" },
  FOLLOW_UP_RESPONSE: { label: "Follow up on pending responses", detail: "Forwarded with no response yet", href: () => "/forwarded?state=AWAITING_RESPONSE", tone: "warning" },
  REVIEW_RESPONSE: { label: "Review team responses", detail: "A receiving team replied", href: (id) => (id ? `/complaints/${id}#timeline` : "/forwarded?state=RESPONDED"), tone: "accent" },
  VERIFY_RESOLUTION: { label: "Verify reported outcomes", detail: "Reported, not yet verified", href: (id) => (id ? `/complaints/${id}#resolution` : "/complaints?status=AWAITING_VERIFICATION"), tone: "verify" },
  REVIEW_REOPENED: { label: "Review reopened cases", detail: "Reopened with a new reason", href: (id) => (id ? `/complaints/${id}` : "/complaints?status=REOPENED"), tone: "warning" },
  COMPLETE_INFORMATION: { label: "Complete case information", detail: "Missing required details", href: (id) => (id ? `/complaints/${id}#overview` : "/complaints?status=NEEDS_ACTION"), tone: "neutral" },
  INVESTIGATE: { label: "Investigate cases", detail: "Evidence needs review", href: (id) => (id ? `/complaints/${id}#evidence` : "/complaints?status=IN_PROGRESS"), tone: "neutral" },
  FORWARD: { label: "Forward to the right team", detail: "A team has been suggested", href: (id) => (id ? `/complaints/${id}?action=forward` : "/complaints?status=NEEDS_ACTION"), tone: "neutral" },
};
export const nextActionOrder = Object.keys(nextActionMeta) as NextActionKind[];

export const reportTypes: { type: ReportType; label: string; question: string }[] = [
  { type: "OVERVIEW", label: "Overview", question: "How is complaint work moving overall?" },
  { type: "COMPLAINT_VOLUMES", label: "Complaint volumes", question: "How many complaints arrived, and when?" },
  { type: "RECURRING_ISSUES", label: "Recurring issues", question: "Which issues keep coming back?" },
  { type: "RESOLUTION_PERFORMANCE", label: "Resolution performance", question: "How quickly are cases verified as resolved?" },
  { type: "TEAM_RESPONSE_TIMES", label: "Team response times", question: "How fast do receiving teams acknowledge and respond?" },
  { type: "OVERDUE_CASES", label: "Overdue cases", question: "What is past its deadline, and where?" },
  { type: "INCIDENT_TRENDS", label: "Incident trends", question: "Which potential shared incidents are growing?" },
];

export const dateRanges = [
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
  { value: "90d", label: "Last 90 days" },
  { value: "custom", label: "Custom range" },
];
