"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ReactNode, useEffect, useRef, useState } from "react";
import { AlertTriangle, ArrowLeft, ChevronRight, CircleDashed, Link2, Sparkles } from "lucide-react";
import { api } from "@/lib/api/endpoints";
import type { ComplaintAction, ComplaintDetail } from "@/lib/api/types";
import { actionFromParam, actionLabels, actionOrder, actionParam, handoffMeta } from "@/lib/labels";
import { useFormat } from "@/lib/session";
import { useResource } from "@/lib/use-resource";
import { safeReturnPath, useUrlState } from "@/lib/use-url-state";
import { ActionPanel, RetryHandoffButton } from "../complaint-actions";
import { useToast } from "../toast";
import { Badge, HandoffBadge, OverdueBadge, PriorityTag, ServiceState, SkeletonBlock, SourceBadge, StatusBadge } from "../ui";

const backLabels: Record<string, string> = { "/complaints": "Complaints", "/my-cases": "My cases", "/forwarded": "Forwarded", "/": "Home", "/notifications": "Notifications" };

export function ComplaintDetailView() {
  const { id } = useParams<{ id: string }>();
  const { params, set } = useUrlState();
  const complaint = useResource(`complaint:${id}`, (signal) => api.complaint(id, signal));
  const from = safeReturnPath(params.get("from"));
  const back = from ?? "/complaints";
  const backLabel = backLabels[back.split("?")[0]] ?? "Back";

  return (
    <>
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link href={back}><ArrowLeft size={15} aria-hidden="true" />{backLabel}</Link>
        {complaint.state === "ready" && <><ChevronRight size={14} aria-hidden="true" /><span aria-current="page">{complaint.data.reference}</span></>}
      </nav>
      {complaint.state === "loading" && <div className="detail-loading"><SkeletonBlock height={96} label="Loading complaint" /><div className="detail-layout"><SkeletonBlock height={320} label="Loading complaint" /><SkeletonBlock height={220} label="Loading complaint" /></div></div>}
      {complaint.state === "error" && <section className="panel"><ServiceState error={complaint.error} onRetry={complaint.reload} /></section>}
      {complaint.state === "ready" && <Detail complaint={complaint.data} reload={complaint.reload} action={actionFromParam(params.get("action"))} setAction={(a) => set({ action: a ? actionParam(a) : null })} />}
    </>
  );
}

