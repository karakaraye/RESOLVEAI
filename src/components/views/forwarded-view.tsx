"use client";

import Link from "next/link";
import { Send, SearchX, X } from "lucide-react";
import { api } from "@/lib/api/endpoints";
import { handoffMeta, handoffOrder } from "@/lib/labels";
import { useFormat } from "@/lib/session";
import { useResource } from "@/lib/use-resource";
import { useUrlState } from "@/lib/use-url-state";
import { complaintHref, SearchField, Select } from "../complaint-register";
import { EmptyState, HandoffBadge, Pagination, PageHeader, ServiceState, SkeletonRows } from "../ui";
import { WorkloadStrip } from "../workload-strip";

export function ForwardedView() {
  const { params, set, here } = useUrlState();
  const format = useFormat();
  const query = { q: params.get("q") ?? undefined, state: params.get("state") ?? undefined, page: Number(params.get("page")) || 1, pageSize: Number(params.get("pageSize")) === 50 ? 50 : 25 };
  const handoffs = useResource(`handoffs:${JSON.stringify(query)}`, (signal) => api.handoffs(query, signal));
  const counts = useResource("handoff-counts", api.handoffCounts);
  const filtered = Boolean(query.q || query.state);
  const clear = () => set({ q: null, state: null });

  const header = <PageHeader title="Forwarded" description="Complaints you sent to other bank teams, and what happened next." />;
  if (handoffs.state === "error" && !filtered && ["not-configured", "unauthorized", "forbidden"].includes(handoffs.error.kind)) {
    return <>{header}<section className="panel"><ServiceState error={handoffs.error} /></section></>;
  }

  return (
    <>
      {header}
      {counts.state === "ready" && (
        <WorkloadStrip label="Handoff summary" items={[
          { label: "Total forwarded", value: counts.data.total, href: "/forwarded", current: !query.state },
          { label: "Awaiting response", value: counts.data.awaitingResponse, href: "/forwarded?state=AWAITING_RESPONSE", tone: "warning", current: query.state === "AWAITING_RESPONSE" },
          { label: "Overdue", value: counts.data.overdue, href: "/forwarded?state=OVERDUE", tone: "danger", current: query.state === "OVERDUE" },
          { label: "Send failed", value: counts.data.failed, href: "/forwarded?state=SEND_FAILED", tone: "danger", current: query.state === "SEND_FAILED" },
          { label: "Responded", value: counts.data.responded, href: "/forwarded?state=RESPONDED", current: query.state === "RESPONDED" },
        ]} />
      )}
      <section className="panel register" aria-label="Forwarded complaints">
        <div className="filters" role="group" aria-label="Filter handoffs">
          <SearchField value={query.q ?? ""} label="Search by reference, customer or team" onCommit={(q) => set({ q })} />
          <Select label="Handoff state" value={query.state} onChange={(state) => set({ state })} allLabel="All states" options={handoffOrder.map((s) => ({ value: s, label: handoffMeta[s].label }))} />
          {filtered && <button type="button" className="button button-ghost button-small clear-filters" onClick={clear}><X size={14} aria-hidden="true" />Clear</button>}
        </div>
        {handoffs.state === "loading" && <SkeletonRows label="Loading handoffs" />}
        {handoffs.state === "error" && <ServiceState error={handoffs.error} onRetry={handoffs.reload} compact />}
        {handoffs.state === "ready" && (handoffs.data.items.length === 0
          ? filtered
            ? <EmptyState icon={<SearchX />} title="No handoffs match" action={<button type="button" className="button button-secondary button-small" onClick={clear}>Clear filters</button>}>Try another search or state.</EmptyState>
            : <EmptyState icon={<Send />} title="Nothing has been forwarded yet">When you forward a complaint to a bank team, its delivery, acknowledgement and response are tracked here. Use <strong>Forward to team</strong> on any complaint.</EmptyState>
          : <>
              <div className="table-wrap">
                <table className="register-table">
                  <thead><tr>
                    <th scope="col">Complaint</th><th scope="col">Forwarded</th><th scope="col">Customer</th><th scope="col" className="col-issue">Issue</th>
                    <th scope="col">Receiving team</th><th scope="col">Handoff state</th><th scope="col">Last update</th><th scope="col"><span className="sr-only">Actions</span></th>
                  </tr></thead>
                  <tbody>
                    {handoffs.data.items.map((handoff) => (
                      <tr key={handoff.id}>
                        <td data-label="Complaint" className="nowrap"><Link className="record-link" href={complaintHref(handoff.complaint, here)}>{handoff.complaint.reference}</Link></td>
                        <td data-label="Forwarded" className="nowrap muted">{format.dateTime(handoff.createdAt)}</td>
                        <td data-label="Customer" className="mono">{handoff.complaint.customerReference}</td>
                        <td data-label="Issue" className="col-issue">{handoff.complaint.summary}</td>
                        <td data-label="Receiving team">{handoff.team.name}{handoff.recipient && <span className="cell-sub">{handoff.recipient}</span>}</td>
                        <td data-label="Handoff state"><HandoffBadge state={handoff.state} />{handoff.responseDueAt && !handoff.response && <span className="cell-sub">Response due {format.dateTime(handoff.responseDueAt)}</span>}</td>
                        <td data-label="Last update" className="nowrap muted">{format.dateTime(handoff.lastUpdatedAt)}</td>
                        <td className="row-actions"><Link className="button button-secondary button-small" href={`${complaintHref(handoff.complaint, here)}#handoffs`} aria-label={`View handoff history for ${handoff.complaint.reference}`}>History</Link></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination page={query.page} pageSize={query.pageSize} total={handoffs.data.total} noun="handoffs"
                onPage={(page) => set({ page }, { resetPage: false })} onPageSize={(pageSize) => set({ pageSize: pageSize === 25 ? null : pageSize })} />
            </>)}
      </section>
    </>
  );
}
