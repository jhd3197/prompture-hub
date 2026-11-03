import { useRef, useState } from "react";
import { api } from "../api";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { Num } from "../components/Num";
import { PageHead } from "../components/PageHead";
import { SkelReadouts, SkelRows } from "../components/Skeleton";
import { IconAlert, IconChevronDown, IconDollar, IconRefresh } from "../icons";
import { dateTime, plural, signedUsd, usd } from "../util/format";
import { useAsync } from "../util/hooks";
import type { BillingProvider, BillingStatus } from "../types";

const PERIODS = ["day", "week", "month"] as const;
type Period = (typeof PERIODS)[number];

const LABEL: Record<BillingStatus, string> = {
  ok: "In line", mismatch: "Mismatch", not_configured: "Not configured", error: "Error",
  not_comparable: "Not comparable", balance_only: "Balance only", unsupported: "Unsupported",
};
const CHIP: Record<BillingStatus, string> = {
  ok: "chip-ok", mismatch: "chip-bad", error: "chip-bad", not_configured: "chip-mute",
  not_comparable: "chip-warn", balance_only: "chip-mute", unsupported: "chip-mute",
};

const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });

function DeltaRow({ r, scale }: { r: BillingProvider; scale: number }) {
  const [open, setOpen] = useState(false);
  const hasProv = r.provider_usd != null;
  const hasNotes = r.caveats.length > 0 || !!r.error || !!r.fetched_at;
  const bad = r.status === "mismatch";
  return (
    <li style={bad ? { background: "var(--red-wash)" } : undefined}>
      <div className="delta-head">
        <span className="d-name">{r.provider}</span>
        <span className={`chip ${CHIP[r.status]}`} title={r.error ?? undefined}>{LABEL[r.status]}</span>
        {r.difference_usd != null && (
          <span className={`d-diff ${bad ? "status-err" : "faint"}`}>
            {signedUsd(r.difference_usd)}
            {r.difference_pct != null && <> ({r.difference_pct > 0 ? "+" : ""}{r.difference_pct}%)</>}
          </span>
        )}
      </div>
      <div className="delta-line">
        <span>Hub</span>
        <span className="d-bar" aria-hidden="true"><span className="d-fill" style={{ ["--p" as string]: scale > 0 ? r.hub_usd / scale : 0 }} /></span>
        <span className="d-val">{usd(r.hub_usd)}</span>
      </div>
      <div className={`delta-line${hasProv ? "" : " is-none"}`}>
        <span>Provider</span>
        <span className="d-bar" aria-hidden="true">{hasProv && <span className="d-fill prov" style={{ ["--p" as string]: scale > 0 ? r.provider_usd! / scale : 0 }} />}</span>
        <span className="d-val">{r.status === "balance_only" ? `bal. ${usd(r.balance)}` : hasProv ? usd(r.provider_usd) : "no figure"}</span>
      </div>
      {hasNotes && (
        <div>
          <button type="button" className="btn btn-ghost btn-sm" aria-expanded={open} onClick={() => setOpen(o => !o)} style={{ marginLeft: -10 }}>
            <IconChevronDown style={{ transform: open ? "rotate(180deg)" : undefined, transition: "transform 240ms var(--settle)" }} />Notes
          </button>
          {open && (
            <div className="faint" style={{ fontSize: "var(--t-xs)", padding: "4px 0 0" }}>
              {r.error && <div className="status-err">{r.error}</div>}
              <ul style={{ margin: "4px 0", paddingLeft: 18 }}>{r.caveats.map(c => <li key={c}>{c}</li>)}</ul>
              {r.fetched_at && <div>Fetched {dateTime(r.fetched_at)}</div>}
            </div>
          )}
        </div>
      )}
    </li>
  );
}

