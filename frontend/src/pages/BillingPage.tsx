import { Fragment, useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { EmptyState } from "../components/EmptyState";
import { IconAlert, IconDollar, IconRefresh } from "../icons";
import type { BillingReconciliation, BillingStatus } from "../types";

const PERIODS = ["day", "week", "month"] as const;
type Period = (typeof PERIODS)[number];

const usd = (v: number | null) => (v == null ? "—" : `$${v < 1 ? v.toFixed(4) : v.toFixed(2)}`);
const signed = (v: number | null) => (v == null ? "—" : `${v > 0 ? "+" : v < 0 ? "-" : ""}${usd(Math.abs(v))}`);

const LABEL: Record<BillingStatus, string> = {
  ok: "In line",
  mismatch: "Mismatch",
  not_configured: "Not configured",
  error: "Error",
  not_comparable: "Not comparable",
  balance_only: "Balance only",
  unsupported: "Unsupported",
};
const BADGE: Record<BillingStatus, string> = {
  ok: "badge-live",
  mismatch: "badge-danger",
  error: "badge-danger",
  not_configured: "badge-revoked",
  not_comparable: "badge-warn",
  balance_only: "badge-revoked",
  unsupported: "badge-revoked",
};

const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });

export function BillingPage() {
  const [period, setPeriod] = useState<Period>("month");
  const [data, setData] = useState<BillingReconciliation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState<string | null>(null);

  const load = useCallback((refresh: boolean) => {
    setLoading(true);
    setError(null);
    api.billingReconciliation(period, refresh)
      .then(setData)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, [period]);

  useEffect(() => load(false), [load]);

  const rows = data?.providers ?? [];
  const nothingConfigured = !!data && rows.length > 0 && rows.every(r => r.status === "not_configured");

  return (
    <div className="container">
      <div className="page-head">
        <div className="grow">
          <h1 className="page-title">Billing</h1>
          <p className="page-sub">
            Spend the hub recorded vs. what providers say was billed
            {data && <> ({day(data.window_start)} to {day(data.window_end)}, UTC)</>}.
          </p>
        </div>
        <div className="seg" role="radiogroup" aria-label="Period">
          {PERIODS.map(p => (
            <button
              key={p} type="button" role="radio" aria-checked={period === p}
              className={period === p ? "on" : ""} onClick={() => setPeriod(p)}
            >
              {p}
            </button>
          ))}
        </div>
        <button type="button" className="btn" disabled={loading} onClick={() => load(true)}>
          <IconRefresh />{loading ? "Refreshing" : "Refresh"}
        </button>
      </div>

      {error && <EmptyState icon={<IconAlert />} title="Couldn't load billing">{error}</EmptyState>}

      {data && data.summary.mismatches > 0 && (
        <div className="card card-pad mb16 status-err" role="alert">
          {data.summary.mismatches} provider{data.summary.mismatches > 1 ? "s differ" : " differs"} from the hub's
          records by more than {data.tolerance.pct}% and ${data.tolerance.abs_usd}.
        </div>
      )}

      {nothingConfigured && (
        <div className="card card-pad mb16">
          No billing sources are configured, so nothing can be compared yet. Set{" "}
          <code className="mono">OPENAI_ADMIN_KEY</code> or <code className="mono">ANTHROPIC_ADMIN_KEY</code> (organization
          admin keys, not ordinary API keys) in the hub's environment.
        </div>
      )}

      {data && rows.length === 0 && (
        <EmptyState icon={<IconDollar />} title="Nothing to reconcile">
          No hub spend in this window and no billing source configured.
        </EmptyState>
      )}

      {rows.length > 0 && (
        <div className="card">
          <div className="table-wrap">
            <table className="tbl">
              <thead>
                <tr>
                  <th>Provider</th>
                  <th>Status</th>
                  <th className="num">Hub</th>
                  <th className="num">Provider</th>
                  <th className="num">Difference</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map(r => (
                  <Fragment key={r.provider}>
                    <tr style={r.status === "mismatch" ? { background: "var(--danger-soft)" } : undefined}>
                      <td className="strong mono" style={{ fontSize: 12.5 }}>{r.provider}</td>
                      <td>
                        <span className={`badge ${BADGE[r.status]}`} title={r.error ?? undefined}>
                          {LABEL[r.status]}
                        </span>
                      </td>
                      <td className="num mono tnum">{usd(r.hub_usd)}</td>
                      <td className="num mono tnum">
                        {r.status === "balance_only"
                          ? <span title="Account balance">bal. {usd(r.balance)}</span>
                          : usd(r.provider_usd)}
                      </td>
                      <td className={`num mono tnum ${r.status === "mismatch" ? "status-err" : "faint"}`}>
                        {signed(r.difference_usd)}
                        {r.difference_pct != null && <> ({r.difference_pct > 0 ? "+" : ""}{r.difference_pct}%)</>}
                      </td>
                      <td className="num">
                        <button
                          type="button" className="btn btn-ghost btn-sm" aria-expanded={open === r.provider}
                          onClick={() => setOpen(open === r.provider ? null : r.provider)}
                        >
                          Notes
                        </button>
                      </td>
                    </tr>
                    {open === r.provider && (
                      <tr>
                        <td colSpan={6} className="faint" style={{ fontSize: 12.5 }}>
                          {r.error && <div className="status-err">{r.error}</div>}
                          <ul style={{ margin: 0, paddingLeft: 18 }}>
                            {r.caveats.map(c => <li key={c}>{c}</li>)}
                          </ul>
                          {r.fetched_at && <div>Fetched {new Date(r.fetched_at).toLocaleString()}</div>}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
