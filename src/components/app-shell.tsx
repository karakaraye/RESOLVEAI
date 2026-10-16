"use client";

import Link from "next/link";
import { usePathname, useRouter, useSelectedLayoutSegment } from "next/navigation";
import { FormEvent, ReactNode, Suspense, useEffect, useLayoutEffect, useRef, useState } from "react";
import { ArrowUpRight, Bell, BriefcaseBusiness, ChevronDown, FileBarChart2, Home, Inbox, Laptop, LogIn, LogOut, Moon, PanelLeftClose, PanelLeftOpen, Plus, PlusCircle, Search, Send, Settings, Sun, X } from "lucide-react";
import { BrandMark } from "./brand-mark";
import { ToastProvider, useToast } from "./toast";
import { api } from "@/lib/api/endpoints";
import { ApiError, signInUrl } from "@/lib/api/client";
import { setPreference, usePreferences } from "@/lib/preferences";
import { SessionProvider, useFormat, useSession } from "@/lib/session";
import { useResource } from "@/lib/use-resource";

const mainNav = [
  { segment: null, href: "/", label: "Home", icon: Home },
  { segment: "complaints", href: "/complaints", label: "Complaints", icon: Inbox },
  { segment: "my-cases", href: "/my-cases", label: "My Cases", icon: BriefcaseBusiness },
  { segment: "forwarded", href: "/forwarded", label: "Forwarded", icon: Send },
  { segment: "reports", href: "/reports", label: "Reports", icon: FileBarChart2 },
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <SessionProvider>
      <ToastProvider>
        <Shell>{children}</Shell>
      </ToastProvider>
    </SessionProvider>
  );
}

function Shell({ children }: { children: ReactNode }) {
  const { sidebarCollapsed, theme } = usePreferences();

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  return (
    <div className={`app${sidebarCollapsed ? " sidebar-collapsed" : ""}`}>
      <a className="skip-link" href="#main">Skip to content</a>
      <aside className="sidebar" aria-label="Main navigation">
        <Link className="brand" href="/" aria-label="RESOLVEIQ home">
          <BrandMark size={34} />
          <span className="brand-text"><strong>RESOLVEIQ</strong><small>Incident &amp; resolution desk</small></span>
        </Link>
        <div className="sidebar-action-wrap">
          <Link
            href="/complaints/new"
            className="sidebar-new-btn button button-primary"
            title={sidebarCollapsed ? "Log new complaint" : undefined}
          >
            <Plus size={16} aria-hidden="true" />
            <span className="sidebar-new-text">New Complaint</span>
          </Link>
        </div>
        <Suspense fallback={<NavList active={undefined} collapsed={sidebarCollapsed} />}>
          <ActiveNav collapsed={sidebarCollapsed} />
        </Suspense>
        <div className="sidebar-footer">
          <button type="button" className="nav-link sidebar-toggle" aria-pressed={sidebarCollapsed} onClick={() => setPreference("sidebarCollapsed", !sidebarCollapsed)} title={sidebarCollapsed ? "Expand navigation" : undefined}>
            {sidebarCollapsed ? <PanelLeftOpen size={18} aria-hidden="true" /> : <PanelLeftClose size={18} aria-hidden="true" />}
            <span className="nav-label">{sidebarCollapsed ? "Expand navigation" : "Collapse"}</span>
          </button>
        </div>
      </aside>

      <header className="topbar">
        <Link className="brand brand-compact" href="/" aria-label="RESOLVEIQ home"><BrandMark size={28} /><strong>RESOLVEIQ</strong></Link>
        <GlobalSearch />
        <div className="topbar-actions">
          <Link
            href="/complaints/new"
            className="button button-primary button-small topbar-new-btn"
            title="Log new complaint for live hackathon demo"
          >
            <Plus size={15} aria-hidden="true" />
            <span className="topbar-new-label">New Complaint</span>
          </Link>
          <ThemeToggle />
          <NotificationsMenu />
          <AccountMenu />
        </div>
      </header>

      <main id="main" className="main" tabIndex={-1}>{children}</main>

      <Suspense fallback={null}>
        <MobileNav />
      </Suspense>
    </div>
  );
}

