"use client";

import { useSyncExternalStore } from "react";

// Local, per-browser display preferences. Nothing here is security- or case-relevant.
export type Preferences = {
  theme: "light" | "dark" | "system";
  dateStyle: "day-month" | "iso";
  hourCycle: "h23" | "h12";
  sidebarCollapsed: boolean;
};

const KEY = "resolveiq-preferences";
const LEGACY_KEY = "biirs-preferences";
const EVENT = "resolveiq-preferences-change";
const defaults: Preferences = { theme: "system", dateStyle: "day-month", hourCycle: "h23", sidebarCollapsed: false };

let cachedRaw: string | null | undefined;
let cached: Preferences = defaults;
let memoryRaw: string | null = null; // used when storage is blocked, so changes still apply for this page view

function read(): Preferences {
  let raw = memoryRaw;
  try { raw = window.localStorage.getItem(KEY) ?? window.localStorage.getItem(LEGACY_KEY) ?? memoryRaw; } catch { /* storage blocked */ }
  if (raw !== cachedRaw) {
    cachedRaw = raw;
    try { cached = { ...defaults, ...(raw ? JSON.parse(raw) : {}) }; } catch { cached = defaults; }
  }
  return cached;
}

function subscribe(onChange: () => void) {
  window.addEventListener("storage", onChange);
  window.addEventListener(EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(EVENT, onChange);
  };
}

export function usePreferences() {
  return useSyncExternalStore(subscribe, read, () => defaults);
}

export function setPreference<K extends keyof Preferences>(key: K, value: Preferences[K]) {
  const next = { ...read(), [key]: value };
  memoryRaw = JSON.stringify(next);
  try { window.localStorage.setItem(KEY, memoryRaw); } catch { /* memoryRaw keeps it for this page view */ }
  window.dispatchEvent(new Event(EVENT));
}
