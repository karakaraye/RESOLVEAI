import Link from "next/link";
import type { Tone } from "@/lib/labels";

export type StripItem = { label: string; value: number; href: string; tone?: Tone; hint?: string; current?: boolean };

// One continuous register strip instead of a grid of identical stat cards; urgent counts carry the only colour.
export function WorkloadStrip({ items, label }: { items: StripItem[]; label: string }) {
  return (
    <nav className="workload-strip" aria-label={label}>
      {items.map((item) => (
        <Link key={item.label} href={item.href} className={`strip-item${item.value > 0 && item.tone ? ` tone-${item.tone}` : ""}`} aria-current={item.current ? "true" : undefined} scroll={false}>
          <span className="strip-value">{item.value.toLocaleString("en-GB")}</span>
          <span className="strip-label">{item.label}</span>
          {item.hint && <span className="strip-hint">{item.hint}</span>}
        </Link>
      ))}
    </nav>
  );
}

export function WorkloadStripSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="workload-strip" role="status" aria-label="Loading summary">
      {Array.from({ length: count }, (_, i) => <span key={i} className="strip-item"><span className="skeleton-line short" /><span className="skeleton-line" /></span>)}
    </div>
  );
}
