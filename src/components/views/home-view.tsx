"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowRight, CheckCircle2, ChevronRight, Plus } from "lucide-react";
import { api } from "@/lib/api/endpoints";
import type { ApiError } from "@/lib/api/client";
import type { ReportType } from "@/lib/api/types";
import { nextActionMeta, nextActionOrder, statusMeta } from "@/lib/labels";
import { useFormat, useSession } from "@/lib/session";
import { useNow } from "@/lib/use-now";
import { useResource } from "@/lib/use-resource";
import { BarList, TrendChart } from "../charts";
import { complaintHref, rowMenuItems } from "../complaint-register";
import { OverflowMenu, PageHeader, PriorityTag, ServiceState, SkeletonBlock, SkeletonRows, StatusBadge } from "../ui";
import { WorkloadStrip, WorkloadStripSkeleton } from "../workload-strip";

const blocking: ApiError["kind"][] = ["not-configured", "unauthorized", "forbidden"];

export function HomeView() {
  const session = useSession();
  const summary = useResource("summary:all", (signal) => api.workspaceSummary("all", signal));
  const format = useFormat();
  const now = useNow();
  const rawFirstName = session.state === "ready" ? session.data.user.displayName.split(/\s+/)[0] : null;
  const greetingName = !rawFirstName || rawFirstName.toLowerCase() === "test" ? "Hackathon" : rawFirstName;
  const hour = now === null ? null : Number(new Intl.DateTimeFormat("en-GB", { hour: "numeric", hourCycle: "h23", timeZone: format.timeZone }).format(now));
  const greeting = hour === null ? "Good afternoon" : hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  const today = now === null ? " " : new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: format.timeZone }).format(now);

  const header = (
    <PageHeader
      eyebrow={today}
      title={`${greeting}, ${greetingName}`}
      description="Here’s what needs your attention."
      actions={
        <Link href="/complaints/new" className="button button-primary">
          <Plus size={16} aria-hidden="true" />
          <span>Log Complaint</span>
        </Link>
      }
    />
  );

  if (summary.state === "error" && blocking.includes(summary.error.kind)) {
    return (
      <>
        {header}
        <section className="panel onboarding">
          <ServiceState error={summary.error} />
          <div className="onboarding-preview" aria-label="What appears here once connected">
            <p className="eyebrow">Once connected, Home shows</p>
            <ol>
              <li><strong>Your workload</strong><span>New, needs-attention, in-progress, overdue and verified-resolved counts, each opening the matching list.</span></li>
              <li><strong>Next actions</strong><span>Work derived from real case states and deadlines, most urgent first.</span></li>
              <li><strong>Recent complaints</strong><span>The latest complaints with a direct way to open each one.</span></li>
              <li><strong>Trends</strong><span>Complaint volume, top issues and case status from verified records only.</span></li>
            </ol>
          </div>
        </section>
      </>
    );
  }

  const counts = summary.state === "ready" ? summary.data.counts : null;
  return (
    <>
      {header}
      {summary.state === "loading" && <WorkloadStripSkeleton count={5} />}
      {summary.state === "error" && <section className="panel"><ServiceState error={summary.error} onRetry={summary.reload} subject="Workload summary" compact /></section>}
      {counts && (
        <WorkloadStrip label="Workload summary" items={[
          { label: "New", value: counts.new, href: "/complaints?status=NEW", tone: "info" },
          { label: "Needs attention", value: counts.needsAttention, href: "/complaints?status=NEEDS_ACTION", tone: "warning" },
          { label: "Overdue", value: counts.overdue, href: "/my-cases?due=overdue", tone: "danger" },
          { label: "In progress", value: counts.inProgress, href: "/complaints?status=IN_PROGRESS" },
          { label: "Verified resolved", value: counts.resolvedVerified, href: "/complaints?status=RESOLVED", hint: counts.awaitingVerification ? `${counts.awaitingVerification} awaiting verification` : undefined },
        ]} />
      )}

      <div className="home-grid">
        <section className="panel" aria-labelledby="next-actions-title">
          <div className="panel-head">
            <h2 id="next-actions-title">Your next actions</h2>
            {summary.state === "ready" && summary.data.nextActions.length > 0 && <span className="count-pill">{summary.data.nextActions.reduce((n, a) => n + a.count, 0)}</span>}
          </div>
          {summary.state === "loading" && <SkeletonRows rows={4} label="Loading next actions" />}
          {summary.state === "ready" && (summary.data.nextActions.length === 0
            ? <div className="all-clear"><CheckCircle2 size={20} aria-hidden="true" /><div><strong>You’re all caught up</strong><p>Nothing needs action right now. New work will appear here as it arrives.</p></div></div>
            : <ul className="action-list">
                {[...summary.data.nextActions].sort((a, b) => nextActionOrder.indexOf(a.kind) - nextActionOrder.indexOf(b.kind)).map((action) => {
                  const meta = nextActionMeta[action.kind];
                  return (
                    <li key={action.kind}>
                      <Link href={meta.href(action.count === 1 ? action.complaintId : undefined)} className="action-row">
                        <span className={`action-mark tone-${meta.tone}`} aria-hidden="true" />
                        <span className="action-text"><strong>{meta.label}</strong><small>{meta.detail}</small></span>
                        <span className="action-count" aria-label={`${action.count} items`}>{action.count}</span>
                        <ChevronRight size={16} aria-hidden="true" />
                      </Link>
                    </li>
                  );
                })}
              </ul>)}
        </section>
        <RecentComplaints />
      </div>

      {summary.state === "ready" && (
        <div className="insight-grid">
          <InsightPanel title="Complaint trend" type="COMPLAINT_VOLUMES" />
          <InsightPanel title="Top issues" type="RECURRING_ISSUES" />
          <InsightPanel title="Cases by status" type="OVERVIEW" />
        </div>
      )}
    </>
  );
}

