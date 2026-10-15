import Link from "next/link";

export default function NotFound() {
  return (
    <section className="panel center-state">
      <p className="eyebrow">Page not found</p>
      <h1>This page doesn’t exist</h1>
      <p className="muted">Check the address, or go back to your work.</p>
      <div className="form-actions centered">
        <Link className="button button-primary" href="/">Go to Home</Link>
        <Link className="button button-secondary" href="/complaints">Open complaints</Link>
      </div>
    </section>
  );
}
