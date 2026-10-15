import { apiFetch, query } from "./client";
import type {
  Assignee, Category, CommunicationComplianceReport, ComplaintDetail, ComplaintSummary, CustomerCommunicationItem, DataSource, ForwardingOptions, Handoff, HandoffCounts, HandoffSummary,
  NotificationPage, NotificationPreference, Page, ReportResult, ReportType, Session, WorkspaceSummary,
} from "./types";

export type ComplaintQuery = {
  q?: string; status?: string; priority?: string; category?: string; due?: string; received?: string;
  scope?: "all" | "mine"; page?: number; pageSize?: number;
};

const id = (value: string) => encodeURIComponent(value);

export const api = {
  session: (signal?: AbortSignal) => apiFetch<Session>("/session", { signal }),
  signOut: () => apiFetch<{ redirectUrl?: string }>("/session/sign-out", { method: "POST" }),

  categories: (signal?: AbortSignal) => apiFetch<Category[]>("/reference/categories", { signal }),
  workspaceSummary: (scope: "all" | "mine", signal?: AbortSignal) => apiFetch<WorkspaceSummary>(`/workspace/summary${query({ scope })}`, { signal }),

  complaints: (params: ComplaintQuery, signal?: AbortSignal) => apiFetch<Page<ComplaintSummary>>(`/complaints${query(params)}`, { signal }),
  complaint: (complaintId: string, signal?: AbortSignal) => apiFetch<ComplaintDetail>(`/complaints/${id(complaintId)}`, { signal }),
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
