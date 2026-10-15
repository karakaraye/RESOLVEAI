"use client";

import Link from "next/link";
import { useId, useState } from "react";

type Point = { date: string; value: number | null };

// Single-series trend: 2px line, light area, recessive grid, crosshair + tooltip on hover/focus, gaps for missing data.
export function TrendChart({ points, label, formatDate, height = 180 }: { points: Point[]; label: string; formatDate: (iso: string) => string; height?: number }) {
  const [active, setActive] = useState<number | null>(null);
  const gradientId = useId();
  const width = 600;
  const pad = { top: 12, right: 12, bottom: 24, left: 34 };
  const values = points.map((p) => p.value).filter((v): v is number => v !== null);
  const max = niceMax(Math.max(1, ...values));
  const x = (i: number) => pad.left + (points.length <= 1 ? 0 : (i / (points.length - 1)) * (width - pad.left - pad.right));
  const y = (v: number) => pad.top + (1 - v / max) * (height - pad.top - pad.bottom);

  const segments: string[] = [];
  let current = "";
  points.forEach((p, i) => {
    if (p.value === null) { if (current) segments.push(current); current = ""; return; }
    current += `${current ? "L" : "M"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`;
  });
  if (current) segments.push(current);
  const area = segments.map((d) => {
    const coords = d.slice(1).split(/[ML]/).map((pair) => pair.split(",").map(Number));
    return `${d}L${coords.at(-1)![0]},${y(0)}L${coords[0][0]},${y(0)}Z`;
  });
  const ticks = [0, max / 2, max];
  const labelEvery = Math.max(1, Math.ceil(points.length / (height < 200 ? 3 : 6)));
  const activePoint = active !== null ? points[active] : null;

  return (
    <figure className="chart">
      <div className="chart-plot">
        <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${label}. ${points.length} points; highest ${Math.max(0, ...values)}.`} preserveAspectRatio="none" style={{ height }}
          onPointerLeave={() => setActive(null)}
          onPointerMove={(e) => {
            const box = e.currentTarget.getBoundingClientRect();
            const px = ((e.clientX - box.left) / box.width) * width;
            setActive(Math.max(0, Math.min(points.length - 1, Math.round(((px - pad.left) / (width - pad.left - pad.right)) * (points.length - 1)))));
          }}>
          <defs>
            <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1"><stop offset="0" className="chart-area-top" /><stop offset="1" className="chart-area-bottom" /></linearGradient>
          </defs>
          {ticks.map((t) => <line key={t} x1={pad.left} x2={width - pad.right} y1={y(t)} y2={y(t)} className="chart-grid" />)}
          {area.map((d, i) => <path key={i} d={d} fill={`url(#${gradientId})`} />)}
          {segments.map((d, i) => <path key={i} d={d} className="chart-line" vectorEffect="non-scaling-stroke" />)}
          {activePoint && active !== null && <line x1={x(active)} x2={x(active)} y1={pad.top} y2={y(0)} className="chart-crosshair" vectorEffect="non-scaling-stroke" />}
        </svg>
        <div className="chart-y" aria-hidden="true">{ticks.slice().reverse().map((t) => <span key={t} style={{ top: `${(y(t) / height) * 100}%` }}>{formatCount(t)}</span>)}</div>
        {activePoint && active !== null && activePoint.value !== null && (
          <span className="chart-dot" style={{ left: `${(x(active) / width) * 100}%`, top: `${(y(activePoint.value) / height) * 100}%` }} aria-hidden="true" />
        )}
        {activePoint && active !== null && (
          <div className="chart-tooltip" style={{ left: `${(x(active) / width) * 100}%` }} role="status">
            <span>{formatDate(activePoint.date)}</span>
            <strong>{activePoint.value === null ? "No data" : activePoint.value.toLocaleString("en-GB")}</strong>
          </div>
        )}
      </div>
      <div className="chart-x" aria-hidden="true">
        {points.map((p, i) => (i === points.length - 1 || (i % labelEvery === 0 && points.length - 1 - i >= labelEvery / 2)) && <span key={p.date} style={{ left: `${(x(i) / width) * 100}%` }}>{formatDate(p.date)}</span>)}
      </div>
      <details className="chart-table">
        <summary>Show as table</summary>
        <table><thead><tr><th scope="col">Date</th><th scope="col">{label}</th></tr></thead>
          <tbody>{points.map((p) => <tr key={p.date}><td>{formatDate(p.date)}</td><td>{p.value === null ? "No data" : p.value.toLocaleString("en-GB")}</td></tr>)}</tbody>
        </table>
      </details>
    </figure>
  );
}

// Ranked magnitude list: label, single-hue bar, value as text. Rows link to the filtered register when permitted.
export function BarList({ items, valueLabel, max: fixedMax }: { items: { label: string; value: number | null; secondary?: string; href?: string }[]; valueLabel: string; max?: number }) {
  const max = fixedMax ?? Math.max(1, ...items.map((i) => i.value ?? 0));
  return (
    <ul className="bar-list" aria-label={valueLabel}>
      {items.map((item) => {
        const content = (
          <>
            <span className="bar-label">{item.label}{item.secondary && <small>{item.secondary}</small>}</span>
            <span className="bar-track" aria-hidden="true"><span className="bar-fill" style={{ width: `${item.value ? Math.max(2, (item.value / max) * 100) : 0}%` }} /></span>
            <span className="bar-value">{item.value == null ? "—" : item.value.toLocaleString("en-GB", { maximumFractionDigits: 1 })}</span>
          </>
        );
        return <li key={item.label}>{item.href ? <Link href={item.href} title={`${item.label}: ${item.value ?? "no data"} ${valueLabel}. Open matching cases`}>{content}</Link> : <div title={`${item.label}: ${item.value ?? "no data"} ${valueLabel}`}>{content}</div>}</li>;
      })}
    </ul>
  );
}

function niceMax(value: number) {
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const step = [1, 2, 2.5, 5, 10].find((s) => s * magnitude >= value) ?? 10;
  return step * magnitude;
}

const formatCount = (value: number) => (Number.isInteger(value) ? value.toLocaleString("en-GB") : value.toFixed(1));
