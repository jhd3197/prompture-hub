import { useEffect, useState } from "react";
import { ApiError, api } from "../api";
import { CopyButton } from "../components/CopyButton";
import { EmptyState } from "../components/EmptyState";
import { KeyStatus } from "../components/KeyStatus";
import { ModelMultiSelect } from "../components/ModelMultiSelect";
import { Modal } from "../components/Modal";
import { useToast } from "../components/Toast";
import {
  IconAlert, IconCheck, IconChevronDown, IconClock, IconKey, IconLock,
  IconPlus, IconTrash,
} from "../icons";
import type { CreatedKey, HubKey, SpendPeriod } from "../types";

const PERIOD_OPTIONS: Array<{ value: SpendPeriod; label: string; resetCopy: string }> = [
  { value: "day", label: "Per day", resetCopy: "resets daily at UTC midnight" },
  { value: "week", label: "Per week", resetCopy: "resets Monday 00:00 UTC" },
  { value: "month", label: "Per month", resetCopy: "resets on the 1st of the month, UTC" },
];

// Period-aware spend presets. Same "shape" of choices (testing / small / prod)
// translated into amounts that make sense at that timescale.
const SPEND_PRESETS_BY_PERIOD: Record<SpendPeriod, Array<{ value: string; note: string }>> = {
  day:   [{ value: "1",   note: "testing" }, { value: "5",   note: "small app" }, { value: "20",  note: "production" }],
  week:  [{ value: "5",   note: "testing" }, { value: "25",  note: "small app" }, { value: "100", note: "production" }],
  month: [{ value: "20",  note: "testing" }, { value: "100", note: "small app" }, { value: "500", note: "production" }],
};

const RATE_PRESETS = [
  { label: "30/min", value: "30", note: "1 every 2s" },
  { label: "60/min", value: "60", note: "default · 1/s" },
  { label: "300/min", value: "300", note: "burst" },
] as const;

function periodSuffix(p: SpendPeriod): string {
  return p === "day" ? "day" : p === "week" ? "week" : "month";
}