function ActiveNav({ collapsed }: { collapsed: boolean }) {
  const segment = useSelectedLayoutSegment();
  return <NavList active={segment} collapsed={collapsed} />;
}

function NavList({ active, collapsed }: { active: string | null | undefined; collapsed: boolean }) {
  return (
    <nav className="nav">
      <ul>
        {mainNav.map((item) => (
          <li key={item.href}>
            <Link href={item.href} className="nav-link" aria-current={active !== undefined && active === item.segment ? "page" : undefined} title={collapsed ? item.label : undefined}>
              <item.icon size={18} aria-hidden="true" /><span className="nav-label">{item.label}</span>
            </Link>
          </li>
        ))}
      </ul>
      <ul className="nav-secondary">
        <li>
          <Link href="/settings" className="nav-link" aria-current={active === "settings" ? "page" : undefined} title={collapsed ? "Settings" : undefined}>
            <Settings size={18} aria-hidden="true" /><span className="nav-label">Settings</span>
          </Link>
        </li>
        <li><SignOutButton className="nav-link" collapsed={collapsed} /></li>
      </ul>
    </nav>
  );
}

const mobileNavItems = [
  { href: "/", label: "Home", mobileLabel: "Home", icon: Home },
  { href: "/complaints", label: "Complaints", mobileLabel: "Cases", icon: Inbox },
  { href: "/complaints/new", label: "New Complaint", mobileLabel: "+ New", icon: PlusCircle },
  { href: "/my-cases", label: "My Cases", mobileLabel: "Mine", icon: BriefcaseBusiness },
  { href: "/reports", label: "Reports", mobileLabel: "Reports", icon: FileBarChart2 },
  { href: "/settings", label: "Settings", mobileLabel: "Settings", icon: Settings },
] as const;

function MobileNav() {
  const pathname = usePathname();
  return (
    <nav className="mobile-nav" aria-label="Main navigation">
      {mobileNavItems.map((item) => {
        const isActive =
          item.href === "/"
            ? pathname === "/"
            : item.href === "/complaints"
            ? pathname === "/complaints"
            : pathname.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={isActive ? "page" : undefined}
            title={item.label}
            aria-label={item.label}
          >
            <item.icon size={18} aria-hidden="true" />
            <span>{item.mobileLabel}</span>
          </Link>
        );
      })}
    </nav>
  );
}

function GlobalSearch() {
  const router = useRouter();
  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const focusSearch = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (event.key === "/" && !event.metaKey && !event.ctrlKey && !target.closest("input, textarea, select, [contenteditable=true]")) {
        event.preventDefault();
        inputRef.current?.focus();
      }
    };
    document.addEventListener("keydown", focusSearch);
    return () => document.removeEventListener("keydown", focusSearch);
  }, []);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const q = value.trim();
    router.push(q ? `/complaints?q=${encodeURIComponent(q)}` : "/complaints");
  };

  return (
    <form className="global-search" role="search" onSubmit={submit}>
      <Search size={17} aria-hidden="true" />
      <label className="sr-only" htmlFor="global-search">Search complaints by reference, customer or issue</label>
      <input id="global-search" ref={inputRef} value={value} onChange={(e) => setValue(e.target.value)} placeholder="Search complaints" autoComplete="off" enterKeyHint="search" />
      {value ? <button type="button" className="icon-button" aria-label="Clear search" onClick={() => { setValue(""); inputRef.current?.focus(); }}><X size={15} aria-hidden="true" /></button> : <kbd aria-hidden="true">/</kbd>}
    </form>
  );
}

