"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError } from "./api/client";

export type Resource<T> =
  | { state: "loading"; data?: undefined; error?: undefined; reload: () => void }
  | { state: "ready"; data: T; error?: undefined; reload: () => void }
  | { state: "error"; data?: undefined; error: ApiError; reload: () => void };

type Snapshot<T> = { key: string; version: number; data?: T; error?: ApiError };

// Loads `load` whenever `key` changes; a null key means "do not load yet".
// reload() refetches while keeping the last good data on screen, so saving an action never flashes a skeleton.
export function useResource<T>(key: string | null, load: (signal: AbortSignal) => Promise<T>): Resource<T> {
  const [snapshot, setSnapshot] = useState<Snapshot<T> | null>(null);
  const [version, setVersion] = useState(0);
  const reload = useCallback(() => setVersion((v) => v + 1), []);

  useEffect(() => {
    if (key === null) return;
    const controller = new AbortController();
    load(controller.signal)
      .then((data) => setSnapshot({ key, version, data }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setSnapshot({ key, version, error: error instanceof ApiError ? error : new ApiError("server", "Something went wrong.") });
      });
    return () => controller.abort();
    // `load` is recreated each render; `key` captures everything it depends on.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, version]);

  const current = snapshot && key !== null && snapshot.key === key ? snapshot : null;
  if (current?.data !== undefined) return { state: "ready", data: current.data, reload };
  if (current?.error && current.version === version) return { state: "error", error: current.error, reload };
  return { state: "loading", reload };
}
