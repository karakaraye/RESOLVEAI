"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Bell, CheckCheck } from "lucide-react";
import { api } from "@/lib/api/endpoints";
import type { ApiError } from "@/lib/api/client";
import type { NotificationItem } from "@/lib/api/types";
import { useFormat } from "@/lib/session";
import { useResource } from "@/lib/use-resource";
import { useUrlState } from "@/lib/use-url-state";
import { useToast } from "../toast";
import { EmptyState, ErrorNote, PageHeader, Pagination, ServiceState, SkeletonRows } from "../ui";

export function NotificationsView() {
  const { params, set } = useUrlState();
  const unreadOnly = params.get("filter") === "unread";
  const page = Number(params.get("page")) || 1;
  const pageSize = Number(params.get("pageSize")) === 50 ? 50 : 25;
  const notifications = useResource(`notifications:${unreadOnly}:${page}:${pageSize}`, (signal) => api.notifications({ unread: unreadOnly, page, pageSize }, signal));
  const format = useFormat();
  const router = useRouter();
  const toast = useToast();
  const [error, setError] = useState<ApiError | null>(null);
  const [marking, setMarking] = useState(false);
  const unread = notifications.state === "ready" ? notifications.data.unreadCount : 0;

  const markAll = async () => {
    setMarking(true); setError(null);
    try { await api.markAllNotificationsRead(); notifications.reload(); toast("All notifications marked as read.", "success"); }
    catch (e) { setError(e as ApiError); }
    finally { setMarking(false); }
  };

  const open = async (item: NotificationItem) => {
    if (!item.read) await api.markNotificationRead(item.id).catch(() => { /* opening the record matters more than the read flag */ });
    if (item.complaint) router.push(`/complaints/${encodeURIComponent(item.complaint.id)}`);
    else notifications.reload();
  };

  const blocked = notifications.state === "error" && ["not-configured", "unauthorized", "forbidden"].includes(notifications.error.kind);
  return (
    <>
      <PageHeader title="Notifications" description="Assignments, team responses, deadlines and case changes."
        actions={unread > 0 && <button type="button" className="button button-secondary" onClick={markAll} disabled={marking}><CheckCheck size={16} aria-hidden="true" />{marking ? "Marking…" : "Mark all as read"}</button>} />
      <section className="panel" aria-label="Notifications">
        {!blocked && (
          <div className="panel-head">
            <div className="segmented" role="group" aria-label="Show">
              <Link href="/notifications" aria-current={!unreadOnly ? "true" : undefined} scroll={false}>All</Link>
              <Link href="/notifications?filter=unread" aria-current={unreadOnly ? "true" : undefined} scroll={false}>Unread{unread ? ` (${unread})` : ""}</Link>
            </div>
          </div>
        )}
        <ErrorNote error={error} />
        {notifications.state === "loading" && <SkeletonRows rows={5} label="Loading notifications" />}
        {notifications.state === "error" && <ServiceState error={notifications.error} onRetry={notifications.reload} />}
        {notifications.state === "ready" && (notifications.data.items.length === 0
          ? <EmptyState icon={<Bell />} title={unreadOnly ? "No unread notifications" : "No notifications yet"}>
              {unreadOnly ? "You’ve read everything." : "You’ll be notified about assignments, team responses, approaching deadlines and reopened cases."}
            </EmptyState>
          : <>
              <ul className="notification-list">
                {notifications.data.items.map((item) => (
                  <li key={item.id} className={item.read ? "" : "unread"}>
                    <button type="button" onClick={() => open(item)}>
                      <span className="unread-marker" aria-hidden="true" />
                      <span className="notification-body">
                        <strong>{item.title}</strong>
                        <span className="muted">{item.complaint ? `${item.complaint.reference} · ` : ""}{format.dateTime(item.occurredAt)}</span>
                      </span>
                      <span className="sr-only">{item.read ? "Read" : "Unread"}</span>
                    </button>
                  </li>
                ))}
              </ul>
              <Pagination page={page} pageSize={pageSize} total={notifications.data.total} noun="notifications"
                onPage={(p) => set({ page: p }, { resetPage: false })} onPageSize={(size) => set({ pageSize: size === 25 ? null : size })} />
            </>)}
      </section>
    </>
  );
}
