import { useEffect, useState } from "react";
import { ApiError, api } from "../api";
import { CopyButton } from "../components/CopyButton";
import { EmptyState } from "../components/EmptyState";
import { KeyStatus } from "../components/KeyStatus";
import { ModelMultiSelect } from "../components/ModelMultiSelect";
import { Modal } from "../components/Modal";
import { useToast } from "../components/Toast";
import {
  IconAlert, IconChevronDown, IconKey, IconLock, IconPlus, IconTrash,
} from "../icons";
import type { CreatedKey, HubKey } from "../types";

function CreateKeyModal({
  onClose, onCreated,
}: {
  onClose: () => void;
  onCreated: (k: CreatedKey) => void;
}) {
  const [name, setName] = useState("");
  const [modelList, setModelList] = useState<string[]>([]);
  const [cap, setCap] = useState("1");
  const [rate, setRate] = useState("60");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();

  const nameOk = /^[a-z0-9][a-z0-9-_]{0,99}$/i.test(name);
  const valid = nameOk;

  const submit = async () => {
    if (!valid || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const created = await api.createKey({
        name: name.trim(),
        allowed_models: modelList,
        daily_spend_cap_usd: Number(cap),
        rate_limit_per_min: Number(rate),
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
        <span className="hint">A label only you see — pick something that maps to where it's used.</span>
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

      <div className="grid-2">
        <div className="field">
          <label htmlFor="k-cap">Daily spend cap</label>
          <div className="input-prefix">
            <span className="pfx mono">$</span>
            <input
              id="k-cap" type="number" min="0" step="0.01"
              className="input mono tnum"
              value={cap} onChange={e => setCap(e.target.value)}
            />
          </div>
          <span className="hint">Calls refused for the rest of the UTC day once hit.</span>
        </div>
        <div className="field">
          <label htmlFor="k-rate">Rate limit</label>
          <input
            id="k-rate" type="number" min="1" step="1"
            className="input mono tnum"
            value={rate} onChange={e => setRate(e.target.value)}
          />
          <span className="hint">Requests per minute (per key).</span>
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
            {k.allowed_models.length} model{k.allowed_models.length !== 1 ? "s" : ""} · ${k.daily_spend_cap_usd.toFixed(2)}/day cap
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
          ${k.daily_spend_cap_usd.toFixed(2)}<span className="faint" style={{ fontSize: 11 }}>/day</span>
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
