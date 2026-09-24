import { useEffect, useState } from "react";
import { api } from "../api";
import { EmptyState } from "../components/EmptyState";
import { StatCard } from "../components/StatCard";
import {
  IconActivity, IconAlert, IconClock, IconDollar, IconRoute,
} from "../icons";
import type { Analytics, AnalyticsBucket } from "../types";

const RANGES = [7, 30, 90] as const;

const pct = (v: number) => `${(v * 100).toFixed(v > 0 && v < 0.01 ? 2 : 1)}%`;
const usd = (v: number) => `$${v < 1 ? v.toFixed(4) : v.toFixed(2)}`;
const ms = (v: number | null) => (v == null ? "—" : v >= 1000 ? `${(v / 1000).toFixed(1)}s` : `${v}ms`);

function shortDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/** Single-series daily bar chart. Hover target is the full column; the
 *  tooltip is an HTML overlay so it can carry the formatted value + date. */
function DailyBars({
  days, value, format, label,
}: {
  days: Analytics["by_day"];
  value: (d: AnalyticsBucket) => number;
  format: (v: number) => string;
  label: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 640;
  const H = 150;
  const padB = 22;
  const plotH = H - padB - 8;
  const max = Math.max(...days.map(value), 0);
  const col = W / Math.max(days.length, 1);
  const barW = Math.max(2, Math.min(28, col - 2));
  const labelEvery = Math.ceil(days.length / 7);
  const hovered = hover != null ? days[hover] : null;

  return (
    <div style={{ position: "relative" }}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        role="img"
        aria-label={`${label} per day`}
        style={{ display: "block", overflow: "visible" }}
        onMouseLeave={() => setHover(null)}
      >
        <line x1={0} x2={W} y1={H - padB} y2={H - padB} stroke="var(--border)" strokeWidth={1} />
        {days.map((d, i) => {
          const v = value(d);
          const h = max > 0 ? Math.max(v > 0 ? 2 : 0, (v / max) * plotH) : 0;
          const x = i * col + (col - barW) / 2;
          const y = H - padB - h;
          const r = Math.min(4, barW / 2, h);
          return (
            <g key={d.date}>
              {h > 0 && (
                <path
                  d={`M${x},${H - padB} V${y + r} Q${x},${y} ${x + r},${y} H${x + barW - r} Q${x + barW},${y} ${x + barW},${y + r} V${H - padB} Z`}
                  fill="var(--accent)"
                  opacity={hover == null || hover === i ? 1 : 0.45}
                />
              )}
              {i % labelEvery === 0 && (
                <text
                  x={i * col + col / 2} y={H - 6} textAnchor="middle"
                  fontSize={10.5} fill="var(--text-3)"
                >
                  {shortDate(d.date)}
                </text>
              )}
              <rect
                x={i * col} y={0} width={col} height={H - padB}
                fill="transparent"
                onMouseEnter={() => setHover(i)}
              />
            </g>
          );
        })}
      </svg>
      {hovered && hover != null && (
        <div
          className="card"
          style={{
            position: "absolute",
            top: 0,
            left: `${((hover + 0.5) / days.length) * 100}%`,
            transform: `translateX(${hover > days.length / 2 ? "-105%" : "5%"})`,
            padding: "6px 10px",
            fontSize: 12,
            pointerEvents: "none",
            whiteSpace: "nowrap",
            boxShadow: "var(--shadow-md, 0 4px 14px rgba(0,0,0,.12))",
          }}
        >
          <div className="faint">{shortDate(hovered.date)}</div>
          <div className="strong mono tnum">{format(value(hovered))}</div>
          {hovered.errors > 0 && (
            <div className="status-err" style={{ fontSize: 11.5 }}>{hovered.errors} error{hovered.errors > 1 ? "s" : ""}</div>
          )}
        </div>
      )}
    </div>
  );
}

function BreakdownTable<T extends AnalyticsBucket>({
  title, rows, name,
}: {
  title: string;
  rows: T[];
  name: (r: T) => string;
}) {
  return (
    <div className="card">
      <div className="card-head"><h3>{title}</h3></div>
      <div className="table-wrap">
        {rows.length === 0 ? (
          <div className="faint" style={{ padding: 16, fontSize: 13 }}>No traffic in this range.</div>
        ) : (
          <table className="tbl">
            <thead>
              <tr>
                <th>Name</th>
                <th className="num">Requests</th>
                <th className="num">Cost</th>
                <th className="num">Errors</th>
                <th className="num">p95</th>
                <th className="num">Fallbacks</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={name(r)}>
                  <td className="strong mono" style={{ fontSize: 12.5 }}>{name(r)}</td>
                  <td className="num mono tnum">{r.requests.toLocaleString()}</td>
                  <td className="num mono tnum">{usd(r.cost_usd)}</td>
                  <td className={`num mono tnum ${r.errors ? "status-err" : "faint"}`}>{pct(r.error_rate)}</td>
                  <td className="num mono tnum faint">{ms(r.p95_latency_ms)}</td>
                  <td className="num mono tnum faint">{r.fallbacks ? pct(r.fallback_rate) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export function AnalyticsPage() {
  const [days, setDays] = useState<(typeof RANGES)[number]>(7);
  const [data, setData] = useState<Analytics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    api.analytics(days).then(setData).catch(e => setError(String(e)));
  }, [days]);

  const t = data?.totals;

  return (
    <div className="container">
      <div className="page-head">
        <div className="grow">
          <h1 className="page-title">Analytics</h1>
          <p className="page-sub">Traffic, spend, reliability and fallbacks across every hub key.</p>
        </div>
        <div className="seg" role="radiogroup" aria-label="Time range">
          {RANGES.map(r => (
            <button
              key={r} type="button" role="radio"
              aria-checked={days === r}
              className={days === r ? "on" : ""}
              onClick={() => setDays(r)}
            >
              {r}d
            </button>
          ))}
        </div>
      </div>

      {error && <EmptyState icon={<IconAlert />} title="Couldn't load analytics">{error}</EmptyState>}

      {t && data && (
        <>
          <div className="stat-grid mb24">
            <StatCard icon={<IconActivity />} label="Requests" value={t.requests.toLocaleString()}
              meta={t.blocked ? `${t.blocked} blocked by quotas` : `${t.tokens.toLocaleString()} tokens`} />
            <StatCard icon={<IconDollar />} label="Spend" value={usd(t.cost_usd)}
              meta={`last ${data.range.days} days`} />
            <StatCard icon={<IconAlert />} label="Error rate" value={pct(t.error_rate)}
              meta={`${t.errors} failed call${t.errors === 1 ? "" : "s"}`} />
            <StatCard icon={<IconClock />} label="Latency p95" value={ms(t.p95_latency_ms)}
              meta={`p50 ${ms(t.p50_latency_ms)}`} />
            <StatCard icon={<IconRoute />} label="Fallbacks" value={pct(t.fallback_rate)}
              meta={`${t.fallbacks} call${t.fallbacks === 1 ? "" : "s"} served by a backup`} />
          </div>

          {t.requests === 0 ? (
            <EmptyState icon={<IconActivity />} title="No traffic yet">
              Once hub keys call <code className="mono">/v1/*</code>, trends and breakdowns show up here.
            </EmptyState>
          ) : (
            <>
              <div className="grid-2 mb24">
                <div className="card card-pad">
                  <h3 className="section-title" style={{ marginBottom: 10 }}>Requests per day</h3>
                  <DailyBars days={data.by_day} value={d => d.requests} format={v => `${v} requests`} label="Requests" />
                </div>
                <div className="card card-pad">
                  <h3 className="section-title" style={{ marginBottom: 10 }}>Spend per day</h3>
                  <DailyBars days={data.by_day} value={d => d.cost_usd} format={usd} label="Spend" />
                </div>
              </div>

              <div className="mb24"><BreakdownTable title="By model requested" rows={data.by_model} name={r => r.model} /></div>
              <div className="grid-2 mb24">
                <BreakdownTable title="By serving provider" rows={data.by_provider} name={r => r.provider} />
                <BreakdownTable title="By hub key" rows={data.by_key} name={r => r.name} />
              </div>

              {data.recent_errors.length > 0 && (
                <div className="card">
                  <div className="card-head"><h3>Recent errors</h3><span className="sub">newest first</span></div>
                  <div className="table-wrap">
                    <table className="tbl">
                      <thead>
                        <tr><th>When</th><th>Key</th><th>Model</th><th>Error</th></tr>
                      </thead>
                      <tbody>
                        {data.recent_errors.map((e, i) => (
                          <tr key={`${e.timestamp}-${i}`}>
                            <td className="faint" style={{ whiteSpace: "nowrap", fontSize: 12.5 }}>
                              {new Date(e.timestamp).toLocaleString()}
                            </td>
                            <td>{e.key_name ?? e.key_id}</td>
                            <td className="mono" style={{ fontSize: 12.5 }}>{e.model}</td>
                            <td className="status-err" style={{ fontSize: 12.5 }}>{e.error}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}