function Detail({ complaint, reload, action, setAction }: { complaint: ComplaintDetail; reload: () => void; action?: ComplaintAction; setAction: (action: ComplaintAction | null) => void }) {
  const format = useFormat();
  const toast = useToast();
  const scrolled = useRef(false);
  const allowed = actionOrder.filter((a) => complaint.allowedActions.includes(a));
  const activeAction = action && allowed.includes(action) ? action : undefined;
  const primary = recommendedAction(complaint, allowed);

  useEffect(() => {
    document.title = `${complaint.reference} · RESOLVEIQ`;
    if (scrolled.current || !window.location.hash) return;
    scrolled.current = true;
    document.getElementById(window.location.hash.slice(1))?.scrollIntoView({ block: "start" });
  }, [complaint.reference]);

  // A link that asked for an action this record no longer allows should say so instead of silently ignoring it.
  useEffect(() => {
    if (!action || activeAction) return;
    toast(`${actionLabels[action]} isn’t available for this case in its current state.`);
    setAction(null);
    // setAction changes identity with the URL; the guard above stops repeats.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [action, activeAction, toast]);

  const done = (message?: string) => {
    if (message) toast(message, "success");
    setAction(null);
    reload();
  };

  return (
    <>
      <header className="detail-header">
        <p className="eyebrow">{complaint.reference} · Received {format.dateTime(complaint.receivedAt)} · {complaint.sourceChannel}</p>
        <h1>{complaint.summary}</h1>
        <div className="detail-badges">
          <StatusBadge status={complaint.status} />
          <PriorityTag priority={complaint.priority} />
          {complaint.overdue && <OverdueBadge />}
          {complaint.category && <span className="tag">{complaint.category.label}</span>}
        </div>
        <dl className="key-facts">
          <div><dt>Assigned operator</dt><dd>{complaint.assignedOperator?.displayName ?? <span className="muted">Unassigned</span>}</dd></div>
          <div><dt>Due</dt><dd className={complaint.overdue ? "text-danger" : undefined}>{complaint.dueAt ? format.dateTime(complaint.dueAt) : <span className="muted">No due date</span>}</dd></div>
          <div><dt>Customer</dt><dd className="mono">{complaint.customerReference}</dd></div>
          <div><dt>Source reference</dt><dd className="mono">{complaint.sourceReference}</dd></div>
        </dl>
      </header>

      <div className="detail-layout">
        <div className="detail-main">
          <Section id="overview" title="What happened" aside={<SourceFreshness complaint={complaint} />}>
            <p className="narrative">{complaint.narrative}</p>
            {complaint.reopenReason && <p className="callout"><strong>Reopened:</strong> {complaint.reopenReason}</p>}
          </Section>

          <Section id="evidence" title="Evidence and investigation">
            {complaint.transactions.length === 0
              ? <p className="muted">No transaction record is linked. RESOLVEIQ doesn’t infer a transaction result from the complaint text.</p>
              : <ul className="evidence-list">
                  {complaint.transactions.map((t) => (
                    <li key={t.reference}>
                      <div className="evidence-top"><strong className="mono">{t.reference}</strong><SourceBadge status={t.status} /></div>
                      <dl className="inline-facts">
                        <div><dt>Source</dt><dd>{t.sourceSystem}</dd></div>
                        {t.amount && <div><dt>Amount</dt><dd className="mono">{t.amount.currency} {t.amount.value}</dd></div>}
                        {t.occurredAt && <div><dt>Occurred</dt><dd>{format.dateTime(t.occurredAt)}</dd></div>}
                        <div><dt>Reported status</dt><dd>{t.statusLabel ?? <span className="muted">Not reported</span>}</dd></div>
                        <div><dt>Last updated</dt><dd>{t.lastUpdatedAt ? format.dateTime(t.lastUpdatedAt) : <span className="muted">Unknown</span>}</dd></div>
                      </dl>
                      {t.conflict && <p className="warning-note"><AlertTriangle size={14} aria-hidden="true" />Sources disagree: {t.conflict}. No final outcome is assumed.</p>}
                      {t.matchEvidence && <p className="muted small">Matched because: {t.matchEvidence}</p>}
                    </li>
                  ))}
                </ul>}
            {complaint.related.length > 0 && (
              <>
                <h3 className="subhead">Related records</h3>
                <ul className="related-list">
                  {complaint.related.map((r) => (
                    <li key={r.id}>
                      <Link2 size={14} aria-hidden="true" />
                      {r.kind === "COMPLAINT" ? <Link href={`/complaints/${encodeURIComponent(r.id)}`} className="record-link">{r.reference}</Link> : <strong>{r.reference}</strong>}
                      <span>{r.title}</span><span className="muted">{r.relation}</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </Section>

          <Section id="findings" title="RESOLVEIQ findings" aside={<FindingAvailability complaint={complaint} />}>
            <Findings complaint={complaint} />
          </Section>

          <Section id="handoffs" title="Handoffs">
            {complaint.handoffs.length === 0
              ? <p className="muted">This complaint hasn’t been forwarded.</p>
              : <ol className="handoff-list">
                  {complaint.handoffs.map((h) => (
                    <li key={h.id}>
                      <div className="handoff-top">
                        <strong>{h.team.name}</strong>{h.recipient && <span className="muted">· {h.recipient}</span>}
                        <HandoffBadge state={h.state} />
                      </div>
                      <p className="muted small">{handoffMeta[h.state].meaning}</p>
                      <dl className="inline-facts">
                        <div><dt>Forwarded</dt><dd>{format.dateTime(h.createdAt)} by {h.createdBy}</dd></div>
                        <div><dt>Channel</dt><dd>{h.channel}</dd></div>
                        <div><dt>Last update</dt><dd>{format.dateTime(h.lastUpdatedAt)}</dd></div>
                        {h.responseDueAt && <div><dt>Response due</dt><dd>{format.dateTime(h.responseDueAt)}</dd></div>}
                      </dl>
                      {h.response && <div className="quote"><p>{h.response.summary}</p><small className="muted">Response recorded {format.dateTime(h.response.receivedAt)}</small></div>}
                      {h.attempts.length > 0 && (
                        <details className="attempts">
                          <summary>Delivery attempts ({h.attempts.length})</summary>
                          <ol>{h.attempts.map((a, i) => <li key={i}><span>{format.dateTime(a.at)}</span><span>{a.channel}</span><span>{a.outcome}</span></li>)}</ol>
                        </details>
                      )}
                      {h.retryAllowed && <RetryHandoffButton handoff={h} onDone={reload} />}
                    </li>
                  ))}
                </ol>}
          </Section>

          <Section id="resolution" title="Resolution">
            {!complaint.resolution
              ? <p className="muted">No outcome has been reported.</p>
              : <div className="resolution">
                  <Badge tone={complaint.resolution.verification === "VERIFIED" ? "success" : complaint.resolution.verification === "REJECTED" ? "danger" : "verify"}>
                    {complaint.resolution.verification === "VERIFIED" ? "Verified" : complaint.resolution.verification === "REJECTED" ? "Rejected" : "Awaiting verification"}
                  </Badge>
                  <p>{complaint.resolution.outcome}</p>
                  {complaint.resolution.evidence && <p className="muted">Evidence: {complaint.resolution.evidence}</p>}
                  <p className="muted small">
                    Reported {format.dateTime(complaint.resolution.reportedAt)} by {complaint.resolution.reportedBy}
                    {complaint.resolution.verifiedAt && ` · ${complaint.resolution.verification === "REJECTED" ? "Rejected" : "Verified"} ${format.dateTime(complaint.resolution.verifiedAt)} by ${complaint.resolution.verifiedBy}`}
                  </p>
                  {complaint.resolution.verification === "AWAITING" && <p className="small">Not counted as resolved until verified.</p>}
                </div>}
          </Section>

          <Section id="notes" title="Internal notes">
            {complaint.notes.length === 0
              ? <p className="muted">No notes yet.</p>
              : <ul className="note-list">{complaint.notes.map((n) => <li key={n.id}><div className="note-meta"><strong>{n.author}</strong><span className="muted">{format.dateTime(n.createdAt)}</span></div><p>{n.text}</p></li>)}</ul>}
            {allowed.includes("ADD_NOTE") && activeAction !== "ADD_NOTE" && <button type="button" className="button button-ghost button-small" onClick={() => setAction("ADD_NOTE")}>Add note</button>}
          </Section>

          <Section id="communications" title="Customer communications">
            <CustomerCommunications complaintId={complaint.id} />
          </Section>

          <Section id="timeline" title="Timeline">
            {complaint.timeline.length === 0
              ? <p className="muted">No activity recorded.</p>
              : <ol className="timeline">
                  {[...complaint.timeline].sort((a, b) => b.at.localeCompare(a.at)).map((event) => (
                    <li key={event.id}>
                      <span className="timeline-dot" aria-hidden="true" />
                      <div><strong>{event.title}</strong>{event.detail && <p>{event.detail}</p>}<span className="muted small">{format.dateTime(event.at)}{event.actor ? ` · ${event.actor}` : ""}</span></div>
                    </li>
                  ))}
                </ol>}
          </Section>
        </div>

        <aside className="detail-rail" aria-label="Case actions">
          {activeAction
            ? <ActionPanel key={activeAction} action={activeAction} complaint={complaint} onDone={done} onCancel={() => setAction(null)} />
            : <>
                <section className="rail-card next-step">
                  <p className="eyebrow">Next step</p>
                  <h2>{primary ? nextStepCopy[primary] : complaint.status === "RESOLVED" ? "Resolved and verified" : "No action available"}</h2>
                  <p className="muted">{complaint.findings.recommendedNextStep ?? (primary ? "Based on this case’s current state." : complaint.status === "RESOLVED" ? "Nothing else is needed unless the customer comes back." : "Your role doesn’t allow changes to this case.")}</p>
                  {primary && <button type="button" className="button button-primary button-block" onClick={() => setAction(primary)}>{actionLabels[primary]}</button>}
                </section>
                {allowed.filter((a) => a !== primary).length > 0 && (
                  <section className="rail-card">
                    <h2 className="rail-title">Other actions</h2>
                    <ul className="rail-actions">
                      {allowed.filter((a) => a !== primary).map((a) => (
                        <li key={a}><button type="button" className={a === "REOPEN" ? "danger" : undefined} onClick={() => setAction(a)}>{actionLabels[a]}<ChevronRight size={15} aria-hidden="true" /></button></li>
                      ))}
                    </ul>
                  </section>
                )}
                <nav className="rail-card rail-index" aria-label="On this page">
                  {[["overview", "What happened"], ["evidence", "Evidence"], ["findings", "Findings"], ["handoffs", `Handoffs${complaint.handoffs.length ? ` (${complaint.handoffs.length})` : ""}`], ["resolution", "Resolution"], ["notes", `Notes${complaint.notes.length ? ` (${complaint.notes.length})` : ""}`], ["communications", "Communications"], ["timeline", "Timeline"]].map(([id, label]) => (
                    <a key={id} href={`#${id}`}>{label}</a>
                  ))}
                </nav>
              </>}
        </aside>
      </div>
    </>
  );
}

const nextStepCopy: Record<ComplaintAction, string> = {
  ASSIGN: "Assign an operator",
  FORWARD: "Forward to the right team",
  ADD_NOTE: "Record what you found",
  SET_FOLLOW_UP: "Set a follow-up",
  RECORD_OUTCOME: "Record the outcome",
  VERIFY_OUTCOME: "Verify the reported outcome",
  REOPEN: "Reopen if the customer returns",
};

function recommendedAction(complaint: ComplaintDetail, allowed: ComplaintAction[]): ComplaintAction | undefined {
  const pick = (...candidates: ComplaintAction[]) => candidates.find((c) => allowed.includes(c));
  if (complaint.status === "RESOLVED") return undefined;
  if (complaint.status === "AWAITING_VERIFICATION") return pick("VERIFY_OUTCOME", "ADD_NOTE");
  if (!complaint.assignedOperator) return pick("ASSIGN", "FORWARD", "ADD_NOTE");
  if (complaint.status === "FORWARDED") return pick("SET_FOLLOW_UP", "RECORD_OUTCOME", "ADD_NOTE");
  if (complaint.status === "NEEDS_ACTION" || complaint.status === "NEW") return pick("FORWARD", "RECORD_OUTCOME", "ADD_NOTE");
  return pick("RECORD_OUTCOME", "SET_FOLLOW_UP", "ADD_NOTE");
}

function Section({ id, title, aside, children }: { id: string; title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section id={id} className="detail-section" aria-labelledby={`${id}-title`}>
      <div className="section-head"><h2 id={`${id}-title`}>{title}</h2>{aside}</div>
      {children}
    </section>
  );
}

function SourceFreshness({ complaint }: { complaint: ComplaintDetail }) {
  const format = useFormat();
  return <span className="freshness"><SourceBadge status={complaint.source.status} /><span className="muted small">{complaint.source.name}{complaint.source.lastUpdatedAt ? ` · ${format.dateTime(complaint.source.lastUpdatedAt)}` : ""}</span></span>;
}

function FindingAvailability({ complaint }: { complaint: ComplaintDetail }) {
  const f = complaint.findings;
  if (f.availability === "UNAVAILABLE") return <Badge tone="neutral">Unavailable</Badge>;
  if (f.availability === "LOW_CONFIDENCE") return <Badge tone="warning">Low confidence</Badge>;
  return f.confidence !== undefined ? <Badge tone="accent">{Math.round(f.confidence * 100)}% confidence</Badge> : null;
}

function Findings({ complaint }: { complaint: ComplaintDetail }) {
  const f = complaint.findings;
  if (f.availability === "UNAVAILABLE") {
    return <p className="muted"><CircleDashed size={14} aria-hidden="true" className="inline-icon" />Automated findings aren’t available for this complaint. Review the evidence above manually; every case action still works.</p>;
  }
  return (
    <div className="findings">
      {f.availability === "LOW_CONFIDENCE" && <p className="warning-note"><AlertTriangle size={14} aria-hidden="true" />RESOLVEIQ isn’t confident about these findings. Treat them as leads, not conclusions.</p>}
      <dl className="inline-facts">
        {f.category && <div><dt>Suggested category</dt><dd>{f.category}</dd></div>}
        {f.possibleCause && <div><dt>Possible cause</dt><dd>{f.possibleCause}</dd></div>}
      </dl>
      {f.facts.length > 0 && <div className="finding-group"><h3><span className="finding-kind fact">Confirmed</span>Facts from source records</h3><ul>{f.facts.map((x) => <li key={x}>{x}</li>)}</ul></div>}
      {f.hypotheses.length > 0 && <div className="finding-group"><h3><span className="finding-kind hypothesis"><Sparkles size={12} aria-hidden="true" />Hypothesis</span>Not yet confirmed</h3><ul>{f.hypotheses.map((x) => <li key={x}>{x}</li>)}</ul></div>}
      {f.evidence.length > 0 && <details className="attempts"><summary>Supporting evidence ({f.evidence.length})</summary><ul>{f.evidence.map((x) => <li key={x}>{x}</li>)}</ul></details>}
    </div>
  );
}

function CustomerCommunications({ complaintId }: { complaintId: string }) {
  const format = useFormat();
  const toast = useToast();
  const comms = useResource(`comms:${complaintId}`, (signal) => api.communications(complaintId, signal));
  const [retryingId, setRetryingId] = useState<string | null>(null);

  const handleRetry = async (commId: string) => {
    setRetryingId(commId);
    try {
      await api.retryCommunication(commId, crypto.randomUUID());
      toast("Communication queued for retry dispatch.", "success");
      comms.reload();
    } catch (err: unknown) {
      toast(err instanceof Error ? err.message : "Failed to retry communication.", "info");
    } finally {
      setRetryingId(null);
    }
  };

  if (comms.state === "loading") {
    return <p className="muted small">Loading communications...</p>;
  }

  if (comms.state === "error") {
    return <p className="muted small">Failed to load communications.</p>;
  }

  const items = comms.data?.items ?? [];
  if (items.length === 0) {
    return <p className="muted">No customer communications have been issued for this case.</p>;
  }

  const toneForStatus = (status: string): "success" | "accent" | "warning" | "danger" | "neutral" => {
    if (status === "DELIVERED") return "success";
    if (status === "SENT") return "accent";
    if (status === "DELIVERY_UNCONFIRMED") return "warning";
    if (status === "FAILED") return "danger";
    return "neutral";
  };

  return (
    <div className="communications-list">
      <ul className="evidence-list">
        {items.map((item) => (
          <li key={item.id}>
            <div className="evidence-top">
              <strong>{item.category_label} · <span className="mono">{item.channel}</span></strong>
              <Badge tone={toneForStatus(item.status)}>{item.status}</Badge>
            </div>
            <dl className="inline-facts">
              <div><dt>Recipient</dt><dd className="mono">{item.masked_destination}</dd></div>
              <div><dt>Queued</dt><dd>{format.dateTime(item.queued_at)}</dd></div>
              {item.delivered_at && <div><dt>Delivered</dt><dd>{format.dateTime(item.delivered_at)}</dd></div>}
              {item.cancelled_at && <div><dt>Cancelled</dt><dd>{format.dateTime(item.cancelled_at)}</dd></div>}
              {item.provider && <div><dt>Provider</dt><dd>{item.provider}</dd></div>}
              {item.verification_reference && <div><dt>Verification Ref</dt><dd className="mono">{item.verification_reference}</dd></div>}
            </dl>
            {item.subject && <p className="small"><strong>Subject:</strong> {item.subject}</p>}
            <div className="quote">
              <p style={{ whiteSpace: "pre-wrap" }}>{item.rendered_content}</p>
            </div>
            {item.cancellation_reason && (
              <p className="warning-note">
                <AlertTriangle size={14} aria-hidden="true" />
                Suppressed: {item.cancellation_reason}
              </p>
            )}
            {item.error_message && (
              <p className="text-danger small">
                Error: {item.error_message}
              </p>
            )}
            {item.status === "FAILED" && (
              <button
                type="button"
                className="button button-ghost button-small"
                disabled={retryingId === item.id}
                onClick={() => handleRetry(item.id)}
              >
                {retryingId === item.id ? "Retrying..." : "Retry delivery"}
              </button>
            )}
            {item.delivery_attempts && item.delivery_attempts.length > 0 && (
              <details className="attempts">
                <summary>Delivery attempts ({item.delivery_attempts.length})</summary>
                <ol>
                  {item.delivery_attempts.map((att) => (
                    <li key={att.id}>
                      <span>{format.dateTime(att.attempted_at)}</span>
                      <span>{att.channel}</span>
                      <span>{att.status} ({att.latency_ms}ms)</span>
                      {att.error_detail && <span className="text-danger">{att.error_detail}</span>}
                    </li>
                  ))}
                </ol>
              </details>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
