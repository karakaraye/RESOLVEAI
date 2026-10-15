"use client";

import Link from "next/link";
import { Inbox, SearchX, X } from "lucide-react";
import { api, ComplaintQuery } from "@/lib/api/endpoints";
import type { ComplaintSummary } from "@/lib/api/types";
import { actionLabels, actionOrder, actionParam, priorityMeta, priorityOrder, statusMeta, statusOrder } from "@/lib/labels";
import { useFormat } from "@/lib/session";
import { useResource } from "@/lib/use-resource";
import { useUrlState } from "@/lib/use-url-state";
import { EmptyState, OverdueBadge, OverflowMenu, Pagination, PriorityTag, ServiceState, SkeletonRows, StatusBadge } from "./ui";

const receivedOptions = [{ value: "today", label: "Today" }, { value: "7d", label: "Last 7 days" }, { value: "30d", label: "Last 30 days" }, { value: "90d", label: "Last 90 days" }];
const dueOptions = [{ value: "overdue", label: "Overdue" }, { value: "today", label: "Due today" }, { value: "soon", label: "Due within 24 hours" }, { value: "week", label: "Due this week" }, { value: "none", label: "No due date" }];

export function complaintHref(item: Pick<ComplaintSummary, "id">, from?: string, action?: string) {
  const params = new URLSearchParams();
  if (action) params.set("action", action);
  if (from) params.set("from", from);
  const text = params.toString();
  return `/complaints/${encodeURIComponent(item.id)}${text ? `?${text}` : ""}`;
}

export function rowMenuItems(item: ComplaintSummary, from?: string) {
  return [
    { label: "View complaint", href: complaintHref(item, from) },
    ...actionOrder.filter((action) => item.allowedActions.includes(action)).map((action) => ({
      label: actionLabels[action], href: complaintHref(item, from, actionParam(action)), tone: action === "REOPEN" ? "danger" as const : undefined,
    })),
  ];
}