function usePopover() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => () => setOpen(false), []);
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setOpen(false); ref.current?.querySelector<HTMLElement>("button")?.focus(); }
    };
    const onPointer = (event: PointerEvent) => { if (event.target instanceof Node && !ref.current?.contains(event.target)) setOpen(false); };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    return () => { document.removeEventListener("keydown", onKey); document.removeEventListener("pointerdown", onPointer); };
  }, [open]);
  return { open, setOpen, ref };
}

function NotificationsMenu() {
  const { open, setOpen, ref } = usePopover();
  const format = useFormat();
  const notifications = useResource("notifications-preview", (signal) => api.notifications({ pageSize: 6 }, signal));
  const unread = notifications.state === "ready" ? notifications.data.unreadCount : 0;

  return (
    <div className="popover-anchor" ref={ref}>
      <button type="button" className="icon-button topbar-icon" aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"} aria-expanded={open} aria-controls="notifications-popover"
        onClick={() => { if (!open) notifications.reload(); setOpen(!open); }}>
        <Bell size={19} aria-hidden="true" />
        {unread > 0 && <span className="unread-dot" aria-hidden="true">{unread > 9 ? "9+" : unread}</span>}
      </button>
      {open && (
        <div id="notifications-popover" className="popover notifications-popover" role="region" aria-label="Recent notifications">
          <div className="popover-head"><strong>Notifications</strong>{unread > 0 && <span className="muted">{unread} unread</span>}</div>
          {notifications.state === "loading" && <div className="popover-body"><span className="skeleton-line" /><span className="skeleton-line short" /></div>}
          {notifications.state === "error" && <p className="popover-empty">{notificationError(notifications.error)}</p>}
          {notifications.state === "ready" && (notifications.data.items.length === 0
            ? <p className="popover-empty">No notifications yet. Assignments, team responses and deadlines will appear here.</p>
            : <ul className="popover-list">
                {notifications.data.items.map((item) => (
                  <li key={item.id}>
                    <Link href={item.complaint ? `/complaints/${item.complaint.id}` : "/notifications"} className={item.read ? "" : "unread"} onClick={() => setOpen(false)}>
                      <span className="notification-title">{item.title}</span>
                      <span className="muted">{item.complaint?.reference ? `${item.complaint.reference} · ` : ""}{format.dateTime(item.occurredAt)}</span>
                    </Link>
                  </li>
                ))}
              </ul>)}
          <Link href="/notifications" className="popover-footer" onClick={() => setOpen(false)}>View all notifications <ArrowUpRight size={14} aria-hidden="true" /></Link>
        </div>
      )}
    </div>
  );
}

const notificationError = (error: ApiError) =>
  error.kind === "not-configured" ? "Notifications appear once RESOLVEIQ is connected." : error.kind === "unauthorized" ? "Sign in to see your notifications." : "Notifications couldn’t be loaded. Try again shortly.";

