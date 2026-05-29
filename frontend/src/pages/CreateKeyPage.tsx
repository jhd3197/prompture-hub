import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, api } from "../api";
import { ModelGroupedPicker } from "../components/ModelGroupedPicker";
import { useToast } from "../components/Toast";
import {
  IconAlert, IconCheck, IconChevronRight, IconClock, IconKey, IconX,
} from "../icons";
import type { SpendPeriod } from "../types";

const PERIOD_OPTIONS: Array<{ value: SpendPeriod; label: string; resetCopy: string }> = [
  { value: "day", label: "Per day", resetCopy: "resets daily at UTC midnight" },
  { value: "week", label: "Per week", resetCopy: "resets Monday 00:00 UTC" },
  { value: "month", label: "Per month", resetCopy: "resets on the 1st of the month, UTC" },
];

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

export function CreateKeyPage() {
  const navigate = useNavigate();
  const toast = useToast();

  const [name, setName] = useState("");
  const [modelList, setModelList] = useState<string[]>([]);
  const [allowAnyModel, setAllowAnyModel] = useState(false);
  const [period, setPeriod] = useState<SpendPeriod>("day");
  const [cap, setCap] = useState("1");
  const [rate, setRate] = useState("60");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  const onPeriodChange = (next: SpendPeriod) => {
    const oldPresets = SPEND_PRESETS_BY_PERIOD[period];
    const newPresets = SPEND_PRESETS_BY_PERIOD[next];
    const idx = oldPresets.findIndex(p => p.value === cap);
    if (idx >= 0) setCap(newPresets[idx].value);
    setPeriod(next);
  };

  const submit = async () => {
    if (!valid || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const created = await api.createKey({
        name: name.trim(),
        allowed_models: allowAnyModel ? [] : modelList,
        daily_spend_cap_usd: capNumber,
        spend_period: period,
        rate_limit_per_min: rateNumber,
      });
      toast(`Created ${created.name}`);
      // Hand the plaintext off to the /keys page via router state so it
      // can pop the one-time reveal banner. State is gone after the user
      // navigates away — never in a URL.
      navigate("/keys", { replace: true, state: { newKey: created } });
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

  const effectiveModelCount = allowAnyModel ? "any model" : modelList.length === 0
    ? "no models yet — pick at least one or enable Any model"
    : `${modelList.length} model${modelList.length > 1 ? "s" : ""}`;

  return (
    <div className="container">
      {/* breadcrumb */}
      <div
        className="row"
        style={{ gap: 6, color: "var(--text-3)", fontSize: 12.5, marginBottom: 10 }}
      >
        <Link to="/keys" style={{ color: "inherit" }}>Hub keys</Link>
        <IconChevronRight style={{ width: 12, height: 12 }} />
        <span style={{ color: "var(--text)", fontWeight: 600 }}>New key</span>
      </div>

      <div className="page-head">
        <div className="grow">
          <h1 className="page-title">Issue a hub key</h1>
          <p className="page-sub">
            A scoped credential your app sends as a Bearer token. It maps to
            real provider keys without ever exposing them. You'll see the
            plaintext exactly once — copy it before you leave the next page.
          </p>
        </div>
        <Link to="/keys" className="btn btn-ghost">
          <IconX style={{ width: 14, height: 14 }} />Cancel
        </Link>
      </div>

      {error && (
        <div className="discovery-fail mb16" role="alert" style={{
          borderRadius: "var(--r-md)",
          border: "1px solid var(--danger)",
          background: "var(--danger-soft)",
        }}>
          <IconAlert style={{ color: "var(--danger)" }} />
          <span className="mono" style={{ wordBreak: "break-word" }}>{error}</span>
        </div>
      )}

      <div className="grid-dash" style={{ alignItems: "start", gap: 24 }}>
        {/* main form */}
        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          <div className="card card-pad">
            <h2 className="section-title" style={{ marginBottom: 14 }}>Identity</h2>
            <div className="field">
              <label htmlFor="k-name">Key name</label>
              <input
                id="k-name" className="input mono" placeholder="production-web"
                value={name} onChange={e => setName(e.target.value)} autoFocus
              />
              <span className={`hint ${name && !nameOk ? "field-error" : ""}`}>
                Letters, numbers, hyphens, or underscores. Example: <code className="mono">production-web</code>.
              </span>
            </div>
          </div>

          <div className="card card-pad">
            <div className="row between" style={{ marginBottom: 6 }}>
              <h2 className="section-title">Allowed models</h2>
              <span className="faint" style={{ fontSize: 12 }}>{effectiveModelCount}</span>
            </div>

            <label
              className="row"
              style={{
                gap: 10,
                padding: "10px 12px",
                border: "1px solid var(--border)",
                borderRadius: "var(--r-md)",
                background: allowAnyModel ? "var(--accent-softer)" : "var(--surface-2)",
                cursor: "pointer",
                marginBottom: 14,
              }}
            >
              <input
                type="checkbox"
                checked={allowAnyModel}
                onChange={e => setAllowAnyModel(e.target.checked)}
                style={{ accentColor: "var(--accent)" }}
              />
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, fontSize: 13 }}>
                  Allow any model
                </div>
                <div className="faint" style={{ fontSize: 12 }}>
                  Skip the picker — this key will be accepted for any model the
                  hub knows how to route. Useful for trusted apps under your control.
                </div>
              </div>
            </label>

            <div
              style={{
                opacity: allowAnyModel ? 0.45 : 1,
                pointerEvents: allowAnyModel ? "none" : "auto",
              }}
            >
              <ModelGroupedPicker value={modelList} onChange={setModelList} />
            </div>
          </div>

          <div className="card card-pad">
            <div className="row between" style={{ marginBottom: 14 }}>
              <h2 className="section-title">Safety limits</h2>
              <span className="row" style={{ gap: 6, color: "var(--text-3)", fontSize: 12 }}>
                <IconClock style={{ width: 13, height: 13 }} />{periodCopy}
              </span>
            </div>

            <div className="field" style={{ marginBottom: 16 }}>
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
                  Calls stop once the key reaches this amount for the current {periodSuffix(period)}.
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
          </div>
        </div>

        {/* summary sticky aside */}
        <aside style={{ position: "sticky", top: 80 }}>
          <div className="card card-pad">
            <h2 className="section-title" style={{ marginBottom: 12 }}>Summary</h2>

            <dl
              style={{
                display: "grid",
                gridTemplateColumns: "auto 1fr",
                gap: "8px 12px",
                margin: 0,
                fontSize: 13,
              }}
            >
              <dt className="faint">Name</dt>
              <dd style={{ margin: 0, fontWeight: 600 }}>
                {name || <span className="faint">—</span>}
              </dd>

              <dt className="faint">Models</dt>
              <dd style={{ margin: 0 }}>
                {allowAnyModel
                  ? <span style={{ fontWeight: 600 }}>any</span>
                  : modelList.length === 0
                    ? <span className="faint">none yet</span>
                    : <span style={{ fontWeight: 600 }}>{modelList.length} selected</span>}
              </dd>

              <dt className="faint">Budget</dt>
              <dd style={{ margin: 0, fontWeight: 600 }}>{capSummary}</dd>

              <dt className="faint">Rate</dt>
              <dd style={{ margin: 0, fontWeight: 600 }}>{rateSummary}</dd>

              <dt className="faint">Resets</dt>
              <dd style={{ margin: 0, fontSize: 12.5 }}>{periodCopy}</dd>
            </dl>

            <div className="policy-summary" role="status" style={{ marginTop: 16 }}>
              <IconCheck />
              <span>
                This key stops at <strong>{capSummary}</strong> and allows{" "}
                <strong>{rateSummary}</strong>.
              </span>
            </div>

            <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
              <Link to="/keys" className="btn btn-ghost" style={{ flex: 1 }}>
                Cancel
              </Link>
              <button
                className="btn btn-primary"
                onClick={submit}
                disabled={!valid || submitting || (!allowAnyModel && modelList.length === 0)}
                style={{ flex: 2 }}
              >
                <IconKey />{submitting ? "Creating…" : "Create key"}
              </button>
            </div>

            {!allowAnyModel && modelList.length === 0 && (
              <p className="hint field-error" style={{ marginTop: 10, fontSize: 12 }}>
                Pick at least one model or enable <strong>Allow any model</strong>.
              </p>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
