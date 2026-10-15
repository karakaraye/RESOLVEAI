"use client";

import { FormEvent, ReactNode, useEffect, useRef, useState } from "react";
import { ArrowLeft, CheckCircle2, Send, X } from "lucide-react";
import { api } from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/client";
import type { ComplaintAction, ComplaintDetail, ForwardingOptions, Handoff } from "@/lib/api/types";
import { useNow } from "@/lib/use-now";
import { actionLabels, handoffMeta } from "@/lib/labels";
import { useFormat } from "@/lib/session";
import { zonedWallTimeToIso } from "@/lib/time";
import { useResource } from "@/lib/use-resource";
import { useToast } from "./toast";
import { ErrorNote, ServiceState, SkeletonRows } from "./ui";

type PanelProps = { complaint: ComplaintDetail; onDone: (message?: string) => void; onCancel: () => void };

export function ActionPanel({ action, complaint, onDone, onCancel }: PanelProps & { action: ComplaintAction }) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => { headingRef.current?.focus(); }, [action]);
  const Form = forms[action];
  return (
    <section className="action-panel" aria-labelledby="action-panel-title">
      <div className="action-panel-head">
        <h2 id="action-panel-title" ref={headingRef} tabIndex={-1}>{actionLabels[action]}</h2>
        <button type="button" className="icon-button" aria-label="Close panel" onClick={onCancel}><X size={16} aria-hidden="true" /></button>
      </div>
      <Form complaint={complaint} onDone={onDone} onCancel={onCancel} />
    </section>
  );
}

// One idempotency key per prepared operation: resubmitting after an uncertain failure can never create a duplicate.
const useOperationKey = () => useState(() => crypto.randomUUID())[0];

function useSubmit(run: () => Promise<unknown>, onSuccess: () => void) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    setPending(true); setError(null);
    try { await run(); onSuccess(); }
    catch (e) { setError(e instanceof ApiError ? e : new ApiError("server", "Something went wrong.")); }
    finally { setPending(false); }
  };
  return { pending, error, submit };
}

function Actions({ pending, label, pendingLabel, onCancel, danger, disabled }: { pending: boolean; label: string; pendingLabel: string; onCancel: () => void; danger?: boolean; disabled?: boolean }) {
  return (
    <div className="form-actions">
      <button type="submit" className={`button ${danger ? "button-danger" : "button-primary"}`} disabled={pending || disabled}>{pending ? pendingLabel : label}</button>
      <button type="button" className="button button-ghost" onClick={onCancel} disabled={pending}>Cancel</button>
    </div>
  );
}

function Field({ label, hint, children, htmlFor }: { label: string; hint?: ReactNode; children: ReactNode; htmlFor: string }) {
  return <div className="field"><label htmlFor={htmlFor}>{label}</label>{children}{hint && <p className="field-hint" id={`${htmlFor}-hint`}>{hint}</p>}</div>;
}

const uncertainCopy = "RESOLVEIQ couldn’t confirm whether this was saved. Trying again is safe: it won’t create a duplicate.";
const errorFor = (error: ApiError | null) => (error?.kind === "unreachable" ? uncertainCopy : error);

function AssignForm({ complaint, onDone, onCancel }: PanelProps) {
  const assignees = useResource(`assignees:${complaint.id}`, (signal) => api.eligibleAssignees(complaint.id, signal));
  const [assigneeId, setAssigneeId] = useState("");
  const [reason, setReason] = useState("");
  const key = useOperationKey();
  const chosen = assignees.state === "ready" ? assignees.data.find((a) => a.id === assigneeId) : undefined;
  const { pending, error, submit } = useSubmit(() => api.assign(complaint.id, { assigneeId, reason: reason.trim() || undefined }, key), () => onDone(`Assigned to ${chosen?.displayName}.`));

  if (assignees.state === "loading") return <SkeletonRows rows={3} label="Loading eligible operators" />;
  if (assignees.state === "error") return <ServiceState error={assignees.error} onRetry={assignees.reload} compact />;
  if (!assignees.data.length) return <p className="callout">No eligible operator or team is available for this case. It stays visible in the exception queue and your supervisor has been alerted.</p>;
  return (
    <form onSubmit={submit} className="action-form">
      <p className="muted">Currently: <strong>{complaint.assignedOperator?.displayName ?? "Unassigned"}</strong></p>
      <Field label="Assign to" htmlFor="assignee">
        <select id="assignee" value={assigneeId} onChange={(e) => setAssigneeId(e.target.value)} required>
          <option value="" disabled>Choose an eligible operator</option>
          {assignees.data.map((a) => <option key={a.id} value={a.id} disabled={a.id === complaint.assignedOperator?.id}>{a.displayName}{a.team ? ` · ${a.team}` : ""}{a.openCases !== undefined ? ` · ${a.openCases} open` : ""}</option>)}
        </select>
      </Field>
      <Field label="Reason (optional)" htmlFor="assign-reason" hint="Recorded in the case history.">
        <textarea id="assign-reason" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} />
      </Field>
      <ErrorNote error={errorFor(error)} />
      <Actions pending={pending} label={chosen ? `Assign to ${chosen.displayName}` : "Assign"} pendingLabel="Assigning…" onCancel={onCancel} disabled={!assigneeId} />
    </form>
  );
}

