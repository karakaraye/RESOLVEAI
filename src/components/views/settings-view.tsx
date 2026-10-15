"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { BellRing, CircleHelp, Database, Lock, Shield, SlidersHorizontal, UserRound } from "lucide-react";
import { api } from "@/lib/api/endpoints";
import type { ApiError } from "@/lib/api/client";
import type { NotificationPreference } from "@/lib/api/types";
import { handoffMeta, handoffOrder } from "@/lib/labels";
import { Preferences, setPreference, usePreferences } from "@/lib/preferences";
import { useFormat, useSession } from "@/lib/session";
import { useResource } from "@/lib/use-resource";
import { useUrlState } from "@/lib/use-url-state";
import { useToast } from "../toast";
import { Badge, EmptyState, ErrorNote, PageHeader, ServiceState, SkeletonRows, SourceBadge } from "../ui";

const sections = [
  { id: "profile", label: "Profile", icon: UserRound },
  { id: "notifications", label: "Notifications", icon: BellRing },
  { id: "preferences", label: "Preferences", icon: SlidersHorizontal },
  { id: "security", label: "Security & session", icon: Shield },
  { id: "data-sources", label: "Data sources", icon: Database },
  { id: "help", label: "Help & support", icon: CircleHelp },
] as const;

export function SettingsView() {
  const { params } = useUrlState();
  const active = sections.find((s) => s.id === params.get("section")) ?? sections[0];

  return (
    <>
      <PageHeader title="Settings" description="Your account, alerts and display preferences." />
      <div className="settings-layout">
        <nav className="settings-nav" aria-label="Settings sections">
          {sections.map((s) => (
            <Link key={s.id} href={`/settings?section=${s.id}`} aria-current={s.id === active.id ? "page" : undefined} scroll={false} replace>
              <s.icon size={17} aria-hidden="true" />{s.label}
            </Link>
          ))}
        </nav>
        <section className="panel settings-panel" aria-labelledby="settings-title">
          <h2 id="settings-title">{active.label}</h2>
          {active.id === "profile" && <ProfileSection />}
          {active.id === "notifications" && <NotificationSection />}
          {active.id === "preferences" && <PreferencesSection />}
          {active.id === "security" && <SecuritySection />}
          {active.id === "data-sources" && <DataSourcesSection />}
          {active.id === "help" && <HelpSection />}
        </section>
      </div>
    </>
  );
}

function ManagedField({ label, value }: { label: string; value?: string }) {
  return (
    <div className="field-row">
      <dt>{label}</dt>
      <dd>{value || <span className="muted">Not provided</span>}<span className="managed" title="Managed by your organisation"><Lock size={12} aria-hidden="true" /><span className="sr-only">Managed by your organisation</span></span></dd>
    </div>
  );
}

function ProfileSection() {
  const session = useSession();
  if (session.state === "loading") return <SkeletonRows rows={4} label="Loading profile" />;
  if (session.state === "error") return <ServiceState error={session.error} onRetry={session.reload} />;
  const { user, tenant } = session.data;
  return (
    <>
      <p className="section-intro">These details come from your company account. To change them, contact your organisation’s IT administrator.</p>
      <dl className="field-list">
        <ManagedField label="Name" value={user.displayName} />
        <ManagedField label="Company email" value={user.email} />
        <ManagedField label="Department" value={user.department} />
        <ManagedField label="Role" value={user.roleLabel} />
        <ManagedField label="Organisation" value={tenant.name} />
      </dl>
    </>
  );
}

function NotificationSection() {
  const preferences = useResource("notification-preferences", api.notificationPreferences);
  const [draft, setDraft] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const toast = useToast();

  if (preferences.state === "loading") return <SkeletonRows rows={4} label="Loading notification preferences" />;
  if (preferences.state === "error") return <ServiceState error={preferences.error} onRetry={preferences.reload} />;

  const value = (p: NotificationPreference) => draft[p.key] ?? p.enabled;
  const dirty = preferences.data.some((p) => value(p) !== p.enabled);
  const save = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true); setError(null);
    try {
      await api.saveNotificationPreferences(preferences.data.map((p) => ({ key: p.key, enabled: value(p) })));
      setDraft({}); preferences.reload(); toast("Notification preferences saved.", "success");
    } catch (e) { setError(e as ApiError); }
    finally { setSaving(false); }
  };

  if (!preferences.data.length) return <EmptyState title="No notification types are configured">Your organisation hasn’t enabled any notification categories yet.</EmptyState>;
  return (
    <form onSubmit={save}>
      <p className="section-intro">Choose which events alert you inside RESOLVEIQ. Alerts never show more detail than your role allows.</p>
      <ul className="toggle-list">
        {preferences.data.map((p) => (
          <li key={p.key}>
            <label>
              <span><strong>{p.label}</strong><small>{p.description}</small></span>
              <input type="checkbox" role="switch" className="switch" checked={value(p)} onChange={(e) => setDraft({ ...draft, [p.key]: e.target.checked })} />
            </label>
          </li>
        ))}
      </ul>
      <ErrorNote error={error} />
      <div className="form-actions">
        <button type="submit" className="button button-primary" disabled={!dirty || saving}>{saving ? "Saving…" : "Save preferences"}</button>
        {dirty && <button type="button" className="button button-ghost" onClick={() => setDraft({})}>Discard changes</button>}
        {!dirty && <span className="muted">All changes saved</span>}
      </div>
    </form>
  );
}

