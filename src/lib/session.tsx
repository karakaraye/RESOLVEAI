"use client";

import { createContext, ReactNode, useContext, useMemo } from "react";
import { api } from "./api/endpoints";
import type { Session } from "./api/types";
import { usePreferences } from "./preferences";
import { Resource, useResource } from "./use-resource";

const SessionContext = createContext<Resource<Session> | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const session = useResource("session", api.session);
  return <SessionContext.Provider value={session}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const session = useContext(SessionContext);
  if (!session) throw new Error("useSession must be used inside SessionProvider");
  return session;
}

// Dates display in the institution's configured time zone once the session is known, otherwise the browser's.
export function useFormat() {
  const session = useContext(SessionContext);
  const { dateStyle, hourCycle } = usePreferences();
  const timeZone = session?.state === "ready" ? session.data.tenant.timeZone : undefined;
  return useMemo(() => {
    const zone = timeZone ? { timeZone } : {};
    const time = new Intl.DateTimeFormat("en-GB", { ...zone, hour: "2-digit", minute: "2-digit", hourCycle });
    const dayMonth = new Intl.DateTimeFormat("en-GB", { ...zone, day: "2-digit", month: "short", year: "numeric" });
    const iso = new Intl.DateTimeFormat("en-CA", { ...zone, year: "numeric", month: "2-digit", day: "2-digit" });
    const date = (value?: string) => (value ? (dateStyle === "iso" ? iso : dayMonth).format(new Date(value)) : "—");
    return {
      timeZone: timeZone ?? Intl.DateTimeFormat().resolvedOptions().timeZone,
      date,
      time: (value?: string) => (value ? time.format(new Date(value)) : "—"),
      dateTime: (value?: string) => (value ? `${date(value)}, ${time.format(new Date(value))}` : "—"),
    };
  }, [timeZone, dateStyle, hourCycle]);
}

export const can = (session: Resource<Session>, permission: string) => session.state === "ready" && session.data.permissions.includes(permission);
