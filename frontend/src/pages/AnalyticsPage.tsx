import { useState } from "react";
import { api } from "../api";
import { BarList } from "../components/charts/Bars";
import { ShareBar } from "../components/charts/Bars";
import { Sparkline } from "../components/charts/Sparkline";
import { TimeChart } from "../components/charts/TimeChart";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { Num } from "../components/Num";
import { PageHead } from "../components/PageHead";
import { SkelChart, SkelReadouts, SkelRows } from "../components/Skeleton";
import { IconActivity, IconAlert, IconClock, IconDollar, IconRoute } from "../icons";
import { dateTime, int, ms, pct, plural, shortDate, usd } from "../util/format";
import { sortRows, useAsync, useSort } from "../util/hooks";
import type { Analytics, AnalyticsBucket } from "../types";

const RANGES = [7, 30, 90] as const;
type Key = "name" | "requests" | "cost" | "errors" | "p95" | "fallbacks";

function SortTh({ label, k, sort, num }: { label: string; k: Key; sort: ReturnType<typeof useSort<Key>>; num?: boolean }) {
  return (
    <th scope="col" className={num ? "num" : undefined} aria-sort={sort.ariaSort(k)}>
      <button type="button" className="sort-btn" onClick={() => sort.toggle(k, k === "name")}>
        {label}
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m7 10 5 5 5-5" /></svg>
      </button>
    </th>
  );
}