export function BillingPage() {
  const [period, setPeriod] = useState<Period>("month");
  const force = useRef(false); // Refresh asks the hub to bypass its provider cache once
  const { data, error, loading, reload } = useAsync(() => {
    const refresh = force.current;
    force.current = false;
    return api.billingReconciliation(period, refresh);
  }, [period]);
  const rows = data?.providers ?? [];
  const nothingConfigured = !!data && rows.length > 0 && rows.every(r => r.status === "not_configured");
  const scale = Math.max(...rows.flatMap(r => [r.hub_usd, r.provider_usd ?? 0]), 0);
  const hubTotal = rows.reduce((a, r) => a + r.hub_usd, 0);

  return (
    <div className="container">
      <PageHead
        title="Billing"
        sub={<>Spend the hub recorded against what providers say was billed{data && <> ({day(data.window_start)} to {day(data.window_end)}, UTC)</>}.</>}
      >
        <div className="seg" role="radiogroup" aria-label="Period">
          {PERIODS.map(p => (
            <button key={p} type="button" role="radio" aria-checked={period === p} className={period === p ? "on" : ""} onClick={() => setPeriod(p)}>{p}</button>
          ))}
        </div>
        <button type="button" className="btn" disabled={loading} onClick={() => { force.current = true; reload(); }}>
          <IconRefresh />{loading ? "Refreshing" : "Refresh"}
        </button>
      </PageHead>

      {error && !data ? (
        <div className="panel"><ErrorState title="Couldn't load billing" error={error} onRetry={reload} /></div>
      ) : !data ? (
        <div className="stack" aria-busy="true"><SkelReadouts n={3} /><div className="panel"><SkelRows rows={4} /></div></div>
      ) : (
        <div className="stack" style={{ opacity: loading ? 0.6 : 1, transition: "opacity 160ms" }} aria-busy={loading}>
          {error && <div className="notice bad" role="alert"><IconAlert /><span>Couldn't refresh: {error}. <button type="button" className="btn btn-sm" onClick={reload}>Try again</button></span></div>}
          <div className="readouts rise">
            <div className="readout">
              <span className="caption readout-label"><IconDollar />Hub recorded</span>
              <div className="readout-value"><Num value={hubTotal} format={v => usd(v)} /></div>
              <div className="readout-meta">across {plural(rows.length, "provider")}, this {period}</div>
            </div>
            <div className={`readout${data.summary.mismatches ? " readout-bad" : ""}`}>
              <span className="caption readout-label"><IconAlert />Mismatches</span>
              <div className="readout-value"><Num value={data.summary.mismatches} format={v => String(Math.round(v))} /></div>
              <div className="readout-meta">beyond {data.tolerance.pct}% and ${data.tolerance.abs_usd}</div>
            </div>
            <div className="readout">
              <span className="caption readout-label"><IconAlert />Cannot compare</span>
              <div className="readout-value"><Num value={data.summary.errors + data.summary.unconfigured} format={v => String(Math.round(v))} /></div>
              <div className="readout-meta">{data.summary.errors} errors, {data.summary.unconfigured} not configured</div>
            </div>
          </div>

          {data.summary.mismatches > 0 && (
            <div className="notice bad" role="alert"><IconAlert />
              <span>{plural(data.summary.mismatches, "provider")} differ{data.summary.mismatches === 1 ? "s" : ""} from the hub's records by more than {data.tolerance.pct}% and ${data.tolerance.abs_usd}.</span>
            </div>
          )}
          {nothingConfigured && (
            <div className="notice"><IconAlert />
              <span>No billing sources are configured, so nothing can be compared yet. Set <code className="mono">OPENAI_ADMIN_KEY</code> or <code className="mono">ANTHROPIC_ADMIN_KEY</code> (organization admin keys, not ordinary API keys) in the hub's environment.</span>
            </div>
          )}

          <section className="panel rise" style={{ ["--i" as string]: 1 }} aria-labelledby="recon">
            <div className="panel-head">
              <h2 id="recon">Hub ledger against provider bills</h2>
              <span className="sub">filled bar is the hub, hatched bar is the provider</span>
            </div>
            {rows.length === 0 ? (
              <EmptyState icon={<IconDollar />} title="Nothing to reconcile">
                No hub spend fell in this window and no billing source is configured. Pick a longer period, or set an admin key to compare against a provider.
              </EmptyState>
            ) : (
              <ul className="delta-list" aria-label="Hub spend against provider spend">
                {rows.map(r => <DeltaRow key={r.provider} r={r} scale={scale} />)}
              </ul>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