function ForwardForm(props: PanelProps) {
  const options = useResource(`forwarding:${props.complaint.id}`, (signal) => api.forwardingOptions(props.complaint.id, signal));
  if (options.state === "loading") return <SkeletonRows rows={4} label="Loading receiving teams" />;
  if (options.state === "error") return <ServiceState error={options.error} onRetry={options.reload} compact />;
  if (!options.data.teams.length) return <p className="callout">No receiving team is approved for this complaint’s category. It has been placed in the exception queue for your supervisor.</p>;
  return <ForwardComposer {...props} options={options.data} />;
}

function ForwardComposer({ complaint, onDone, onCancel, options }: PanelProps & { options: ForwardingOptions }) {
  const { teams, recommendedTeamId, shareableSummary, sharedFields } = options;
  const [teamId, setTeamId] = useState<string | null>(null);
  const [recipient, setRecipient] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [step, setStep] = useState<"compose" | "review" | "result">("compose");
  const [result, setResult] = useState<Handoff | null>(null);
  const key = useOperationKey();
  const toast = useToast();
  const selectedTeam = teams.find((t) => t.id === (teamId ?? recommendedTeamId));
  const text = message ?? shareableSummary;
  const { pending, error, submit } = useSubmit(async () => {
    const handoff = await api.forward(complaint.id, { teamId: selectedTeam!.id, recipient: recipient || undefined, message: text }, key);
    setResult(handoff); setStep("result");
    if (handoff.state !== "SEND_FAILED") toast(`${handoffMeta[handoff.state].label}: ${selectedTeam!.name}`, "info");
  }, () => {});

  if (step === "result" && result) {
    const failed = result.state === "SEND_FAILED";
    return (
      <div className="action-form">
        <div className={`result-banner${failed ? " failed" : ""}`} role="status">
          {failed ? <X size={18} aria-hidden="true" /> : <CheckCircle2 size={18} aria-hidden="true" />}
          <div><strong>{failed ? "Not forwarded" : `Handoff recorded · ${handoffMeta[result.state].label}`}</strong><p>{handoffMeta[result.state].meaning}</p></div>
        </div>
        {failed && <p className="muted">The case is still open and has been added to the exception queue. You can retry from the handoff history or follow up manually.</p>}
        <div className="form-actions"><button type="button" className="button button-primary" onClick={() => onDone()}>Done</button></div>
      </div>
    );
  }

  if (step === "review" && selectedTeam) {
    return (
      <form onSubmit={submit} className="action-form">
        <p className="muted">Check the destination and what will be shared. Nothing is sent until you confirm.</p>
        <dl className="review-list">
          <div><dt>Receiving team</dt><dd>{selectedTeam.name}</dd></div>
          {recipient && <div><dt>Recipient</dt><dd>{recipient}</dd></div>}
          <div><dt>Sent through</dt><dd>{selectedTeam.channel}</dd></div>
          {selectedTeam.responseDueHours && <div><dt>Response expected within</dt><dd>{selectedTeam.responseDueHours} hours</dd></div>}
          <div><dt>Information shared</dt><dd><ul className="plain-list">{sharedFields.map((f) => <li key={f}>{f}</li>)}</ul></dd></div>
          <div><dt>Message</dt><dd className="pre-wrap">{text}</dd></div>
        </dl>
        <ErrorNote error={errorFor(error)} />
        <div className="form-actions">
          <button type="submit" className="button button-primary" disabled={pending}><Send size={15} aria-hidden="true" />{pending ? "Sending…" : `Send to ${selectedTeam.name}`}</button>
          <button type="button" className="button button-ghost" onClick={() => setStep("compose")} disabled={pending}><ArrowLeft size={15} aria-hidden="true" />Edit</button>
        </div>
      </form>
    );
  }

  return (
    <form className="action-form" onSubmit={(e) => { e.preventDefault(); setStep("review"); }}>
      <Field label="Receiving team" htmlFor="forward-team" hint={recommendedTeamId && selectedTeam?.id === recommendedTeamId ? "Suggested from this complaint’s category and priority." : undefined}>
        <select id="forward-team" value={selectedTeam?.id ?? ""} onChange={(e) => { setTeamId(e.target.value); setRecipient(""); }} required>
          {!selectedTeam && <option value="" disabled>Choose a team</option>}
          {teams.map((t) => <option key={t.id} value={t.id}>{t.name}{t.id === recommendedTeamId ? " (suggested)" : ""}</option>)}
        </select>
      </Field>
      {selectedTeam && selectedTeam.recipients.length > 0 && (
        <Field label="Named recipient (optional)" htmlFor="forward-recipient">
          <select id="forward-recipient" value={recipient} onChange={(e) => setRecipient(e.target.value)}>
            <option value="">Anyone on the team</option>
            {selectedTeam.recipients.map((r) => <option key={r}>{r}</option>)}
          </select>
        </Field>
      )}
      <Field label="Message" htmlFor="forward-message" hint="Customer details are minimised. Only the information listed on the next step is shared.">
        <textarea id="forward-message" rows={5} value={text} onChange={(e) => setMessage(e.target.value)} required maxLength={2000} />
      </Field>
      <div className="form-actions">
        <button type="submit" className="button button-primary" disabled={!selectedTeam || !text.trim()}>Review handoff</button>
        <button type="button" className="button button-ghost" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

function NoteForm({ complaint, onDone, onCancel }: PanelProps) {
  const [text, setText] = useState("");
  const key = useOperationKey();
  const { pending, error, submit } = useSubmit(() => api.addNote(complaint.id, { text: text.trim() }, key), () => onDone("Internal note added."));
  return (
    <form onSubmit={submit} className="action-form">
      <Field label="Internal note" htmlFor="note-text" hint="Visible to RESOLVEIQ staff with access to this case. Never shared with the customer or receiving teams.">
        <textarea id="note-text" rows={4} value={text} onChange={(e) => setText(e.target.value)} required maxLength={4000} />
      </Field>
      <ErrorNote error={errorFor(error)} />
      <Actions pending={pending} label="Add note" pendingLabel="Saving…" onCancel={onCancel} disabled={!text.trim()} />
    </form>
  );
}

function FollowUpForm({ complaint, onDone, onCancel }: PanelProps) {
  const format = useFormat();
  const [when, setWhen] = useState("");
  const [reason, setReason] = useState("");
  const key = useOperationKey();
  const dueAt = when ? zonedWallTimeToIso(when, format.timeZone) : null;
  const now = useNow();
  const past = dueAt !== null && now !== null && Date.parse(dueAt) <= now;
  const { pending, error, submit } = useSubmit(() => api.setFollowUp(complaint.id, { dueAt: dueAt!, reason: reason.trim() }, key), () => onDone(`Follow-up set for ${format.dateTime(dueAt!)}.`));
  return (
    <form onSubmit={submit} className="action-form">
      {complaint.dueAt && <p className="muted">Current due date: <strong>{format.dateTime(complaint.dueAt)}</strong></p>}
      <Field label="Follow up on" htmlFor="follow-when" hint={`Time zone: ${format.timeZone.replaceAll("_", " ")}`}>
        <input id="follow-when" type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} required aria-invalid={past || undefined} />
      </Field>
      {past && <p className="form-error" role="alert">Choose a time in the future.</p>}
      <Field label="Reason" htmlFor="follow-reason">
        <input id="follow-reason" value={reason} onChange={(e) => setReason(e.target.value)} required maxLength={300} placeholder="For example: chase settlement team response" />
      </Field>
      <ErrorNote error={errorFor(error)} />
      <Actions pending={pending} label="Set follow-up" pendingLabel="Saving…" onCancel={onCancel} disabled={!dueAt || past || !reason.trim()} />
    </form>
  );
}

function OutcomeForm({ complaint, onDone, onCancel }: PanelProps) {
  const [outcome, setOutcome] = useState("");
  const [evidence, setEvidence] = useState("");
  const key = useOperationKey();
  const { pending, error, submit } = useSubmit(() => api.recordOutcome(complaint.id, { outcome: outcome.trim(), evidence: evidence.trim() || undefined }, key), () => onDone("Outcome recorded. It is awaiting verification."));
  return (
    <form onSubmit={submit} className="action-form">
      <p className="callout">Recording an outcome does not resolve the case. It moves to <strong>Awaiting verification</strong> until an authorised person verifies it.</p>
      <Field label="Reported outcome" htmlFor="outcome-text">
        <textarea id="outcome-text" rows={3} value={outcome} onChange={(e) => setOutcome(e.target.value)} required maxLength={2000} />
      </Field>
      <Field label="Supporting evidence (optional)" htmlFor="outcome-evidence" hint="For example a reversal reference or the team’s confirmation.">
        <textarea id="outcome-evidence" rows={2} value={evidence} onChange={(e) => setEvidence(e.target.value)} maxLength={2000} />
      </Field>
      <ErrorNote error={errorFor(error)} />
      <Actions pending={pending} label="Record outcome" pendingLabel="Saving…" onCancel={onCancel} disabled={!outcome.trim()} />
    </form>
  );
}

function VerifyForm({ complaint, onDone, onCancel }: PanelProps) {
  const [decision, setDecision] = useState<"VERIFY" | "REJECT" | "">("");
  const [note, setNote] = useState("");
  const key = useOperationKey();
  const { pending, error, submit } = useSubmit(() => api.verifyOutcome(complaint.id, { decision: decision as "VERIFY" | "REJECT", note: note.trim() || undefined }, key),
    () => onDone(decision === "VERIFY" ? "Outcome verified. The case is resolved." : "Outcome rejected. The case stays open."));
  const resolution = complaint.resolution;
  return (
    <form onSubmit={submit} className="action-form">
      {resolution && <div className="quote"><p>{resolution.outcome}</p>{resolution.evidence && <p className="muted">Evidence: {resolution.evidence}</p>}<small className="muted">Reported by {resolution.reportedBy}</small></div>}
      <fieldset className="choice-group">
        <legend>Decision</legend>
        <div className="choice-options stacked">
          <label className="choice"><input type="radio" name="decision" checked={decision === "VERIFY"} onChange={() => setDecision("VERIFY")} /><span><strong>Verify outcome</strong><small>The evidence confirms it. The case becomes resolved.</small></span></label>
          <label className="choice"><input type="radio" name="decision" checked={decision === "REJECT"} onChange={() => setDecision("REJECT")} /><span><strong>Reject outcome</strong><small>Not confirmed. The case stays open.</small></span></label>
        </div>
      </fieldset>
      <Field label={decision === "REJECT" ? "Reason" : "Note (optional)"} htmlFor="verify-note">
        <textarea id="verify-note" rows={2} value={note} onChange={(e) => setNote(e.target.value)} required={decision === "REJECT"} maxLength={1000} />
      </Field>
      <ErrorNote error={errorFor(error)} />
      <Actions pending={pending} label={decision === "REJECT" ? "Reject outcome" : "Verify outcome"} pendingLabel="Saving…" onCancel={onCancel} danger={decision === "REJECT"} disabled={!decision || (decision === "REJECT" && !note.trim())} />
    </form>
  );
}

function ReopenForm({ complaint, onDone, onCancel }: PanelProps) {
  const [reason, setReason] = useState("");
  const key = useOperationKey();
  const { pending, error, submit } = useSubmit(() => api.reopen(complaint.id, { reason: reason.trim() }, key), () => onDone("Case reopened."));
  return (
    <form onSubmit={submit} className="action-form">
      <p className="muted">Reopening removes this case from verified-resolution reporting until it is resolved and verified again.</p>
      <Field label="Reason for reopening" htmlFor="reopen-reason">
        <textarea id="reopen-reason" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} required maxLength={1000} />
      </Field>
      <ErrorNote error={errorFor(error)} />
      <Actions pending={pending} label="Reopen case" pendingLabel="Reopening…" onCancel={onCancel} danger disabled={!reason.trim()} />
    </form>
  );
}

const forms: Record<ComplaintAction, (props: PanelProps) => ReactNode> = {
  ASSIGN: AssignForm,
  FORWARD: ForwardForm,
  ADD_NOTE: NoteForm,
  SET_FOLLOW_UP: FollowUpForm,
  RECORD_OUTCOME: OutcomeForm,
  VERIFY_OUTCOME: VerifyForm,
  REOPEN: ReopenForm,
};

export function RetryHandoffButton({ handoff, onDone }: { handoff: Handoff; onDone: () => void }) {
  const key = useOperationKey();
  const toast = useToast();
  const { pending, error, submit } = useSubmit(async () => {
    const next = await api.retryHandoff(handoff.id, key);
    toast(`Retry recorded · ${handoffMeta[next.state].label}`);
  }, onDone);
  return (
    <div className="retry">
      <button type="button" className="button button-secondary button-small" onClick={() => submit()} disabled={pending}>{pending ? "Retrying…" : "Retry send"}</button>
      <ErrorNote error={errorFor(error)} />
    </div>
  );
}