function Choice<K extends keyof Preferences>({ name, label, value, options }: { name: K; label: string; value: Preferences[K]; options: { value: Preferences[K]; label: string; hint?: string }[] }) {
  return (
    <fieldset className="choice-group">
      <legend>{label}</legend>
      <div className="choice-options">
        {options.map((option) => (
          <label key={String(option.value)} className="choice">
            <input type="radio" name={name} checked={value === option.value} onChange={() => setPreference(name, option.value)} />
            <span><strong>{option.label}</strong>{option.hint && <small>{option.hint}</small>}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function PreferencesSection() {
  const prefs = usePreferences();
  const format = useFormat();
  const sample = "2026-03-10T14:05:00Z";
  return (
    <>
      <p className="section-intro">These apply to this browser only and take effect immediately.</p>
      <Choice name="theme" label="Appearance" value={prefs.theme} options={[{ value: "system", label: "Match system" }, { value: "light", label: "Light" }, { value: "dark", label: "Dark" }]} />
      <Choice name="dateStyle" label="Date format" value={prefs.dateStyle} options={[{ value: "day-month", label: "10 Mar 2026" }, { value: "iso", label: "2026-03-10" }]} />
      <Choice name="hourCycle" label="Time format" value={prefs.hourCycle} options={[{ value: "h23", label: "24-hour", hint: "14:05" }, { value: "h12", label: "12-hour", hint: "2:05 pm" }]} />
      <p className="muted small">Example: {format.dateTime(sample)} · Times show in {format.timeZone.replaceAll("_", " ")}.</p>
    </>
  );
}

function SecuritySection() {
  const session = useSession();
  const format = useFormat();
  if (session.state === "loading") return <SkeletonRows rows={3} label="Loading session" />;
  if (session.state === "error") return <ServiceState error={session.error} onRetry={session.reload} />;
  const s = session.data.session;
  return (
    <>
      <p className="section-intro">You sign in with your company account. Passwords, multi-factor authentication and access policies are managed by your organisation, not by RESOLVEIQ.</p>
      <dl className="field-list">
        <ManagedField label="Sign-in provider" value={s.identityProvider} />
        <ManagedField label="Signed in" value={format.dateTime(s.signedInAt)} />
        <ManagedField label="Session ends" value={s.expiresAt ? format.dateTime(s.expiresAt) : "Set by your organisation’s policy"} />
      </dl>
      <p className="callout">
        {s.signOutAffectsOtherSessions === true && "Signing out also ends your other RESOLVEIQ sessions on this company account."}
        {s.signOutAffectsOtherSessions === false && "Signing out ends this browser’s session only. Other devices stay signed in."}
        {s.signOutAffectsOtherSessions === undefined && "Whether signing out ends other sessions depends on your organisation’s sign-in policy."}
      </p>
    </>
  );
}

function DataSourcesSection() {
  const sources = useResource("data-sources", api.dataSources);
  const format = useFormat();
  if (sources.state === "loading") return <SkeletonRows rows={4} label="Loading data sources" />;
  if (sources.state === "error") return <ServiceState error={sources.error} onRetry={sources.reload} />;
  return (
    <>
      <p className="section-intro">Systems RESOLVEIQ reads from for your organisation. Connections are set up and monitored by the RESOLVEIQ technical team; contact them through your administrator if something looks wrong.</p>
      {sources.data.length === 0
        ? <EmptyState icon={<Database />} title="No data sources connected">Approved complaint, transaction and team sources will be listed here with their health and last update time.</EmptyState>
        : <ul className="source-table">
            {sources.data.map((source) => (
              <li key={source.id}>
                <span><strong>{source.name}</strong><small>{source.kind}</small></span>
                <SourceBadge status={source.status} />
                <span className="muted">{source.lastUpdatedAt ? `Updated ${format.dateTime(source.lastUpdatedAt)}` : "Last update unknown"}</span>
                {source.note && <span className="source-note">{source.note}</span>}
              </li>
            ))}
          </ul>}
    </>
  );
}

function HelpSection() {
  const session = useSession();
  const support = session.state === "ready" ? session.data.tenant.support : undefined;
  return (
    <>
      <div className="support-card">
        <CircleHelp size={20} aria-hidden="true" />
        {support
          ? <div><strong>{support.label}</strong><p>{support.contact}{support.hours ? ` · ${support.hours}` : ""}</p></div>
          : <div><strong>Your organisation’s support contact</strong><p>For account access or workflow questions, contact your supervisor or RESOLVEIQ administrator. Their contact details appear here once your organisation adds them.</p></div>}
      </div>
      <h3 className="subhead">Keyboard</h3>
      <dl className="shortcut-list">
        <div><dt><kbd>/</kbd></dt><dd>Search complaints from anywhere</dd></div>
        <div><dt><kbd>Esc</kbd></dt><dd>Close a menu or panel</dd></div>
        <div><dt><kbd>↑</kbd> <kbd>↓</kbd></dt><dd>Move through an open menu</dd></div>
      </dl>
      <h3 className="subhead">What handoff states mean</h3>
      <dl className="glossary">
        {handoffOrder.map((state) => <div key={state}><dt><Badge tone={handoffMeta[state].tone}>{handoffMeta[state].label}</Badge></dt><dd>{handoffMeta[state].meaning}</dd></div>)}
      </dl>
      <h3 className="subhead">Reported vs verified</h3>
      <p className="section-intro">A <strong>reported outcome</strong> is what someone says happened. A case only counts as <strong>resolved</strong> once an authorised person verifies it. Until then it shows as <em>Awaiting verification</em> and is not counted in resolution reports.</p>
    </>
  );
}
