// Shown while a page's URL-dependent content resolves; mirrors the page header so nothing jumps.
export function PageFallback({ title }: { title: string }) {
  return (
    <div role="status" aria-label={`Loading ${title}`}>
      <header className="page-header"><div><h1>{title}</h1></div></header>
      <div className="skeleton-block" style={{ height: 320 }} />
    </div>
  );
}