function ThemeToggle() {
  const { theme } = usePreferences();
  const [mounted, setMounted] = useState(false);
  const [resolvedTheme, setResolvedTheme] = useState<"light" | "dark">("light");

  useEffect(() => {
    setMounted(true);
    const update = () => {
      if (theme === "system") {
        const isDark = typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches;
        setResolvedTheme(isDark ? "dark" : "light");
      } else {
        setResolvedTheme(theme);
      }
    };
    update();
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, [theme]);

  const toggle = () => {
    const next = resolvedTheme === "dark" ? "light" : "dark";
    setPreference("theme", next);
  };

  if (!mounted) {
    return (
      <button type="button" className="icon-button theme-toggle-btn" aria-label="Toggle light or dark mode" disabled>
        <span style={{ width: 18, height: 18, display: "inline-block" }} />
      </button>
    );
  }

  const isDark = resolvedTheme === "dark";

  return (
    <button
      type="button"
      className="icon-button theme-toggle-btn"
      onClick={toggle}
      title={isDark ? "Switch to light mode" : "Switch to dark mode"}
      aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
    >
      {isDark ? (
        <Sun size={18} aria-hidden="true" className="theme-icon-sun" />
      ) : (
        <Moon size={18} aria-hidden="true" className="theme-icon-moon" />
      )}
    </button>
  );
}

function AccountMenu() {
  const { open, setOpen, ref } = usePopover();
  const session = useSession();
  const { theme } = usePreferences();
  const user = session.state === "ready" ? session.data.user : null;
  const isTest = user?.displayName.toLowerCase().includes("test");
  const displayTitle = isTest ? "Hackathon Operator" : (user?.displayName ?? "Account");
  const initials = isTest ? "HO" : user?.displayName.split(/\s+/).map((part) => part[0]).slice(0, 2).join("").toUpperCase();

  return (
    <div className="popover-anchor" ref={ref}>
      <button type="button" className="account-trigger" aria-expanded={open} aria-controls="account-popover" onClick={() => setOpen(!open)}>
        <span className="avatar" aria-hidden="true">{initials ?? <span className="avatar-empty" />}</span>
        <span className="account-text"><strong>{displayTitle}</strong><small>{user?.roleLabel ?? (session.state === "loading" ? "Checking sign-in…" : "Not signed in")}</small></span>
        <ChevronDown size={15} aria-hidden="true" />
      </button>
      {open && (
        <div id="account-popover" className="popover account-popover" role="region" aria-label="Account">
          {user && <div className="popover-head stacked"><strong>{displayTitle}</strong><span className="muted">{user.email}</span></div>}
          <div className="popover-theme-selector">
            <span className="muted small">Mode</span>
            <div className="theme-toggle-pills" role="radiogroup" aria-label="Appearance">
              <button
                type="button"
                className={`theme-pill ${theme === "light" ? "active" : ""}`}
                onClick={() => setPreference("theme", "light")}
                title="Light mode"
              >
                <Sun size={13} aria-hidden="true" /><span>Light</span>
              </button>
              <button
                type="button"
                className={`theme-pill ${theme === "dark" ? "active" : ""}`}
                onClick={() => setPreference("theme", "dark")}
                title="Dark mode"
              >
                <Moon size={13} aria-hidden="true" /><span>Dark</span>
              </button>
              <button
                type="button"
                className={`theme-pill ${theme === "system" ? "active" : ""}`}
                onClick={() => setPreference("theme", "system")}
                title="Match system"
              >
                <Laptop size={13} aria-hidden="true" /><span>System</span>
              </button>
            </div>
          </div>
          <nav className="popover-links" aria-label="Account">
            <Link href="/settings?section=profile" onClick={() => setOpen(false)}>My profile</Link>
            <Link href="/settings?section=preferences" onClick={() => setOpen(false)}>Preferences</Link>
            <Link href="/settings?section=help" onClick={() => setOpen(false)}>Help &amp; support</Link>
          </nav>
          <div className="popover-footer-actions">{session.state === "error" && session.error.kind === "unauthorized"
            ? <a className="popover-signout" href={signInUrl()}><LogIn size={18} aria-hidden="true" />Sign in</a>
            : <SignOutButton className="popover-signout" />}</div>
        </div>
      )}
    </div>
  );
}

function SignOutButton({ className, collapsed }: { className: string; collapsed?: boolean }) {
  const session = useSession();
  const toast = useToast();
  const [pending, setPending] = useState(false);

  const signOut = async () => {
    if (session.state !== "ready") {
      toast("You’re not signed in. Organisation sign-in is managed by your IT administrator.");
      return;
    }
    setPending(true);
    try {
      const result = await api.signOut();
      window.location.assign(result?.redirectUrl ?? "/");
    } catch {
      setPending(false);
      toast("Sign out didn’t complete. Your session is still active; try again.");
    }
  };

  return (
    <button type="button" className={className} onClick={signOut} disabled={pending} title={collapsed ? "Sign out" : undefined}>
      <LogOut size={18} aria-hidden="true" /><span className="nav-label">{pending ? "Signing out…" : "Sign out"}</span>
    </button>
  );
}
