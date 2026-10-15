"use client";

import { useSyncExternalStore } from "react";

// Current time, refreshed each minute. Null during server render so time-dependent text never mismatches on hydration.
let now = 0;
const subscribe = (onChange: () => void) => {
  const timer = window.setInterval(() => { now = Date.now(); onChange(); }, 60_000);
  return () => window.clearInterval(timer);
};
const getSnapshot = () => (now ||= Date.now());

export function useNow(): number | null {
  return useSyncExternalStore(subscribe, getSnapshot, () => null);
}
