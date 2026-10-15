"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";

// Filters live in the URL so Home links can pre-filter lists and Back restores what the operator was looking at.
export function useUrlState() {
  const params = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();

  const set = useCallback((changes: Record<string, string | number | null | undefined>, { resetPage = true } = {}) => {
    const next = new URLSearchParams(params.toString());
    for (const [key, value] of Object.entries(changes)) {
      if (value === null || value === undefined || value === "") next.delete(key);
      else next.set(key, String(value));
    }
    if (resetPage && !("page" in changes)) next.delete("page");
    const text = next.toString();
    router.replace(text ? `${pathname}?${text}` : pathname, { scroll: false });
  }, [params, pathname, router]);

  const current = params.toString();
  return { params, set, here: current ? `${pathname}?${current}` : pathname };
}

// Only same-origin relative paths are accepted as a "back to" target.
export const safeReturnPath = (value: string | null) => (value && value.startsWith("/") && !value.startsWith("//") ? value : null);
