"use client";

export default function Error({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <section className="panel center-state" role="alert">
      <p className="eyebrow">Something went wrong</p>
      <h1>This page couldn’t be displayed</h1>
      <p className="muted">Nothing was changed. Try again, and if it keeps happening, tell your RESOLVEIQ administrator.</p>
      <div className="form-actions centered">
        <button type="button" className="button button-primary" onClick={reset}>Try again</button>
      </div>
    </section>
  );
}
