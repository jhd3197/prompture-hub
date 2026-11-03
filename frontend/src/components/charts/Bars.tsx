import type { ReactNode } from "react";

export interface BarRow {
  key: string;
  name: ReactNode;
  sub?: ReactNode;
  value: number;
  valueText: string;
  valueSub?: string;
  alt?: boolean;
}

/** Ranked horizontal bars scaled to the largest row. The text value is always shown next to the bar. */
export function BarList({ rows, label }: { rows: BarRow[]; label: string }) {
  const max = Math.max(...rows.map(r => r.value), 0);
  return (
    <ul className="bars" aria-label={label}>
      {rows.map((r, i) => (
        <li key={r.key} style={{ ["--i" as string]: i }}>
          <span className="b-name truncate">{r.name}{r.sub && <small>{r.sub}</small>}</span>
          <span className="b-track" aria-hidden="true"><span className={`b-fill${r.alt ? " alt" : ""}`} style={{ ["--p" as string]: max > 0 ? Math.max(r.value > 0 ? 0.012 : 0, r.value / max) : 0 }} /></span>
          <span className="b-val">{r.valueText}{r.valueSub && <small>{r.valueSub}</small>}</span>
        </li>
      ))}
    </ul>
  );
}

/** One stacked bar of shares (lightness ramp of the accent) with a legend carrying the numbers. */
export function ShareBar({ rows, label, total }: { rows: Array<{ key: string; name: string; value: number; text: string }>; label: string; total?: number }) {
  const sum = total ?? rows.reduce((a, r) => a + r.value, 0);
  if (sum <= 0) return null;
  return (
    <div role="group" aria-label={label}>
      <div className="share" aria-hidden="true">
        {rows.map((r, k) => <i key={r.key} style={{ ["--w" as string]: r.value / sum, ["--k" as string]: Math.min(k, 6) }} title={`${r.name}: ${r.text}`} />)}
      </div>
      <ul className="legend">
        {rows.map((r, k) => (
          <li key={r.key} style={{ ["--k" as string]: Math.min(k, 6) }}>
            <i className="sw" aria-hidden="true" /><span className="l-name truncate">{r.name}</span>
            <span className="l-val">{r.text} ({Math.round((r.value / sum) * 100)}%)</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
