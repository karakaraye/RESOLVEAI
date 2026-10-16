import { apiFetch, query } from "./client";
import { demoStore, type IngestComplaintInput } from "../demo-store";
import type {
  Assignee, Category, CommunicationComplianceReport, ComplaintDetail, ComplaintSummary, CustomerCommunicationItem, DataSource, ForwardingOptions, Handoff, HandoffCounts, HandoffSummary,
  NotificationPage, NotificationPreference, Page, Priority, ReportResult, ReportType, Session, WorkspaceSummary,
} from "./types";

export type ComplaintQuery = {
  q?: string; status?: string; priority?: string; category?: string; due?: string; received?: string;
  scope?: "all" | "mine"; page?: number; pageSize?: number;
};

export type IngestComplaintResponse = {
  complaintId: string;
  reference: string;
  created: boolean;
  status: string;
};

const id = (value: string) => encodeURIComponent(value);

export const api = {
  session: (signal?: AbortSignal) => apiFetch<Session>("/session", { signal }),
  signOut: () => apiFetch<{ redirectUrl?: string }>("/session/sign-out", { method: "POST" }),

  categories: async (signal?: AbortSignal): Promise<Category[]> => {
    try {
      return await apiFetch<Category[]>("/reference/categories", { signal });
    } catch {
      return [
        { code: "CARDS_ATM", label: "Cards & ATM Terminals" },
        { code: "TRANSFERS", label: "Interbank & Wire Transfers" },
        { code: "FRAUD_SECURITY", label: "Fraud & Account Security" },
        { code: "BILL_PAYMENTS", label: "Bill & Utility Payments" },
        { code: "MOBILE_APP", label: "Mobile & Digital Banking" },
        { code: "CHARGES_FEES", label: "Account Charges & Fees" },
        { code: "LOANS_CREDIT", label: "Loans & Credit Facilities" },
        { code: "ACCOUNT_SERVICE", label: "Branch & Account Services" },
      ];
    }
  },

  workspaceSummary: async (scope: "all" | "mine", signal?: AbortSignal): Promise<WorkspaceSummary> => {
    try {
      return await apiFetch<WorkspaceSummary>(`/workspace/summary${query({ scope })}`, { signal });
    } catch {
      const items = demoStore.getSummaries();
      const counts = {
        new: items.filter((i) => i.status === "NEW").length,
        needsAttention: items.filter((i) => i.status === "NEEDS_ACTION").length,
        inProgress: items.filter((i) => i.status === "IN_PROGRESS").length,
        awaitingVerification: items.filter((i) => i.status === "AWAITING_VERIFICATION").length,
        overdue: items.filter((i) => i.overdue).length,
        resolvedVerified: items.filter((i) => i.status === "RESOLVED").length,
      };
      return {
        counts,
        nextActions: [
          { kind: "REVIEW_NEW", count: counts.new },
          { kind: "INVESTIGATE", count: counts.inProgress },
        ].filter((a) => a.count > 0),
        generatedAt: new Date().toISOString(),
      };
    }
  },

  complaints: async (params: ComplaintQuery, signal?: AbortSignal): Promise<Page<ComplaintSummary>> => {
    try {
      const serverRes = await apiFetch<Page<ComplaintSummary>>(`/complaints${query(params)}`, { signal });
      const localItems = demoStore.getSummaries();
      const serverIds = new Set(serverRes.items.map((i) => i.id));
      const serverRefs = new Set(serverRes.items.map((i) => i.reference));
      const extras = localItems.filter((l) => !serverIds.has(l.id) && !serverRefs.has(l.reference));
      if (extras.length > 0 && (!params.page || params.page === 1)) {
        return {
          ...serverRes,
          items: [...extras, ...serverRes.items],
          total: serverRes.total + extras.length,
        };
      }
      return serverRes;
    } catch {
      const localSummaries = demoStore.getSummaries();
      let filtered = localSummaries;
      if (params.q) {
        const q = params.q.toLowerCase();
        filtered = filtered.filter((c) =>
          c.reference.toLowerCase().includes(q) ||
          c.customerReference.toLowerCase().includes(q) ||
          c.summary.toLowerCase().includes(q)
        );
      }
      if (params.status) filtered = filtered.filter((c) => c.status === params.status);
      if (params.priority) filtered = filtered.filter((c) => c.priority === params.priority);
      if (params.category) filtered = filtered.filter((c) => c.category?.code === params.category);
      if (params.scope === "mine") filtered = filtered.filter((c) => Boolean(c.assignedOperator));

      const page = params.page || 1;
      const pageSize = params.pageSize || 25;
      const start = (page - 1) * pageSize;
      const paged = filtered.slice(start, start + pageSize);

      return {
        items: paged,
        total: filtered.length,
        page,
        pageSize,
      };
    }
  },

  complaint: async (complaintId: string, signal?: AbortSignal): Promise<ComplaintDetail> => {
    try {
      return await apiFetch<ComplaintDetail>(`/complaints/${id(complaintId)}`, { signal });
    } catch (err) {
      const local = demoStore.getById(complaintId);
      if (local) return local;
      throw err;
    }
  },

  ingestComplaint: async (body: IngestComplaintInput, idempotencyKey?: string): Promise<IngestComplaintResponse> => {
    const key = idempotencyKey ?? (typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : String(Date.now()));
    try {
      const res = await apiFetch<IngestComplaintResponse>("/ingestion/events", {
        method: "POST",
        body: {
          eventId: key,
          customer_number: body.customerReference,
          customerReference: body.customerReference,
          customer_first_name: body.customerName.split(" ")[0] || "Valued",
          customer_last_name: body.customerName.split(" ").slice(1).join(" ") || "Customer",
          customer_email: body.customerEmail,
          customer_phone: body.customerPhone,
          account_number: body.accountNumber,
          category_code: body.categoryCode,
          source_channel: body.channel,
          channel: body.channel,
          summary: body.summary,
          narrative: body.narrative,
          priority: body.priority,
          transaction_reference: body.transactionReference,
          amount: body.amount,
          channel_acknowledged: body.sendAcknowledgement ?? true,
        },
        idempotencyKey: key,
      });
      if (typeof window !== "undefined") {
        demoStore.ingest({
          ...body,
          customerReference: body.customerReference || res.reference,
        });
      }
      return res;
    } catch {
      const created = demoStore.ingest(body);
      return {
        complaintId: created.id,
        reference: created.reference,
        created: true,
        status: created.status,
      };
    }
  },

  eligibleAssignees: (complaintId: string, signal?: AbortSignal) => apiFetch<Assignee[]>(`/complaints/${id(complaintId)}/eligible-assignees`, { signal }),
  assign: (complaintId: string, body: { assigneeId: string; reason?: string }, idempotencyKey: string) =>
    apiFetch<void>(`/complaints/${id(complaintId)}/assignment`, { method: "POST", body, idempotencyKey }),
  forwardingOptions: (complaintId: string, signal?: AbortSignal) => apiFetch<ForwardingOptions>(`/complaints/${id(complaintId)}/forwarding-options`, { signal }),
  forward: (complaintId: string, body: { teamId: string; recipient?: string; message: string }, idempotencyKey: string) =>
    apiFetch<Handoff>(`/complaints/${id(complaintId)}/handoffs`, { method: "POST", body, idempotencyKey }),
  retryHandoff: (handoffId: string, idempotencyKey: string) => apiFetch<Handoff>(`/handoffs/${id(handoffId)}/retry`, { method: "POST", idempotencyKey }),
  addNote: (complaintId: string, body: { text: string }, idempotencyKey: string) =>
    apiFetch<void>(`/complaints/${id(complaintId)}/notes`, { method: "POST", body, idempotencyKey }),
  setFollowUp: (complaintId: string, body: { dueAt: string; reason: string }, idempotencyKey: string) =>
    apiFetch<void>(`/complaints/${id(complaintId)}/follow-ups`, { method: "POST", body, idempotencyKey }),
  recordOutcome: (complaintId: string, body: { outcome: string; evidence?: string }, idempotencyKey: string) =>
    apiFetch<void>(`/complaints/${id(complaintId)}/resolution`, { method: "POST", body, idempotencyKey }),
  verifyOutcome: (complaintId: string, body: { decision: "VERIFY" | "REJECT"; note?: string }, idempotencyKey: string) =>
    apiFetch<void>(`/complaints/${id(complaintId)}/resolution/verification`, { method: "POST", body, idempotencyKey }),
  reopen: (complaintId: string, body: { reason: string }, idempotencyKey: string) =>
    apiFetch<void>(`/complaints/${id(complaintId)}/reopen`, { method: "POST", body, idempotencyKey }),

  handoffs: (params: { q?: string; state?: string; page?: number; pageSize?: number }, signal?: AbortSignal) =>
    apiFetch<Page<HandoffSummary>>(`/handoffs${query(params)}`, { signal }),
  handoffCounts: (signal?: AbortSignal) => apiFetch<HandoffCounts>("/handoffs/summary", { signal }),

  report: (type: ReportType, range: { range: string; from?: string; to?: string }, signal?: AbortSignal) =>
    apiFetch<ReportResult>(`/reports/${type.toLowerCase().replaceAll("_", "-")}${query(range)}`, { signal }),

  notifications: (params: { unread?: boolean; page?: number; pageSize?: number }, signal?: AbortSignal) =>
    apiFetch<NotificationPage>(`/notifications${query({ ...params, unread: params.unread ? "true" : undefined })}`, { signal }),
  markNotificationRead: (notificationId: string) => apiFetch<void>(`/notifications/${id(notificationId)}/read`, { method: "POST" }),
  markAllNotificationsRead: () => apiFetch<void>("/notifications/read-all", { method: "POST" }),
  notificationPreferences: (signal?: AbortSignal) => apiFetch<NotificationPreference[]>("/me/notification-preferences", { signal }),
  saveNotificationPreferences: (body: { key: string; enabled: boolean }[]) =>
    apiFetch<NotificationPreference[]>("/me/notification-preferences", { method: "PUT", body }),

  dataSources: (signal?: AbortSignal) => apiFetch<DataSource[]>("/data-sources", { signal }),
  communications: (complaintId: string, signal?: AbortSignal) =>
    apiFetch<{ complaintId: string; reference: string; total: number; items: CustomerCommunicationItem[] }>(
      `/complaints/${id(complaintId)}/communications`, { signal }
    ),
  retryCommunication: (communicationId: string, idempotencyKey: string) =>
    apiFetch<{ id: string; status: string; message: string }>(
      `/communications/${id(communicationId)}/retry`, { method: "POST", idempotencyKey }
    ),
  communicationComplianceReport: (params: { report_type?: string; from_date?: string; to_date?: string; channel?: string; status?: string }, signal?: AbortSignal) =>
    apiFetch<CommunicationComplianceReport>(`/communications/compliance-report${query(params)}`, { signal }),
};
