"use client";

import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api/endpoints";
import type { ReportMetric, ReportType } from "@/lib/api/types";
import { dateRanges, reportTypes } from "@/lib/labels";
import { useFormat } from "@/lib/session";
import { useResource } from "@/lib/use-resource";
import { useUrlState } from "@/lib/use-url-state";
import { BarList, TrendChart } from "../charts";
import { PageHeader, ServiceState, SkeletonBlock, SourceBadge } from "../ui";

const isDate = (value: string | null): value is string => Boolean(value && /^\d{4}-\d{2}-\d{2}$/.test(value));

export function ReportsView() {
  const { params, set } = useUrlState();
  const type = (reportTypes.find((r) => r.type === params.get("type"))?.type ?? "OVERVIEW") as ReportType;
  const range = dateRanges.some((r) => r.value === params.get("range")) ? params.get("range")! : "30d";
  const from = params.get("from");
  const to = params.get("to");
  const [draft, setDraft] = useState({ from: from ?? "", to: to ?? "" });
  const rangeError = (start: string | null, end: string | null) =>
    !isDate(start) || !isDate(end) ? "Choose a start and end date, then apply." : start > end ? "The start date must be on or before the end date." : null;
  const customError = range === "custom" ? rangeError(from, to) : null;
  const draftError = rangeError(draft.from, draft.to);
  // Show the draft's problem while editing; otherwise the applied range's.
  const shownError = range === "custom" ? (draft.from && draft.to ? draftError : customError) : null;
  const meta = reportTypes.find((r) => r.type === type)!;
  const ready = range !== "custom" || !customError;
  const report = useResource(ready ? `report:${type}:${range}:${from}:${to}` : null, (signal) => api.report(type, range === "custom" ? { range, from: from!, to: to! } : { range }, signal));
  const format = useFormat();
  const shortDate = (iso: string) => new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: format.timeZone }).format(new Date(iso));

  return (
    <>
      <PageHeader title="Reports" description="One question at a time, answered from verified records." />
      <section className="panel report-controls" aria-label="Report options">
        <label className="select-field wide">
          <span>Report</span>
          <select value={type} onChange={(e) => set({ type: e.target.value === "OVERVIEW" ? null : e.target.value })}>
            {reportTypes.map((r) => <option key={r.type} value={r.type}>{r.label}</option>)}
          </select>
        </label>
        <label className="select-field">
          <span>Date range</span>
          <select value={range} onChange={(e) => set({ range: e.target.value === "30d" ? null : e.target.value, ...(e.target.value === "custom" ? {} : { from: null, to: null }) })}>
            {dateRanges.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
          </select>
        </label>
        {range === "custom" && (
          <form className="custom-range" onSubmit={(e) => { e.preventDefault(); if (!draftError) set({ from: draft.from, to: draft.to }); }}>
            <label className="select-field"><span>From</span><input type="date" value={draft.from} onChange={(e) => setDraft({ ...draft, from: e.target.value })} aria-invalid={Boolean(draftError && draft.from && draft.to) || undefined} /></label>
            <label className="select-field"><span>To</span><input type="date" value={draft.to} onChange={(e) => setDraft({ ...draft, to: e.target.value })} aria-invalid={Boolean(draftError && draft.from && draft.to) || undefined} /></label>
            <button type="submit" className="button button-secondary" disabled={Boolean(draftError) || (draft.from === from && draft.to === to)}>Apply</button>
          </form>
        )}
      </section>

      <section className="panel report" aria-labelledby="report-title">
        <div className="report-head">
          <div>
            <p className="eyebrow">{range === "custom" && !customError ? `${format.date(from!)} to ${format.date(to!)}` : dateRanges.find((r) => r.value === range)!.label}</p>
            <h2 id="report-title">{meta.label}</h2>
            <p className="muted">{meta.question}</p>
          </div>
        </div>

        {shownError && <p className="form-error" role="alert">{shownError}</p>}
        {report.state === "loading" && ready && <div className="report-body"><SkeletonBlock height={72} label="Loading report" /><SkeletonBlock height={220} label="Loading report" /></div>}
        {report.state === "error" && <ServiceState error={report.error} onRetry={report.reload} />}
        {report.state === "ready" && (
          <div className="report-body">
            {!report.data.coverage.complete && (
              <p className="coverage-note" role="note"><strong>Partial data.</strong> {report.data.coverage.note ?? "Some sources were unavailable or stale for this period, so figures may be incomplete."}</p>
            )}
            {report.data.metrics.length > 0 && (
              <ul className="metric-row" aria-label="Key figures">
                {report.data.metrics.map((metric) => <li key={metric.key}><Metric metric={metric} /></li>)}
              </ul>
            )}
            {report.data.series && (report.data.series.points.length
              ? <TrendChart points={report.data.series.points} label={report.data.series.label} formatDate={shortDate} height={240} />
              : <p className="panel-note">No records in this period.</p>)}
            {report.data.rows && (
              <div className="report-rows">
                <h3>{report.data.rows.heading}</h3>
                {report.data.rows.items.length
                  ? <BarList valueLabel={report.data.rows.valueLabel} items={report.data.rows.items.map((row) => ({ label: row.label, value: row.value, secondary: row.secondary, href: row.filter ? `/complaints?${row.filter}` : undefined }))} />
                  : <p className="panel-note">No records in this period.</p>}
              </div>
            )}
            <div className="report-foot">
              <div>
                <h3>Data sources</h3>
                {report.data.coverage.sources.length
                  ? <ul className="source-list">{report.data.coverage.sources.map((s) => <li key={s.name}><span>{s.name}</span><SourceBadge status={s.status} /><span className="muted">{s.lastUpdatedAt ? `Updated ${format.dateTime(s.lastUpdatedAt)}` : "Last update unknown"}</span></li>)}</ul>
                  : <p className="muted">No source information was provided.</p>}
              </div>
              {report.data.definitions.length > 0 && (
                <div>
                  <h3>Definitions</h3>
                  <dl className="definitions">{report.data.definitions.map((d) => <div key={d.term}><dt>{d.term}</dt><dd>{d.meaning}</dd></div>)}</dl>
                </div>
              )}
            </div>
            <p className="muted small">Generated {format.dateTime(report.data.generatedAt)} · Reported resolutions count only once verified.</p>
          </div>
        )}
      </section>
    </>
  );
}

function Metric({ metric }: { metric: ReportMetric }) {
  const value = metric.value == null ? "Not available" : metric.unit === "hours" ? `${metric.value.toLocaleString("en-GB", { maximumFractionDigits: 1 })} h` : metric.unit === "percent" ? `${metric.value.toLocaleString("en-GB", { maximumFractionDigits: 1 })}%` : metric.value.toLocaleString("en-GB");
  const body = <><span className="metric-label">{metric.label}</span><span className={`metric-value${metric.value == null ? " unavailable" : ""}`}>{value}</span></>;
  return metric.filter && metric.value != null
    ? <Link className="metric" href={`/complaints?${metric.filter}`}>{body}</Link>
    : <div className="metric">{body}</div>;
}
