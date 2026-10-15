// RESOLVEIQ route mark: a spine with three nodes, a complaint moving from intake through review to a verified resolution.
export function BrandMark({ size = 32 }: { size?: number }) {
  return (
    <svg className="brand-mark" width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="8" className="brand-mark-bg" />
      <path d="M11 8.5v15" className="brand-mark-line" />
      <path d="M11 16h6.5a4.5 4.5 0 0 0 4.5-4.5V10" className="brand-mark-line" />
      <circle cx="11" cy="8.5" r="2.4" className="brand-mark-node" />
      <circle cx="11" cy="23.5" r="2.4" className="brand-mark-node" />
      <circle cx="22" cy="9" r="3" className="brand-mark-signal" />
    </svg>
  );
}