function Breakdown<T extends AnalyticsBucket>({ title, rows, name }: { title: string; rows: T[]; name: (r: T) => string }) {
  const sort = useSort<Key>("cost");
  const get = (r: T): number | string => {
    switch (sort.key) {
      case "name": return name(r);
      case "requests": return r.requests;
      case "cost": return r.cost_usd;
      case "errors": return r.error_rate;
      case "p95": return r.p95_latency_ms ?? -1;
      default: return r.fallback_rate;
    }
  };
  const sorted = sortRows(rows, get, sort.dir);
  const top = Math.max(...rows.map(r => r.requests), 1);
  return (
    <section className="panel rise" aria-label={title}>
      <div className="panel-head"><h2>{title}</h2><span className="sub">{plural(rows.length, "row")}</span></div>
      {rows.length === 0 ? (
        <div className="state"><p>No traffic in this range.</p></div>
      ) : (
        <div className="table-wrap">
          <table className="tbl">
            <caption className="sr-only">{title}, sortable</caption>
            <thead>
              <tr>
                <SortTh label="Name" k="name" sort={sort} />
                <SortTh label="Requests" k="requests" sort={sort} num />
                <SortTh label="Cost" k="cost" sort={sort} num />
                <SortTh label="Errors" k="errors" sort={sort} num />
                <SortTh label="p95" k="p95" sort={sort} num />
                <SortTh label="Fallbacks" k="fallbacks" sort={sort} num />
              </tr>
            </thead>
            <tbody>
              {sorted.map(r => (
                <tr key={name(r)}>
                  <td className="cell-id strong"><span className="cell-trunc" title={name(r)}>{name(r)}</span></td>
                  <td className="num cell-id">
                    <span className="row" style={{ justifyContent: "flex-end", gap: 8 }}>
                      <span className="b-track" style={{ width: 44, height: 4, position: "relative", overflow: "hidden", background: "var(--sunk)", borderRadius: 2 }} aria-hidden="true">
                        <span className="b-fill" style={{ ["--p" as string]: r.requests / top }} />
                      </span>
                      {int(r.requests)}
                    </span>
                  </td>
                  <td className="num cell-id">{usd(r.cost_usd)}</td>
                  <td className={`num cell-id ${r.errors ? "status-err" : "faint"}`}>{pct(r.error_rate)}</td>
                  <td className="num cell-id faint">{ms(r.p95_latency_ms)}</td>
                  <td className="num cell-id faint">{r.fallbacks ? pct(r.fallback_rate) : "none"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function LatencyRange({ rows }: { rows: Analytics["by_model"] }) {
  const usable = rows.filter(r => r.p95_latency_ms != null && r.p50_latency_ms != null).slice(0, 8);
  const max = Math.max(...usable.map(r => r.p95_latency_ms ?? 0), 1);
  if (usable.length === 0) return <div className="state"><p>No latency samples in this range.</p></div>;
  return (
    <div role="list" aria-label="Latency by model, median to 95th percentile">
      {usable.map(r => {
        const a = (r.p50_latency_ms! / max) * 100;
        const b = (r.p95_latency_ms! / max) * 100;
        return (
          <div className="range-row" role="listitem" key={r.model}>
            <span className="cell-id truncate" title={r.model}>{r.model}</span>
            <span className="range-track" aria-hidden="true">
              <span className="range-span" style={{ ["--a" as string]: `${a}%`, ["--w" as string]: `${Math.max(b - a, 1.5)}%` }} />
              <i className="range-pt" style={{ ["--at" as string]: `${a}%` }} />
            </span>
            <span className="r-val">{ms(r.p50_latency_ms)} to {ms(r.p95_latency_ms)}</span>
          </div>
        );
      })}
    </div>
  );
}

export function AnalyticsPage() {
  const [days, setDays] = useState<(typeof RANGES)[number]>(7);
  const { data, error, loading, reload } = useAsync(() => api.analytics(days), [days]);
  const t = data?.totals;
  const by = data?.by_day ?? [];
  const labels = by.map(d => d.date);
  const ticks = by.map(d => shortDate(d.date));
  const stale = loading && !!data;

  return (
    <div className="container">
      <PageHead title="Analytics" sub="Traffic, spend, reliability and fallbacks across every hub key.">
        <div className="seg" role="radiogroup" aria-label="Time range">
          {RANGES.map(r => (
            <button key={r} type="button" role="radio" aria-checked={days === r} className={days === r ? "on" : ""} onClick={() => setDays(r)}>{r} days</button>
          ))}
        </div>
      </PageHead>

      {error && !data ? (
        <div className="panel"><ErrorState title="Couldn't load analytics" error={error} onRetry={reload} /></div>
      ) : !t || !data ? (
        <div className="stack" aria-busy="true">
          <SkelReadouts n={5} />
          <div className="cols cols-2"><div className="panel"><SkelChart /></div><div className="panel"><SkelChart /></div></div>
          <div className="panel"><SkelRows rows={5} /></div>
        </div>
      ) : (
        <div className="stack" style={{ opacity: stale ? 0.6 : 1, transition: "opacity 160ms" }} aria-busy={stale}>
          {error && <div className="notice bad" role="alert"><IconAlert /><span>Couldn't refresh: {error}. Showing the last result. <button type="button" className="btn btn-sm" onClick={reload}>Try again</button></span></div>}
          <div className="readouts rise" style={{ ["--cols" as string]: "repeat(5, minmax(0, 1fr))" }}>
            <div className="readout span-all">
              <span className="caption readout-label"><IconActivity />Requests</span>
              <div className="readout-value"><Num value={t.requests} format={v => int(Math.round(v))} /></div>
              <div className="readout-meta">{t.blocked ? `${int(t.blocked)} blocked by quotas` : `${int(t.tokens)} tokens`}</div>
              <Sparkline values={by.map(d => d.requests)} label={`Requests per day, last ${days} days`} />
            </div>
            <div className="readout">
              <span className="caption readout-label"><IconDollar />Spend</span>
              <div className="readout-value"><Num value={t.cost_usd} format={v => usd(v)} /></div>
              <div className="readout-meta">last {data.range.days} days</div>
              <Sparkline values={by.map(d => d.cost_usd)} label={`Spend per day, last ${days} days`} />
            </div>
            <div className={`readout${t.error_rate >= 0.05 ? " readout-bad" : ""}`}>
              <span className="caption readout-label"><IconAlert />Error rate</span>
              <div className="readout-value"><Num value={t.error_rate * 100} format={v => `${v.toFixed(1)}`} /><span className="unit">%</span></div>
              <div className="readout-meta">{plural(t.errors, "failed call")}</div>
              <Sparkline tone="bad" values={by.map(d => d.errors)} label={`Failed calls per day, last ${days} days`} />
            </div>
            <div className="readout">
              <span className="caption readout-label"><IconClock />Latency p95</span>
              <div className="readout-value">{t.p95_latency_ms == null ? <span className="faint">n/a</span> : <Num value={t.p95_latency_ms} format={v => ms(Math.round(v))} />}</div>
              <div className="readout-meta">p50 {ms(t.p50_latency_ms)}</div>
              <Sparkline values={by.map(d => d.p95_latency_ms ?? 0)} label={`p95 latency per day, last ${days} days`} />
            </div>
            <div className="readout">
              <span className="caption readout-label"><IconRoute />Fallbacks</span>
              <div className="readout-value"><Num value={t.fallback_rate * 100} format={v => v.toFixed(1)} /><span className="unit">%</span></div>
              <div className="readout-meta">{plural(t.fallbacks, "call")} served by a backup</div>
              <Sparkline values={by.map(d => d.fallbacks)} label={`Fallback calls per day, last ${days} days`} />
            </div>
          </div>

          {t.requests === 0 ? (
            <div className="panel">
              <EmptyState icon={<IconActivity />} title="No traffic in this range">
                Once hub keys call <code className="mono">/v1/*</code>, traces and breakdowns appear here. Try a longer range if the hub was quiet.
              </EmptyState>
            </div>
          ) : (
            <>
              <div className="cols cols-2">
                <section className="panel rise" style={{ ["--i" as string]: 1 }} aria-label="Requests per day">
                  <TimeChart
                    title="Requests per day" kind="bars" labels={labels} tickLabels={ticks}
                    series={[{ name: "Requests", values: by.map(d => d.requests) }, { name: "Errors", values: by.map(d => d.errors), tone: "bad" }]}
                    format={v => int(Math.round(v))}
                  />
                </section>
                <section className="panel rise" style={{ ["--i" as string]: 2 }} aria-label="Spend per day">
                  <TimeChart
                    title="Spend per day" kind="lines" labels={labels} tickLabels={ticks}
                    series={[{ name: "Spend", values: by.map(d => d.cost_usd) }]}
                    format={v => usd(v)} tickFormat={v => usd(v, v < 1 ? 3 : 2)}
                  />
                </section>
              </div>

              <div className="cols cols-2">
                <section className="panel rise" style={{ ["--i" as string]: 3 }} aria-label="Latency per day">
                  <TimeChart
                    title="Latency per day" kind="lines" labels={labels} tickLabels={ticks}
                    series={[{ name: "p95", values: by.map(d => d.p95_latency_ms ?? 0) }, { name: "p50", values: by.map(d => d.p50_latency_ms ?? 0), tone: "alt" }]}
                    format={v => (v === 0 ? "no calls" : ms(v))} tickFormat={v => ms(v)}
                  />
                </section>
                <section className="panel rise" style={{ ["--i" as string]: 4 }} aria-labelledby="lat-model">
                  <div className="panel-head"><h2 id="lat-model">Latency by model</h2><span className="sub">median to p95</span></div>
                  <LatencyRange rows={data.by_model} />
                </section>
              </div>

              <div className="cols cols-8-4">
                <Breakdown title="By model requested" rows={data.by_model} name={r => r.model} />
                <section className="panel rise" aria-labelledby="share">
                  <div className="panel-head"><h2 id="share">Serving provider share</h2><span className="sub">by requests</span></div>
                  <div className="panel-body">
                    <ShareBar
                      label="Share of requests by serving provider"
                      rows={data.by_provider.map(p => ({ key: p.provider, name: p.provider, value: p.requests, text: `${int(p.requests)} req` }))}
                    />
                  </div>
                </section>
              </div>

              <div className="cols cols-2">
                <Breakdown title="By serving provider" rows={data.by_provider} name={r => r.provider} />
                <section className="panel rise" aria-labelledby="by-key">
                  <div className="panel-head"><h2 id="by-key">Spend by hub key</h2><span className="sub">last {days} days</span></div>
                  <BarList
                    label="Spend by hub key"
                    rows={data.by_key.map(k => ({ key: String(k.key_id), name: k.name, sub: plural(k.requests, "request"), value: k.cost_usd, valueText: usd(k.cost_usd) }))}
                  />
                </section>
              </div>

              {data.by_project && data.by_project.some(r => r.project) && (
                <Breakdown title="By project" rows={data.by_project} name={r => r.project ?? "no project"} />
              )}

              {data.recent_errors.length > 0 && (
                <section className="panel rise" aria-labelledby="errs">
                  <div className="panel-head"><h2 id="errs">Recent errors</h2><span className="sub">newest first</span></div>
                  <div className="table-wrap">
                    <table className="tbl cards">
                      <thead><tr><th scope="col">When</th><th scope="col">Key</th><th scope="col">Model</th><th scope="col">Error</th></tr></thead>
                      <tbody>
                        {data.recent_errors.map((e, i) => (
                          <tr key={`${e.timestamp}-${i}`}>
                            <td className="td-primary cell-id nowrap faint">{dateTime(e.timestamp)}</td>
                            <td data-label="Key" className="nowrap">{e.key_name ?? e.key_id}</td>
                            <td data-label="Model" className="cell-id"><span className="cell-trunc" title={e.model}>{e.model}</span></td>
                            <td data-label="Error" className="td-wide"><span className="chip chip-bad" title={e.error}>{e.error.length > 60 ? `${e.error.slice(0, 60)}...` : e.error}</span></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