function CreateKeyModal({
  onClose, onCreated,
}: {
  onClose: () => void;
  onCreated: (k: CreatedKey) => void;
}) {
  const [name, setName] = useState("");
  const [modelList, setModelList] = useState<string[]>([]);
  const [period, setPeriod] = useState<SpendPeriod>("day");
  const [cap, setCap] = useState("1");
  const [rate, setRate] = useState("60");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();

  const nameOk = /^[a-z0-9][a-z0-9-_]{0,99}$/i.test(name);
  const capNumber = Number(cap);
  const rateNumber = Number(rate);
  const capOk = Number.isFinite(capNumber) && capNumber > 0;
  const rateOk = Number.isInteger(rateNumber) && rateNumber >= 1;
  const valid = nameOk && capOk && rateOk;
  const capSummary = capOk
    ? `$${capNumber.toFixed(2)}/${periodSuffix(period)}`
    : `$1.00/${periodSuffix(period)}`;
  const rateSummary = rateOk ? `${rateNumber}/min` : "60/min";
  const periodCopy = PERIOD_OPTIONS.find(o => o.value === period)?.resetCopy ?? "";

  // Swap the cap to the nearest preset for this period when the user
  // switches periods, so the dollar amount tracks the timescale (testing
  // is testing whether per-day or per-month).
  const onPeriodChange = (next: SpendPeriod) => {
    const oldPresets = SPEND_PRESETS_BY_PERIOD[period];
    const newPresets = SPEND_PRESETS_BY_PERIOD[next];
    const idx = oldPresets.findIndex(p => p.value === cap);
    if (idx >= 0) {
      setCap(newPresets[idx].value);
    }
    setPeriod(next);
  };

  const submit = async () => {
    if (!valid || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const created = await api.createKey({
        name: name.trim(),
        allowed_models: modelList,
        daily_spend_cap_usd: capNumber,
        spend_period: period,
        rate_limit_per_min: rateNumber,
      });
      toast(`Created ${created.name}`);
      onCreated(created);
    } catch (e) {
      const msg = e instanceof ApiError
        ? (typeof e.body === "object" && e.body && "detail" in e.body
            ? String((e.body as { detail: unknown }).detail)
            : e.message)
        : String(e);
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title="Create a hub key"
      wide
      desc="A scoped credential your app sends as a Bearer token. It maps to real provider keys without ever exposing them."
      onClose={onClose}
      footer={<>
        <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" onClick={submit} disabled={!valid || submitting}>
          <IconKey />{submitting ? "Creating…" : "Create key"}
        </button>
      </>}
    >
      {error && (
        <div className="discovery-fail" role="alert" style={{
          borderRadius: "var(--r-md)",
          border: "1px solid var(--danger)",
          background: "var(--danger-soft)",
        }}>
          <IconAlert />
          <span className="mono">{error}</span>
        </div>
      )}

      <div className="field">
        <label htmlFor="k-name">Key name</label>
        <input
          id="k-name" className="input mono" placeholder="production-web"
          value={name} onChange={e => setName(e.target.value)} autoFocus
        />
        <span className={`hint ${name && !nameOk ? "field-error" : ""}`}>
          Use letters, numbers, hyphens, or underscores. Example: production-web.
        </span>
      </div>

      <div className="field">
        <label htmlFor="k-models">
          Allowed models <span className="faint" style={{ fontWeight: 500 }}>(empty = any)</span>
        </label>
        <ModelMultiSelect
          value={modelList}
          onChange={setModelList}
          placeholder="openai/gpt-4o"
        />
        <span className="hint">
          {modelList.length === 0
            ? "Pick from the dropdown, or type a model id and press Enter. Leave empty to allow any model."
            : <>This key will be able to call <strong style={{ color: "var(--text)" }}>{modelList.length}</strong> model{modelList.length > 1 ? "s" : ""}.</>}
        </span>
      </div>

      <div className="limit-builder">
        <div className="limit-intro">
          <div>
            <div className="limit-kicker">Safety limits</div>
            <div className="limit-title">Spend budget and request pace</div>
          </div>
          <span className="limit-reset"><IconClock />{periodCopy}</span>
        </div>

        <div className="field" style={{ marginBottom: 14 }}>
          <div className="field-row">
            <label>Reset window</label>
            <span className="mini-note">when the budget refreshes</span>
          </div>
          <div className="seg" role="radiogroup" aria-label="Spend period">
            {PERIOD_OPTIONS.map(opt => (
              <button
                key={opt.value}
                type="button"
                role="radio"
                aria-checked={period === opt.value}
                className={period === opt.value ? "on" : ""}
                onClick={() => onPeriodChange(opt.value)}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        <div className="grid-2">
          <div className="field key-limit-field">
            <div className="field-row">
              <label htmlFor="k-cap">Spend budget</label>
              <span className="mini-note">hard stop · per {periodSuffix(period)}</span>
            </div>
            <div className="preset-row" aria-label="Spend budget presets">
              {SPEND_PRESETS_BY_PERIOD[period].map(p => (
                <button
                  key={p.value}
                  type="button"
                  className={`preset-btn ${cap === p.value ? "on" : ""}`}
                  onClick={() => setCap(p.value)}
                >
                  <strong>${p.value}/{periodSuffix(period)}</strong>
                  <span>{p.note}</span>
                </button>
              ))}
            </div>
            <div className="input-prefix">
              <span className="pfx mono">$</span>
              <input
                id="k-cap" type="number" min="0.01" step="0.01"
                className="input mono tnum"
                value={cap} onChange={e => setCap(e.target.value)}
                aria-invalid={!capOk}
              />
            </div>
            <span className={`hint ${cap && !capOk ? "field-error" : ""}`}>
              Calls stop once the key reaches this amount for {periodCopy.replace(/^resets /, "the current ")}.
            </span>
          </div>
          <div className="field key-limit-field">
            <div className="field-row">
              <label htmlFor="k-rate">Rate limit</label>
              <span className="mini-note">per key</span>
            </div>
            <div className="preset-row" aria-label="Rate limit presets">
              {RATE_PRESETS.map(p => (
                <button
                  key={p.value}
                  type="button"
                  className={`preset-btn ${rate === p.value ? "on" : ""}`}
                  onClick={() => setRate(p.value)}
                >
                  <strong>{p.label}</strong>
                  <span>{p.note}</span>
                </button>
              ))}
            </div>
            <div className="input-suffix">
              <input
                id="k-rate" type="number" min="1" step="1"
                className="input mono tnum"
                value={rate} onChange={e => setRate(e.target.value)}
                aria-invalid={!rateOk}
              />
              <span className="sfx mono">req/min</span>
            </div>
            <span className={`hint ${rate && !rateOk ? "field-error" : ""}`}>
              60/min is a good default for one app.
            </span>
          </div>
        </div>

        <div className="policy-summary" role="status">
          <IconCheck />
          <span>
            This key stops at <strong>{capSummary}</strong> and allows{" "}
            <strong>{rateSummary}</strong>. Budget {periodCopy}.
          </span>
        </div>
      </div>
    </Modal>
  );
}

function RevealKeyModal({
  created, onClose,
}: {
  created: CreatedKey;
  onClose: () => void;
}) {
  return (
    <Modal
      title="Copy your key now"
      onClose={onClose}
      footer={<button className="btn btn-primary" onClick={onClose}>I've stored it safely</button>}
    >
      <div
        className="discovery-fail"
        style={{
          border: "1px solid var(--accent)",
          background: "var(--accent-soft)",
          borderRadius: "var(--r-md)",
          color: "var(--text)",
        }}
      >
        <IconLock style={{ color: "var(--accent-strong)" }} />
        <span>
          This is the <strong>only time</strong> <code className="mono">{created.name}</code>'s secret is shown.
          We store a SHA-256 hash — if you lose it, you'll have to roll a new key.
        </span>
      </div>
      <div className="reveal-key">{created.key}</div>
      <CopyButton text={created.key} label="Copy key" className="btn btn-primary btn-block btn-lg" />
    </Modal>
  );
}

function RevokeKeyModal({
  k, onClose, onConfirm,
}: {
  k: HubKey;
  onClose: () => void;
  onConfirm: () => void;
}) {
  return (
    <Modal
      title={`Revoke ${k.name}?`}
      onClose={onClose}
      desc="Any app using this key will start getting 401s immediately. This does not touch your real provider keys — they keep working for every other hub key."
      footer={<>
        <button className="btn btn-ghost" onClick={onClose}>Keep it</button>
        <button className="btn btn-danger" onClick={onConfirm}>
          <IconTrash />Revoke key
        </button>
      </>}
    >
      <div className="row" style={{
        gap: 10, padding: "12px 14px",
        background: "var(--danger-soft)", borderRadius: "var(--r-md)",
      }}>
        <span className="kdot dead"></span>
        <div>
          <div className="mono strong" style={{ fontWeight: 600 }}>{k.name} · key #{k.id}</div>
          <div className="faint" style={{ fontSize: 12 }}>
            {k.allowed_models.length} model{k.allowed_models.length !== 1 ? "s" : ""} · ${k.daily_spend_cap_usd.toFixed(2)}/{periodSuffix(k.spend_period)} cap
          </div>
        </div>
      </div>
    </Modal>
  );
}

function KeyRow({ k, onRevoke }: { k: HubKey; onRevoke: (k: HubKey) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <tr>
        <td>
          <div className="row" style={{ gap: 10 }}>
            <span className={`kdot ${k.active ? "live" : "dead"}`}></span>
            <div>
              <div className="strong" style={{ fontWeight: 600, fontSize: 13.5 }}>{k.name}</div>
              <div className="mono faint" style={{ fontSize: 11.5 }}>key #{k.id}</div>
            </div>
          </div>
        </td>
        <td>
          {k.allowed_models.length === 0 ? (
            <span className="faint" style={{ fontStyle: "italic" }}>any</span>
          ) : (
            <button
              className="filter-chip"
              style={{ fontSize: 11.5 }}
              onClick={() => setOpen(o => !o)}
              aria-expanded={open}
            >
              {k.allowed_models.length} model{k.allowed_models.length !== 1 ? "s" : ""}
              <IconChevronDown style={{
                width: 12, height: 12,
                transform: open ? "rotate(180deg)" : "none",
                transition: "transform .15s",
              }} />
            </button>
          )}
        </td>
        <td className="num mono tnum">
          ${k.daily_spend_cap_usd.toFixed(2)}<span className="faint" style={{ fontSize: 11 }}>/{periodSuffix(k.spend_period)}</span>
        </td>
        <td className="num mono tnum faint">{k.rate_limit_per_min}/min</td>
        <td className="faint mono" style={{ whiteSpace: "nowrap", fontSize: 12.5 }}>
          {new Date(k.created_at).toLocaleDateString()}
        </td>
        <td><KeyStatus active={k.active} /></td>
        <td className="num">
          {k.active ? (
            <button className="btn btn-sm btn-danger" onClick={() => onRevoke(k)}>
              <IconTrash />Revoke
            </button>
          ) : (
            <span className="faint" style={{ fontSize: 12 }}>
              revoked {k.revoked_at && new Date(k.revoked_at).toLocaleDateString()}
            </span>
          )}
        </td>
      </tr>
      {open && k.allowed_models.length > 0 && (
        <tr>
          <td colSpan={7} style={{ background: "var(--surface-2)", padding: "12px 16px" }}>
            <div className="row wrap" style={{ gap: 6 }}>
              <span className="faint" style={{ fontSize: 12, marginRight: 4 }}>Whitelisted:</span>
              {k.allowed_models.map(m => (
                <span key={m} className="cap" style={{ fontFamily: "var(--font-mono)" }}>{m}</span>
              ))}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export function KeysPage() {
  const [keys, setKeys] = useState<HubKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [reveal, setReveal] = useState<CreatedKey | null>(null);
  const [revoking, setRevoking] = useState<HubKey | null>(null);
  const toast = useToast();

  const refresh = async () => {
    setLoading(true);
    try {
      setKeys(await api.listKeys());
      setLoadError(null);
    } catch (e) {
      setLoadError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { refresh(); }, []);

  const confirmRevoke = async () => {
    if (!revoking) return;
    try {
      await api.revokeKey(revoking.id);
      toast(`Revoked ${revoking.name} — access killed instantly`);
      setRevoking(null);
      await refresh();
    } catch (e) {
      toast(`Couldn't revoke: ${e}`);
    }
  };

  const handleCreated = async (k: CreatedKey) => {
    setShowCreate(false);
    setReveal(k);
    await refresh();
  };

  const active = keys.filter(k => k.active);

  return (
    <div className="container">
      <div className="page-head">
        <div className="grow">
          <h1 className="page-title">Hub keys</h1>
          <p className="page-sub">
            Scoped credentials your apps use. Each maps to real provider keys it can never see —
            and you can revoke any one instantly.
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
          <IconPlus />New hub key
        </button>
      </div>

      <div className="card">
        <div className="card-head">
          <h3>All keys</h3>
          <span className="sub">
            {active.length} active · {keys.length} total
          </span>
        </div>

        {loadError ? (
          <EmptyState icon={<IconAlert />} title="Couldn't load keys">{loadError}</EmptyState>
        ) : loading ? (
          <div className="empty"><p>Loading…</p></div>
        ) : keys.length === 0 ? (
          <EmptyState
            icon={<IconKey />}
            title="No hub keys yet"
            action={
              <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
                <IconPlus />Create your first key
              </button>
            }
          >
            A hub key is a disposable <code className="mono">ph_…</code> credential you hand to an app.
            It carries a model whitelist, a daily spend cap and a rate limit — so the real provider keys stay locked away here.
          </EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="tbl">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Models</th>
                  <th className="num">Spend cap</th>
                  <th className="num">Rate</th>
                  <th>Created</th>
                  <th>Status</th>
                  <th className="num">Action</th>
                </tr>
              </thead>
              <tbody>
                {keys.map(k => <KeyRow key={k.id} k={k} onRevoke={setRevoking} />)}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <p className="muted mt16" style={{ fontSize: 12.5 }}>
        <IconLock style={{ width: 13, height: 13, verticalAlign: "-2px", marginRight: 5 }} />
        Secrets are stored as hashes. The plaintext is shown once at creation — after that, only the prefix is recoverable.
      </p>

      {showCreate && <CreateKeyModal onClose={() => setShowCreate(false)} onCreated={handleCreated} />}
      {reveal && <RevealKeyModal created={reveal} onClose={() => setReveal(null)} />}
      {revoking && (
        <RevokeKeyModal
          k={revoking}
          onClose={() => setRevoking(null)}
          onConfirm={confirmRevoke}
        />
      )}
    </div>
  );
}
