import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { EmptyState } from "../components/EmptyState";
import { EndpointTag } from "../components/EndpointTag";
import { StatCard } from "../components/StatCard";
import { TrustFlow } from "../components/TrustFlow";
import {
  IconActivity, IconAlert, IconCheck, IconChevronRight,
  IconDollar, IconKey, IconPlus,
} from "../icons";
import type { CurrentUser, Overview } from "../types";

function timeAgo(iso: string): string {
  const d = new Date(iso);
  const sec = Math.floor((Date.now() - d.getTime()) / 1000);
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
  return d.toLocaleDateString();
}

export function Dashboard({ user }: { user: CurrentUser }) {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.overview()
      .then(setData)
      .catch(e => setError(String(e)));
  }, []);

  if (error) {
    return (
      <div className="container">
        <EmptyState icon={<IconAlert />} title="Couldn't load overview">{error}</EmptyState>
      </div>
    );
  }

  const stats = data ?? {
    spend_24h: 0, active_key_count: 0, total_call_count: 0,
    recent_usage: [], recent_keys: [],
  };

  return (
    <div className="container">
      <div className="page-head">
        <div className="grow">
          <h1 className="page-title">Overview</h1>
          <p className="page-sub">
            Live, metered traffic for <strong>{user.email}</strong> over the last 24 hours.
          </p>
        </div>
        <Link to="/keys" className="btn btn-primary"><IconPlus />New hub key</Link>
      </div>

      <div className="stat-grid mb24">
        <StatCard
          icon={<IconDollar />}
          label="Spend · last 24h"
          value={<>$<span>{stats.spend_24h.toFixed(4)}</span></>}
          meta={<span>across {stats.recent_usage.length} metered call{stats.recent_usage.length !== 1 ? "s" : ""}</span>}
        />
        <StatCard
          icon={<IconKey />}
          label="Active hub keys"
          value={stats.active_key_count}
          meta={<Link to="/keys" style={{ color: "var(--accent-strong)", fontWeight: 600 }}>manage →</Link>}
        />
        <StatCard
          icon={<IconActivity />}
          label="Recent calls"
          value={stats.recent_usage.length}
          meta="newest first · live feed"
        />
      </div>

      <div className="mb24">
        <div className="row between" style={{ marginBottom: 12 }}>
          <h2 className="section-title">What a hub key protects</h2>
          <Link to="/keys" className="row" style={{
            gap: 4, color: "var(--text-3)", fontSize: 12.5, fontWeight: 600,
          }}>
            Manage keys <IconChevronRight style={{ width: 14, height: 14 }} />
          </Link>
        </div>
        <TrustFlow activeKeys={stats.active_key_count} />
      </div>

      <div className="grid-dash">
        <div className="card">
          <div className="card-head">
            <h3>Recent activity</h3>
            <span className="sub">metered calls</span>
          </div>
          <div className="table-wrap">
            {stats.recent_usage.length === 0 ? (
              <EmptyState icon={<IconActivity />} title="No calls yet">
                Once a hub key calls <code className="mono">/v1/*</code>, it'll show up here with model, tokens, cost and latency.
              </EmptyState>
            ) : (
              <table className="tbl">
                <thead>
                  <tr>
                    <th>Model</th>
                    <th>Endpoint</th>
                    <th className="num">Tokens</th>
                    <th className="num">Cost</th>
                    <th className="num">Latency</th>
                    <th>Status</th>
                    <th>When</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.recent_usage.map(u => (
                    <tr key={u.id}>
                      <td className="strong mono" style={{ fontSize: 12.5 }}>{u.model}</td>
                      <td><EndpointTag endpoint={u.endpoint} /></td>
                      <td className="num mono tnum faint">{u.total_tokens.toLocaleString()}</td>
                      <td className="num mono tnum cost-pos">${u.cost_usd.toFixed(4)}</td>
                      <td className="num mono tnum lat-ok">{u.latency_ms}ms</td>
                      <td>
                        {u.status === "ok" ? (
                          <span className="status-ok row" style={{ gap: 5, fontWeight: 600, fontSize: 12.5 }}>
                            <IconCheck style={{ width: 13, height: 13 }} />ok
                          </span>
                        ) : (
                          <span className="status-err row" style={{ gap: 5, fontWeight: 600, fontSize: 12.5 }}>
                            <IconAlert style={{ width: 13, height: 13 }} />{u.status}
                          </span>
                        )}
                      </td>
                      <td className="faint" style={{ whiteSpace: "nowrap", fontSize: 12.5 }}>
                        {timeAgo(u.timestamp)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        <div className="card card-pad">
          <div className="row between" style={{ marginBottom: 6 }}>
            <h3 style={{ margin: 0, fontSize: 14, fontWeight: 700 }}>Your hub keys</h3>
            <Link to="/keys" className="faint" style={{ fontSize: 12.5, fontWeight: 600 }}>View all</Link>
          </div>
          {stats.recent_keys.length === 0 ? (
            <EmptyState icon={<IconKey />} title="No hub keys yet">
              Create a scoped <code className="mono">ph_…</code> key to start metering traffic.
            </EmptyState>
          ) : (
            <div className="keylist">
              {stats.recent_keys.slice(0, 6).map(k => (
                <div className="keylist-item" key={k.id}>
                  <span className={`kdot ${k.active ? "live" : "dead"}`}></span>
                  <div className="grow" style={{ minWidth: 0 }}>
                    <div className="row" style={{ gap: 8 }}>
                      <span className="strong" style={{ fontWeight: 600, fontSize: 13 }}>{k.name}</span>
                    </div>
                    <div className="mono faint" style={{ fontSize: 11.5, marginTop: 1 }}>
                      {k.allowed_models.length} model{k.allowed_models.length !== 1 ? "s" : ""}
                      {k.allowed_models.length === 0 && " · any"}
                    </div>
                  </div>
                  <div className="right">
                    <div className="mono tnum" style={{ fontSize: 12.5, fontWeight: 600 }}>
                      ${k.daily_spend_cap_usd.toFixed(2)}
                    </div>
                    <div className="faint" style={{ fontSize: 11 }}>cap / day</div>
                  </div>
                </div>
              ))}
            </div>
          )}
          <Link to="/keys" className="btn btn-block mt16"><IconPlus />Create a key</Link>
        </div>
      </div>
    </div>
  );
}