export function ComplaintRegister({ scope, searchLabel }: { scope: "all" | "mine"; searchLabel: string }) {
  const { params, set, here } = useUrlState();
  const format = useFormat();
  const query: ComplaintQuery = {
    scope,
    q: params.get("q") ?? undefined,
    status: params.get("status") ?? undefined,
    priority: params.get("priority") ?? undefined,
    category: params.get("category") ?? undefined,
    due: params.get("due") ?? undefined,
    received: scope === "all" ? params.get("received") ?? undefined : undefined,
    page: Number(params.get("page")) || 1,
    pageSize: Number(params.get("pageSize")) === 50 ? 50 : 25,
  };
  const key = JSON.stringify(query);
  const complaints = useResource(`complaints:${key}`, (signal) => api.complaints(query, signal));
  const categories = useResource("categories", api.categories);
  const filtered = Boolean(query.q || query.status || query.priority || query.category || query.due || query.received);
  const clear = () => set({ q: null, status: null, priority: null, category: null, due: null, received: null });

  if (complaints.state === "error" && !filtered && ["not-configured", "unauthorized", "forbidden"].includes(complaints.error.kind)) {
    return <section className="panel"><ServiceState error={complaints.error} onRetry={complaints.reload} /></section>;
  }

  return (
    <section className="panel register" aria-label={scope === "mine" ? "Cases assigned to you" : "Complaints"}>
      <div className="filters" role="group" aria-label="Filter complaints">
        <SearchField value={query.q ?? ""} label={searchLabel} onCommit={(q) => set({ q })} />
        <Select label="Status" value={query.status} onChange={(status) => set({ status })} allLabel="All statuses" options={statusOrder.map((s) => ({ value: s, label: statusMeta[s].label }))} />
        <Select label="Category" value={query.category} onChange={(category) => set({ category })} allLabel="All categories"
          options={categories.state === "ready" ? categories.data.map((c) => ({ value: c.code, label: c.label })) : query.category ? [{ value: query.category, label: query.category }] : []} />
        <Select label="Priority" value={query.priority} onChange={(priority) => set({ priority })} allLabel="All priorities" options={priorityOrder.map((p) => ({ value: p, label: priorityMeta[p].label }))} />
        {scope === "mine"
          ? <Select label="Due date" value={query.due} onChange={(due) => set({ due })} allLabel="Any due date" options={dueOptions} />
          : <Select label="Received" value={query.received} onChange={(received) => set({ received })} allLabel="Any time" options={receivedOptions} />}
        {filtered && <button type="button" className="button button-ghost button-small clear-filters" onClick={clear}><X size={14} aria-hidden="true" />Clear</button>}
      </div>

      {complaints.state === "loading" && <SkeletonRows label="Loading complaints" />}
      {complaints.state === "error" && <ServiceState error={complaints.error} onRetry={complaints.reload} compact />}
      {complaints.state === "ready" && (complaints.data.items.length === 0
        ? filtered
          ? <EmptyState icon={<SearchX />} title="No complaints match these filters" action={<button type="button" className="button button-secondary button-small" onClick={clear}>Clear filters</button>}>Try a different search, or widen the status, category or date.</EmptyState>
          : <EmptyState icon={<Inbox />} title={scope === "mine" ? "Nothing is assigned to you" : "No complaints yet"}>
              {scope === "mine" ? "Cases assigned to you for review, investigation or follow-up will appear here." : "Complaints arrive here from your bank’s approved channels as soon as they are received."}
            </EmptyState>
        : <>
            <p className="sr-only" role="status">{complaints.data.total} complaints found</p>
            <div className="table-wrap">
              <table className="register-table">
                <thead>
                  <tr>
                    {scope === "mine" && <th scope="col">Assigned</th>}
                    <th scope="col">Reference</th>
                    <th scope="col">Customer</th>
                    <th scope="col" className="col-issue">Issue</th>
                    <th scope="col">Category</th>
                    <th scope="col">Priority</th>
                    <th scope="col">Status</th>
                    <th scope="col">{scope === "mine" ? "Due" : "Assigned operator"}</th>
                    <th scope="col"><span className="sr-only">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {complaints.data.items.map((item) => (
                    <tr key={item.id}>
                      {scope === "mine" && <td data-label="Assigned" className="nowrap muted">{format.dateTime(item.assignedAt)}</td>}
                      <td data-label="Reference" className="nowrap">
                        <Link className="record-link" href={complaintHref(item, here)}>{item.reference}</Link>
                        {scope === "all" && <span className="cell-sub">{format.dateTime(item.receivedAt)}</span>}
                      </td>
                      <td data-label="Customer" className="mono">{item.customerReference}</td>
                      <td data-label="Issue" className="col-issue">{item.summary}</td>
                      <td data-label="Category">{item.category?.label ?? <span className="muted">Unclassified</span>}</td>
                      <td data-label="Priority"><PriorityTag priority={item.priority} /></td>
                      <td data-label="Status"><span className="badge-stack"><StatusBadge status={item.status} />{item.overdue && <OverdueBadge />}</span></td>
                      {scope === "mine"
                        ? <td data-label="Due" className={`nowrap${item.overdue ? " text-danger" : ""}`}>{item.dueAt ? format.dateTime(item.dueAt) : <span className="muted">No due date</span>}</td>
                        : <td data-label="Assigned operator">{item.assignedOperator?.displayName ?? <span className="muted">Unassigned</span>}</td>}
                      <td className="row-actions">
                        <Link className="button button-secondary button-small" href={complaintHref(item, here)} aria-label={`View complaint ${item.reference}`}>View</Link>
                        <OverflowMenu label={`More actions for ${item.reference}`} items={rowMenuItems(item, here).slice(1)} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={query.page ?? 1} pageSize={query.pageSize ?? 25} total={complaints.data.total} noun={scope === "mine" ? "cases" : "complaints"}
              onPage={(page) => set({ page }, { resetPage: false })} onPageSize={(pageSize) => set({ pageSize: pageSize === 25 ? null : pageSize })} />
          </>)}
    </section>
  );
}

export function Select({ label, value, onChange, options, allLabel }: { label: string; value?: string; onChange: (value: string | null) => void; options: { value: string; label: string }[]; allLabel: string }) {
  return (
    <label className={`select-field${value ? " has-value" : ""}`}>
      <span>{label}</span>
      <select value={value ?? ""} onChange={(e) => onChange(e.target.value || null)}>
        <option value="">{allLabel}</option>
        {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
    </label>
  );
}

// Commits on Enter or blur so typing doesn't fire a request per keystroke; the URL stays the single source of truth.
export function SearchField({ value, label, onCommit }: { value: string; label: string; onCommit: (value: string | null) => void }) {
  return (
    <form className="search-field" role="search" onSubmit={(e) => { e.preventDefault(); onCommit(new FormData(e.currentTarget).get("q")?.toString().trim() || null); }}>
      <label className="sr-only" htmlFor={`search-${label}`}>{label}</label>
      <input key={value} id={`search-${label}`} name="q" type="search" defaultValue={value} placeholder={label} enterKeyHint="search"
        onBlur={(e) => { const next = e.currentTarget.value.trim(); if (next !== value) onCommit(next || null); }} />
    </form>
  );
}