function RecentComplaints() {
  const recent = useResource("recent", (signal) => api.complaints({ scope: "all", pageSize: 5, page: 1 }, signal));
  const format = useFormat();
  return (
    <section className="panel" aria-labelledby="recent-title">
      <div className="panel-head">
        <h2 id="recent-title">Recent complaints</h2>
        <Link href="/complaints" className="text-link">View all <ArrowRight size={14} aria-hidden="true" /></Link>
      </div>
      {recent.state === "loading" && <SkeletonRows rows={5} label="Loading recent complaints" />}
      {recent.state === "error" && <ServiceState error={recent.error} onRetry={recent.reload} compact />}
      {recent.state === "ready" && (recent.data.items.length === 0
        ? <p className="panel-note">No complaints have been received yet.</p>
        : <ul className="recent-list">
            {recent.data.items.map((item) => (
              <li key={item.id}>
                <Link href={complaintHref(item, "/")} className="recent-main">
                  <span className="recent-top"><strong className="record-ref">{item.reference}</strong><span className="muted">{format.time(item.receivedAt)} · {format.date(item.receivedAt)}</span></span>
                  <span className="recent-issue">{item.summary}</span>
                  <span className="recent-meta"><StatusBadge status={item.status} /><PriorityTag priority={item.priority} />{item.category && <span className="muted">{item.category.label}</span>}</span>
                </Link>
                <OverflowMenu label={`More actions for ${item.reference}`} items={rowMenuItems(item, "/").slice(1)} />
              </li>
            ))}
          </ul>)}
    </section>
  );
}

function InsightPanel({ title, type }: { title: string; type: ReportType }) {
  const [range, setRange] = useState("7d");
  const report = useResource(`home-report:${type}:${range}`, (signal) => api.report(type, { range }, signal));
  const format = useFormat();
  const shortDate = (iso: string) => new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: format.timeZone }).format(new Date(iso));

  return (
    <section className="panel insight" aria-label={title}>
      <div className="panel-head">
        <h2>{title}</h2>
        <label className="compact-select"><span className="sr-only">Period for {title}</span>
          <select value={range} onChange={(e) => setRange(e.target.value)}><option value="7d">Last 7 days</option><option value="30d">Last 30 days</option><option value="90d">Last 90 days</option></select>
        </label>
      </div>
      {report.state === "loading" && <SkeletonBlock height={150} label={`Loading ${title}`} />}
      {report.state === "error" && <p className="panel-note">{report.error.kind === "forbidden" ? "Your role doesn’t include this report." : "Unavailable right now. Case work is not affected."}</p>}
      {report.state === "ready" && (() => {
        const data = report.data;
        const note = !data.coverage.complete && <p className="coverage-note">Partial data{data.coverage.note ? `: ${data.coverage.note}` : ""}</p>;
        if (type === "COMPLAINT_VOLUMES") return data.series?.points.length
          ? <>{note}<TrendChart points={data.series.points} label={data.series.label} formatDate={shortDate} height={150} /></>
          : <p className="panel-note">No complaints in this period.</p>;
        const items = data.rows?.items.slice(0, 5) ?? [];
        if (!items.length) return <p className="panel-note">No data for this period.</p>;
        return <>{note}<BarList valueLabel={data.rows?.valueLabel ?? "complaints"} items={items.map((row) => ({
          label: type === "OVERVIEW" && row.label in statusMeta ? statusMeta[row.label as keyof typeof statusMeta].label : row.label,
          value: row.value,
          href: row.filter ? `/complaints?${row.filter}` : undefined,
        }))} /></>;
      })()}
    </section>
  );
}
