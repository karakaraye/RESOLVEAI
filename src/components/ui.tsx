"use client";

import Link from "next/link";
import { KeyboardEvent, ReactNode, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { AlertTriangle, CloudOff, KeyRound, Lock, MoreHorizontal, PlugZap, RotateCw, SearchX } from "lucide-react";
import { signInUrl, type ApiError } from "@/lib/api/client";
import type { ComplaintStatus, HandoffState, Priority, SourceStatus } from "@/lib/api/types";
import { handoffMeta, priorityMeta, sourceMeta, statusMeta, Tone } from "@/lib/labels";

export function Badge({ tone, children, title }: { tone: Tone; children: ReactNode; title?: string }) {
  return <span className={`badge tone-${tone}`} title={title}><i aria-hidden="true" />{children}</span>;
}

export const StatusBadge = ({ status }: { status: ComplaintStatus }) => <Badge tone={statusMeta[status].tone}>{statusMeta[status].label}</Badge>;
export const HandoffBadge = ({ state }: { state: HandoffState }) => <Badge tone={handoffMeta[state].tone} title={handoffMeta[state].meaning}>{handoffMeta[state].label}</Badge>;
export const SourceBadge = ({ status }: { status: SourceStatus }) => <Badge tone={sourceMeta[status].tone}>{sourceMeta[status].label}</Badge>;
export const OverdueBadge = () => <Badge tone="danger">Overdue</Badge>;

export function PriorityTag({ priority }: { priority: Priority }) {
  const meta = priorityMeta[priority];
  return <span className={`priority tone-${meta.tone}`}><PriorityBars priority={priority} />{meta.label}</span>;
}

function PriorityBars({ priority }: { priority: Priority }) {
  const level = { LOW: 1, MEDIUM: 2, HIGH: 3, CRITICAL: 4 }[priority];
  return <svg className="priority-bars" viewBox="0 0 14 12" aria-hidden="true">{[0, 1, 2, 3].map((i) => <rect key={i} x={i * 3.6} y={9 - i * 3} width="2.6" height={3 + i * 3} rx=".8" className={i < level ? "on" : ""} />)}</svg>;
}

export function PageHeader({ title, description, actions, eyebrow }: { title: string; description?: ReactNode; actions?: ReactNode; eyebrow?: ReactNode }) {
  return (
    <header className="page-header">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {description && <p className="page-description">{description}</p>}
      </div>
      {actions && <div className="page-header-actions">{actions}</div>}
    </header>
  );
}

export function EmptyState({ icon, title, children, action }: { icon?: ReactNode; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty-state">
      {icon && <span className="empty-icon" aria-hidden="true">{icon}</span>}
      <strong>{title}</strong>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

const serviceCopy: Record<ApiError["kind"], { icon: ReactNode; title: string; body: string; retry?: boolean }> = {
  "not-configured": { icon: <PlugZap />, title: "RESOLVEIQ is not connected yet", body: "This workspace has no RESOLVEIQ service address. Your RESOLVEIQ administrator connects it during onboarding; nothing is shown until real records are available." },
  unreachable: { icon: <CloudOff />, title: "RESOLVEIQ can’t be reached", body: "The service did not respond. Your work is safe on the server. Check your connection and try again.", retry: true },
  unauthorized: { icon: <KeyRound />, title: "Sign in to continue", body: "Your session has ended or organisation sign-in is not set up yet. Sign in with your company account to see this page." },
  forbidden: { icon: <Lock />, title: "You don’t have access to this", body: "Your role doesn’t include this page or record. Ask your supervisor or IT administrator if you need access." },
  "not-found": { icon: <SearchX />, title: "Not found", body: "This record doesn’t exist or you don’t have access to it. Check the reference and try again." },
  conflict: { icon: <AlertTriangle />, title: "This record changed", body: "Someone else updated it. Reload to see the latest version.", retry: true },
  validation: { icon: <AlertTriangle />, title: "The request wasn’t accepted", body: "Some details were missing or invalid." },
  server: { icon: <AlertTriangle />, title: "Something went wrong", body: "RESOLVEIQ couldn’t load this. Nothing was changed. Try again in a moment.", retry: true },
};

export function ServiceState({ error, onRetry, compact = false, subject }: { error: ApiError; onRetry?: () => void; compact?: boolean; subject?: string }) {
  const copy = serviceCopy[error.kind];
  return (
    <div className={`service-state${compact ? " compact" : ""}`} role={error.kind === "not-configured" ? undefined : "alert"}>
      <span className="service-icon" aria-hidden="true">{copy.icon}</span>
      <div>
        <strong>{subject && error.kind !== "not-configured" && error.kind !== "unauthorized" ? `${subject}: ${copy.title.toLowerCase()}` : copy.title}</strong>
        <p>{copy.body}</p>
        {error.kind === "unauthorized" && <a className="button button-primary button-small" href={signInUrl()}>Sign in</a>}
        {copy.retry && onRetry && <button type="button" className="button button-secondary button-small" onClick={onRetry}><RotateCw size={14} aria-hidden="true" />Try again</button>}
      </div>
    </div>
  );
}

export function ErrorNote({ error }: { error: ApiError | string | null }) {
  if (!error) return null;
  const message = typeof error === "string" ? error : error.kind === "validation" || error.kind === "conflict" ? error.message : `${serviceCopy[error.kind].title}. ${error.kind === "unreachable" ? "Nothing was saved." : ""}`;
  return <p className="form-error" role="alert"><AlertTriangle size={14} aria-hidden="true" />{message}</p>;
}

export function SkeletonRows({ rows = 6, label = "Loading" }: { rows?: number; label?: string }) {
  return (
    <div className="skeleton-rows" role="status" aria-label={label}>
      {Array.from({ length: rows }, (_, i) => <span key={i} className="skeleton-row"><i /><i /><i /><i /></span>)}
    </div>
  );
}

export function SkeletonBlock({ height = 120, label = "Loading" }: { height?: number; label?: string }) {
  return <div className="skeleton-block" style={{ height }} role="status" aria-label={label} />;
}

export type MenuItem = { label: string; href?: string; onSelect?: () => void; icon?: ReactNode; tone?: "danger" };

export function OverflowMenu({ label, items }: { label: string; items: MenuItem[] }) {
  const [open, setOpen] = useState(false);
  const [up, setUp] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuId = useId();

  // Activity keeps hidden routes mounted; never come back to a menu left open.
  useLayoutEffect(() => () => setOpen(false), []);

  useEffect(() => {
    if (!open) return;
    menuRef.current?.querySelector<HTMLElement>("[role=menuitem]")?.focus();
    const close = (event: PointerEvent) => {
      if (event.target instanceof Node && !menuRef.current?.contains(event.target) && !triggerRef.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);

  const toggle = () => {
    const rect = triggerRef.current?.getBoundingClientRect();
    setUp(Boolean(rect && window.innerHeight - rect.bottom < 48 + items.length * 40));
    setOpen((value) => !value);
  };

  const onKeyDown = (event: KeyboardEvent) => {
    const entries = [...(menuRef.current?.querySelectorAll<HTMLElement>("[role=menuitem]") ?? [])];
    const index = entries.indexOf(document.activeElement as HTMLElement);
    if (event.key === "Escape") { event.preventDefault(); setOpen(false); triggerRef.current?.focus(); }
    else if (event.key === "ArrowDown") { event.preventDefault(); entries[(index + 1) % entries.length]?.focus(); }
    else if (event.key === "ArrowUp") { event.preventDefault(); entries[(index - 1 + entries.length) % entries.length]?.focus(); }
    else if (event.key === "Home") { event.preventDefault(); entries[0]?.focus(); }
    else if (event.key === "End") { event.preventDefault(); entries.at(-1)?.focus(); }
    else if (event.key === "Tab") setOpen(false);
  };

  if (!items.length) return null;
  return (
    <div className="menu-anchor">
      <button ref={triggerRef} type="button" className="icon-button" aria-label={label} aria-haspopup="menu" aria-expanded={open} aria-controls={open ? menuId : undefined} onClick={toggle}>
        <MoreHorizontal size={18} aria-hidden="true" />
      </button>
      {open && (
        <div ref={menuRef} id={menuId} role="menu" aria-label={label} className={`menu${up ? " menu-up" : ""}`} onKeyDown={onKeyDown}>
          {items.map((item) => item.href
            ? <Link key={item.label} role="menuitem" tabIndex={-1} href={item.href} className={item.tone === "danger" ? "danger" : undefined} onClick={() => setOpen(false)}>{item.icon}{item.label}</Link>
            : <button key={item.label} role="menuitem" tabIndex={-1} type="button" className={item.tone === "danger" ? "danger" : undefined} onClick={() => { setOpen(false); item.onSelect?.(); }}>{item.icon}{item.label}</button>)}
        </div>
      )}
    </div>
  );
}

export function Pagination({ page, pageSize, total, noun, onPage, onPageSize }: { page: number; pageSize: number; total: number; noun: string; onPage: (page: number) => void; onPageSize: (size: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const first = total ? (page - 1) * pageSize + 1 : 0;
  return (
    <div className="pagination">
      <span>{first}–{Math.min(page * pageSize, total)} of {total.toLocaleString("en-GB")} {noun}</span>
      {total > 25 && (
        <div className="pagination-controls">
          <label>Rows <select value={pageSize} onChange={(e) => onPageSize(Number(e.target.value))}><option value={25}>25</option><option value={50}>50</option></select></label>
          <button type="button" className="button button-secondary button-small" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</button>
          <span aria-live="polite">Page {page} of {pages}</span>
          <button type="button" className="button button-secondary button-small" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next</button>
        </div>
      )}
    </div>
  );
}
