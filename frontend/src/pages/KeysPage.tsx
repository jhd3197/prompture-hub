import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";
import { CopyButton } from "../components/CopyButton";
import { EmptyState } from "../components/EmptyState";
import { KeyStatus } from "../components/KeyStatus";
import { Modal } from "../components/Modal";
import { useToast } from "../components/Toast";
import {
  IconAlert, IconChevronDown, IconKey, IconLock, IconPlus, IconTrash,
} from "../icons";
import type { CreatedKey, HubKey, SpendPeriod } from "../types";

function periodSuffix(p: SpendPeriod): string {
  return p === "day" ? "day" : p === "week" ? "week" : "month";
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
  const [reveal, setReveal] = useState<CreatedKey | null>(null);
  const [revoking, setRevoking] = useState<HubKey | null>(null);
  const toast = useToast();
  const location = useLocation();
  const navigate = useNavigate();

  // The CreateKeyPage hands the plaintext off via router state when it
  // redirects here. Pop the reveal modal once and clear the state so a
  // browser refresh doesn't re-show it.
  useEffect(() => {
    const st = location.state as { newKey?: CreatedKey } | null;
    if (st?.newKey) {
      setReveal(st.newKey);
      navigate(location.pathname, { replace: true, state: null });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  // Re-fetch keys once the reveal modal closes so the new row appears
  // in the table.
  useEffect(() => {
    if (reveal) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reveal]);

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
        <Link to="/keys/new" className="btn btn-primary">
          <IconPlus />New hub key
        </Link>
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
              <Link to="/keys/new" className="btn btn-primary">
                <IconPlus />Create your first key
              </Link>
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
