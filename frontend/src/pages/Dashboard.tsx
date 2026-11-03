import { useMemo } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { Meter } from "../components/charts/Meter";
import { Sparkline } from "../components/charts/Sparkline";
import { Num } from "../components/Num";
import { PageHead } from "../components/PageHead";
import { SkelReadouts, SkelRows } from "../components/Skeleton";
import { TrustFlow } from "../components/TrustFlow";
import { IconActivity, IconAlert, IconCheck, IconDollar, IconKey, IconPlus } from "../icons";
import { dateTime, int, ms, pct, plural, timeAgo, usd } from "../util/format";
import { useAsync, useRowNav } from "../util/hooks";
import { projectedSpend, useKeySpend } from "../util/keySpend";
import type { CurrentUser, UsageRow } from "../types";

function StatusChip({ status }: { status: string }) {
  if (status === "ok") return <span className="chip chip-ok"><IconCheck />ok</span>;
  const soft = status === "rate_limited" || status === "quota_exceeded";
  return <span className={`chip ${soft ? "chip-warn" : "chip-bad"}`}><IconAlert />{status}</span>;
}

function ActivityTable({ rows }: { rows: UsageRow[] }) {
  const { tbodyProps, rowProps } = useRowNav();
  const slowest = Math.max(...rows.map(r => r.latency_ms), 1);
  return (
    <div className="table-wrap">
      <table className="tbl cards">
        <caption className="sr-only">Most recent metered calls, newest first</caption>
        <thead>
          <tr>
            <th scope="col">Model</th>
            <th scope="col">Endpoint</th>
            <th scope="col" className="num">Tokens</th>
            <th scope="col" className="num">Cost</th>
            <th scope="col">Latency</th>
            <th scope="col">Status</th>
            <th scope="col" className="num">When</th>
          </tr>
        </thead>
        <tbody {...tbodyProps}>
          {rows.map((u, i) => (
            <tr key={u.id} {...rowProps(i)}>
              <td className="td-primary">
                <span className="cell-main cell-id cell-trunc" title={u.model}>{u.model}</span>
                {u.served_by && u.served_by !== u.model && <span className="cell-sub cell-trunc" title={`Served by ${u.served_by}`}>via {u.served_by}</span>}
              </td>
              <td data-label="Endpoint" className="cell-id nowrap">{u.endpoint.replace("/v1", "")}</td>
              <td data-label="Tokens" className="num cell-id">{int(u.total_tokens)}</td>
              <td data-label="Cost" className="num cell-id cost-pos">{usd(u.cost_usd)}</td>
              <td data-label="Latency" className="cell-id nowrap">
                <span className="row" style={{ gap: 8 }}>
                  <span className="b-track" style={{ width: 56, height: 4, background: "var(--sunk)", position: "relative", overflow: "hidden", borderRadius: 2 }} aria-hidden="true">
                    <span className="b-fill alt" style={{ ["--p" as string]: u.latency_ms / slowest }} />
                  </span>
                  <span style={{ minWidth: 52, textAlign: "right" }}>{ms(u.latency_ms)}</span>
                </span>
              </td>
              <td data-label="Status"><StatusChip status={u.status} /></td>
              <td data-label="When" className="num nowrap faint" title={dateTime(u.timestamp)}>{timeAgo(u.timestamp)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Dashboard({ user }: { user: CurrentUser }) {
  const ov = useAsync(() => api.overview(), []);
  const week = useAsync(() => api.analytics(7), []);
  const data = ov.data;
  const spend = useKeySpend(data?.recent_keys ?? null);

  const keyRows = useMemo(() => {
    if (!data) return [];
    return data.recent_keys.filter(k => k.active)
      .map(k => {
        const used = spend.data?.get(k.id) ?? 0;
        return { k, used, f: k.spend_cap_usd > 0 ? used / k.spend_cap_usd : 0 };
      })
      .sort((a, b) => b.f - a.f || a.k.name.localeCompare(b.k.name))
      .slice(0, 5);
  }, [data, spend.data]);

  const days = week.data?.by_day ?? [];
  const t = week.data?.totals;

  return (
    <div className="container">
      <PageHead title="Overview" docTitle="Overview" sub={<>Metered traffic for <strong>{user.email}</strong>. Figures update when you reload.</>}>
        <Link to="/keys/new" className="btn btn-primary"><IconPlus />New hub key</Link>
      </PageHead>

      {ov.error ? (
        <div className="panel"><ErrorState title="Couldn't load the overview" error={ov.error} onRetry={ov.reload} /></div>
      ) : !data ? (
        <div className="stack" aria-busy="true">
          <SkelReadouts n={3} />
          <div className="panel"><SkelRows rows={6} label="Loading recent activity" /></div>
        </div>
      ) : (
        <div className="stack">
          <div className="readouts rise" style={{ ["--cols" as string]: "minmax(0, 1.4fr) minmax(0, 1fr) minmax(0, 1fr)" }}>
            <div className="readout is-hero span-all">
              <span className="caption readout-label"><IconDollar />Spend, last 24 hours</span>
              <div className="readout-value"><span className="cur">$</span><Num value={data.spend_24h} format={v => v.toFixed(v < 1 ? 4 : 2)} /></div>
              <div className="readout-meta">{plural(data.recent_usage.length, "metered call")} in the feed below</div>
              {days.length > 1 && <Sparkline values={days.map(d => d.cost_usd)} label="Spend per day, last 7 days" />}
            </div>
            <div className="readout">
              <span className="caption readout-label"><IconKey />Active hub keys</span>
              <div className="readout-value"><Num value={Math.max(data.active_key_count, data.recent_keys.filter(k => k.active).length)} format={v => String(Math.round(v))} /></div>
              <div className="readout-meta">
                {keyRows[0] && keyRows[0].f >= 0.7
                  ? <span className={keyRows[0].f >= 0.9 ? "status-err" : "status-warn"}>{keyRows[0].k.name} is at {Math.round(keyRows[0].f * 100)}% of its cap</span>
                  : <Link to="/keys">Manage keys</Link>}
              </div>
            </div>
            <div className="readout">
              <span className="caption readout-label"><IconActivity />Calls, 7 days</span>
              <div className="readout-value">{t ? <Num value={t.requests} format={v => int(Math.round(v))} /> : <span className="faint">n/a</span>}</div>
              <div className="readout-meta">{t ? <>{pct(t.error_rate)} errors, p95 {ms(t.p95_latency_ms)}</> : "Analytics unavailable"}</div>
              {days.length > 1 && <Sparkline values={days.map(d => d.requests)} label="Requests per day, last 7 days" />}
            </div>
          </div>

          <div className="cols cols-8-4">
            <section className="panel rise" style={{ ["--i" as string]: 1 }} aria-labelledby="near-cap">
              <div className="panel-head">
                <h2 id="near-cap">Keys closest to their cap</h2>
                <span className="sub">cap window to date</span>
                <div className="push"><Link to="/keys" className="btn btn-sm btn-ghost">All keys</Link></div>
              </div>
              {keyRows.length === 0 ? (
                <EmptyState icon={<IconKey />} title="No active keys yet" action={<Link to="/keys/new" className="btn btn-primary"><IconPlus />Create a key</Link>}>
                  A hub key is a scoped <code className="mono">ph_</code> credential. Once one exists, its spend against its cap shows here.
                </EmptyState>
              ) : (
                <ul className="bars" aria-label="Spend against cap per key" style={{ padding: 0 }}>
                  {keyRows.map(({ k, used }) => (
                    <li key={k.id} style={{ gridTemplateColumns: "minmax(0, 0.9fr) minmax(0, 2fr)", alignItems: "center", padding: "12px 16px" }}>
                      <span className="b-name truncate">
                        <Link to={`/keys?key=${k.id}`} className="strong" style={{ textDecoration: "underline", textDecorationColor: "var(--line-2)", textUnderlineOffset: 3 }}>{k.name}</Link>
                        <small>{k.paused ? "paused, " : ""}per {k.spend_period}</small>
                      </span>
                      {spend.loading && !spend.data ? <span className="skel" style={{ height: 8 }} aria-hidden="true" /> : (
                        <Meter used={used} cap={k.spend_cap_usd} projected={projectedSpend(used, k.spend_period)} label={`${k.name} spend against its ${k.spend_period} cap`} />
                      )}
                    </li>
                  ))}
                </ul>
              )}
              <div className="tbl-foot">Notches mark 70% and 90%. A dotted tick shows where the current pace lands by the reset. Spend excludes manual adjustments.</div>
            </section>
            <section className="rise" style={{ ["--i" as string]: 2 }} aria-labelledby="protects">
              <h2 className="caption" id="protects" style={{ marginBottom: 10 }}>What a hub key protects</h2>
              <TrustFlow activeKeys={Math.max(data.active_key_count, data.recent_keys.filter(k => k.active).length)} stacked />
            </section>
          </div>

          <section className="panel rise" style={{ ["--i" as string]: 3 }} aria-labelledby="activity">
            <div className="panel-head">
              <h2 id="activity">Recent activity</h2>
              <span className="sub">{data.recent_usage.length} newest calls</span>
              <div className="push"><Link to="/analytics" className="btn btn-sm btn-ghost">Analytics</Link></div>
            </div>
            {data.recent_usage.length === 0 ? (
              <EmptyState icon={<IconActivity />} title="No calls yet" action={<Link to="/keys" className="btn">Open keys</Link>}>
                Once a hub key calls <code className="mono">/v1/*</code>, each request lands here with its model, tokens, cost and latency.
              </EmptyState>
            ) : <ActivityTable rows={data.recent_usage} />}
          </section>
        </div>
      )}
    </div>
  );
}
