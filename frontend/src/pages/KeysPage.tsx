import { Fragment, useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { Meter } from "../components/charts/Meter";
import { CopyButton } from "../components/CopyButton";
import { CopyId } from "../components/CopyId";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { KeyStatus } from "../components/KeyStatus";
import { Menu } from "../components/Menu";
import { Modal } from "../components/Modal";
import { PageHead } from "../components/PageHead";
import { SkelRows } from "../components/Skeleton";
import { useToast } from "../components/Toast";
import { IconChevronDown, IconCopy, IconKey, IconLock, IconMore, IconPause, IconPencil, IconPlay, IconPlus, IconSearch, IconTrash } from "../icons";
import { publishKeys } from "../util/catalog";
import { dateOnly, errText, plural, usd } from "../util/format";
import { sortRows, useAsync, useRowNav, useSort } from "../util/hooks";
import { projectedSpend, useKeySpend } from "../util/keySpend";
import { useDensity } from "../theme";
import type { CreatedKey, HubKey, SpendPeriod } from "../types";

function RevealKeyModal({ created, onClose }: { created: CreatedKey; onClose: () => void }) {
  const snippet = `curl ${window.location.origin}/v1/models \\\n  -H "Authorization: Bearer ${created.key}"`;
  return (
    <Modal
      title="Copy your key now"
      onClose={onClose}
      footer={<button type="button" className="btn btn-primary" onClick={onClose}>I've stored it safely</button>}
    >
      <div className="notice ok">
        <IconLock />
        <span>
          This is the <strong>only time</strong> <code className="mono">{created.name}</code>'s secret is shown.
          The hub keeps a SHA-256 hash, so a lost key means rolling a new one.
        </span>
      </div>
      <div className="reveal-key" data-testid="revealed-key">{created.key}</div>
      <CopyButton text={created.key} label="Copy key" className="btn btn-primary btn-block btn-lg" />
      <div>
        <p className="caption" style={{ marginBottom: 6 }}>Try it</p>
        <pre className="code">{snippet}</pre>
      </div>
    </Modal>
  );
}

function RevokeKeyModal({ k, onClose, onConfirm }: { k: HubKey; onClose: () => void; onConfirm: () => void }) {
  return (
    <Modal
      title={`Revoke ${k.name}?`}
      onClose={onClose}
      desc="Any app using this key will start getting 401s immediately. Your real provider keys are untouched and keep working for every other hub key."
      footer={<>
        <button type="button" className="btn btn-ghost" onClick={onClose}>Keep it</button>
        <button type="button" className="btn btn-danger" onClick={onConfirm}><IconTrash />Revoke key</button>
      </>}
    >
      <div className="notice bad">
        <span className="kdot dead" style={{ marginTop: 6 }} />
        <div>
          <div className="mono strong" style={{ fontWeight: 600 }}>{k.name} (key #{k.id})</div>
          <div className="faint" style={{ fontSize: 12 }}>
            {plural(k.allowed_models.length, "model")}, {usd(k.spend_cap_usd, 2)} per {k.spend_period}
          </div>
        </div>
      </div>
    </Modal>
  );
}

function EditLimitsModal({ k, used, onClose, onSaved }: { k: HubKey; used: number | null; onClose: () => void; onSaved: () => void }) {
  const toast = useToast();
  const [cap, setCap] = useState(String(k.spend_cap_usd));
  const [period, setPeriod] = useState<SpendPeriod>(k.spend_period);
  const [rate, setRate] = useState(String(k.rate_limit_per_min));
  const [saving, setSaving] = useState(false);

  const capNumber = Number(cap);
  const rateNumber = Number(rate);
  const capOk = cap.trim() !== "" && Number.isFinite(capNumber) && capNumber >= 0;
  const rateOk = rate.trim() !== "" && Number.isInteger(rateNumber) && rateNumber >= 1;

  const changes: Parameters<typeof api.updateKey>[1] = {};
  if (capOk && capNumber !== k.spend_cap_usd) changes.spend_cap_usd = capNumber;
  if (period !== k.spend_period) changes.spend_period = period;
  if (rateOk && rateNumber !== k.rate_limit_per_min) changes.rate_limit_per_min = rateNumber;
  const dirty = Object.keys(changes).length > 0;

  const save = async () => {
    setSaving(true);
    try {
      await api.updateKey(k.id, changes);
      toast(`Updated limits for ${k.name}`);
      onSaved();
      onClose();
    } catch (e) {
      toast(`Couldn't update ${k.name}: ${errText(e)}`);
      setSaving(false);
    }
  };

  return (
    <Modal
      title={`Edit limits for ${k.name}`}
      onClose={onClose}
      desc="Changes apply to the key's very next call."
      footer={<>
        <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
        <button type="button" className="btn btn-primary" onClick={save} disabled={!capOk || !rateOk || !dirty || saving}>
          {saving ? "Saving" : "Save limits"}
        </button>
      </>}
    >
      {used != null && period === k.spend_period && (
        <div>
          <p className="caption" style={{ marginBottom: 6 }}>Spend so far this {period}, against the new cap</p>
          <Meter used={used} cap={capOk ? capNumber : 0} label={`${k.name} spend against the edited cap`} />
        </div>
      )}
      <div className="field">
        <span className="field-label" id="e-period">Period</span>
        <div className="seg" role="radiogroup" aria-labelledby="e-period">
          {(["day", "week", "month"] as SpendPeriod[]).map(p => (
            <button key={p} type="button" role="radio" aria-checked={period === p} className={period === p ? "on" : ""} onClick={() => setPeriod(p)}>{p}</button>
          ))}
        </div>
      </div>
      <div className="field">
        <label htmlFor="e-cap">Spend budget</label>
        <div className="input-prefix">
          <span className="pfx mono">$</span>
          <input id="e-cap" type="number" min="0" step="0.01" className="input mono tnum" value={cap} onChange={e => setCap(e.target.value)} aria-invalid={!capOk} />
        </div>
        <span className={`hint ${!capOk ? "field-error" : ""}`}>Calls stop once the key reaches this amount for the current {period}.</span>
      </div>
      <div className="field">
        <label htmlFor="e-rate">Rate limit</label>
        <div className="input-suffix">
          <input id="e-rate" type="number" min="1" step="1" className="input mono tnum" value={rate} onChange={e => setRate(e.target.value)} aria-invalid={!rateOk} />
          <span className="sfx mono">req/min</span>
        </div>
        <span className={`hint ${!rateOk ? "field-error" : ""}`}>Whole number, at least 1.</span>
      </div>
    </Modal>
  );
}

type SortKey = "name" | "used" | "created";

export function KeysPage() {
  const keysQ = useAsync(() => api.listKeys(), []);
  const keys = keysQ.data;
  const spend = useKeySpend(keys);
  const [reveal, setReveal] = useState<CreatedKey | null>(null);
  const [revoking, setRevoking] = useState<HubKey | null>(null);
  const [editing, setEditing] = useState<HubKey | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [filter, setFilter] = useState<"all" | "active" | "inactive">("all");
  const [q, setQ] = useState("");
  const [density, setDensity] = useDensity();
  const [params] = useSearchParams();
  const hit = Number(params.get("key")) || null;
  const toast = useToast();
  const location = useLocation();
  const navigate = useNavigate();
  const sort = useSort<SortKey>("created");
  const { tbodyProps, rowProps } = useRowNav();

  // CreateKeyPage hands the plaintext over in router state; show it once and clear it so a refresh can't re-show it.
  useEffect(() => {
    const st = location.state as { newKey?: CreatedKey } | null;
    if (st?.newKey) {
      setReveal(st.newKey);
      navigate(location.pathname, { replace: true, state: null });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { if (keys) publishKeys(keys); }, [keys]);
  useEffect(() => { if (reveal) keysQ.reload(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [reveal]);

  const used = (k: HubKey) => spend.data?.get(k.id) ?? null;

  const rows = useMemo(() => {
    let list = keys ?? [];
    if (filter === "active") list = list.filter(k => k.active);
    if (filter === "inactive") list = list.filter(k => !k.active);
    if (q.trim()) list = list.filter(k => `${k.name} ${k.default_project ?? ""} ${k.id}`.toLowerCase().includes(q.trim().toLowerCase()));
    return sortRows(list, k => {
      if (sort.key === "name") return k.name;
      if (sort.key === "used") return k.spend_cap_usd > 0 ? (spend.data?.get(k.id) ?? 0) / k.spend_cap_usd : 0;
      return k.created_at;
    }, sort.dir);
  }, [keys, filter, q, sort.key, sort.dir, spend.data]);

  // Jump from the palette: bring the key into view and give it keyboard focus.
  useEffect(() => {
    if (!hit || !keys) return;
    const el = document.querySelector<HTMLElement>(`tr[data-key-id="${hit}"]`);
    el?.scrollIntoView({ block: "center", behavior: "auto" });
    el?.focus({ preventScroll: true });
  }, [hit, keys, rows.length]);

  const togglePause = async (k: HubKey) => {
    try {
      await (k.paused ? api.resumeKey(k.id) : api.pauseKey(k.id));
      toast(k.paused ? `Resumed ${k.name}` : `Paused ${k.name}. Calls are refused until you resume it`);
      keysQ.reload();
    } catch (e) {
      toast(`Couldn't update ${k.name}: ${errText(e)}`);
    }
  };

  const confirmRevoke = async () => {
    if (!revoking) return;
    try {
      await api.revokeKey(revoking.id);
      toast(`Revoked ${revoking.name}. Access is cut immediately`);
      setRevoking(null);
      keysQ.reload();
    } catch (e) {
      toast(`Couldn't revoke: ${errText(e)}`);
    }
  };

  const activeCount = (keys ?? []).filter(k => k.active).length;
  const SortTh = ({ k, label, num }: { k: SortKey; label: string; num?: boolean }) => (
    <th scope="col" className={num ? "num" : undefined} aria-sort={sort.ariaSort(k)}>
      <button type="button" className="sort-btn" onClick={() => sort.toggle(k, k === "name")}>
        {label}
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m7 10 5 5 5-5" /></svg>
      </button>
    </th>
  );

  return (
    <div className="container">
      <PageHead title="Hub keys" sub="Scoped credentials your apps use. Each one maps to real provider keys it can never see, and any of them can be revoked instantly.">
        <Link to="/keys/new" className="btn btn-primary"><IconPlus />New hub key</Link>
      </PageHead>

      <section className="panel rise" aria-labelledby="all-keys">
        <div className="panel-head">
          <h2 id="all-keys">All keys</h2>
          <span className="sub">{keys ? `${activeCount} active of ${keys.length}` : "loading"}</span>
        </div>

        {keysQ.error && !keys ? (
          <ErrorState title="Couldn't load keys" error={keysQ.error} onRetry={keysQ.reload} />
        ) : !keys ? (
          <SkelRows rows={5} label="Loading keys" />
        ) : keys.length === 0 ? (
          <EmptyState
            icon={<IconKey />} title="No hub keys yet"
            action={<Link to="/keys/new" className="btn btn-primary"><IconPlus />Create your first key</Link>}
          >
            A hub key is a disposable <code className="mono">ph_</code> credential you hand to an app. It carries a model allowlist, a spend cap and a rate limit, so the real provider keys stay locked away here.
          </EmptyState>
        ) : (
          <>
            <div className="toolbar" style={{ padding: "10px 16px", borderBottom: "1px solid var(--line)" }}>
              <div className="search">
                <IconSearch />
                <input value={q} onChange={e => setQ(e.target.value)} placeholder="Filter keys" aria-label="Filter keys" />
              </div>
              <div className="seg" role="radiogroup" aria-label="Show">
                {(["all", "active", "inactive"] as const).map(f => (
                  <button key={f} type="button" role="radio" aria-checked={filter === f} className={filter === f ? "on" : ""} onClick={() => setFilter(f)}>{f}</button>
                ))}
              </div>
              <div className="seg seg-density" role="radiogroup" aria-label="Row density">
                {(["comfortable", "compact"] as const).map(d => (
                  <button key={d} type="button" role="radio" aria-checked={density === d} className={density === d ? "on" : ""} onClick={() => setDensity(d)}>{d}</button>
                ))}
              </div>
            </div>
            {rows.length === 0 ? (
              <EmptyState icon={<IconSearch />} title="No keys match" action={<button type="button" className="btn" onClick={() => { setQ(""); setFilter("all"); }}>Clear filters</button>}>
                Nothing in this list fits the current filter.
              </EmptyState>
            ) : (
              <div className="table-wrap">
                <table className="tbl cards keys">
                  <caption className="sr-only">Hub keys with spend against cap</caption>
                  <thead>
                    <tr>
                      <SortTh k="name" label="Key" />
                      <SortTh k="used" label="Spend against cap" />
                      <th scope="col">Models</th>
                      <th scope="col" className="num">Rate</th>
                      <SortTh k="created" label="Created" />
                      <th scope="col">State</th>
                      <th scope="col" className="cell-actions"><span className="sr-only">Actions</span></th>
                    </tr>
                  </thead>
                  <tbody {...tbodyProps}>
                    {rows.map((k, i) => {
                      const u = used(k);
                      const live = k.revoked_at === null;
                      const open = expanded === k.id && k.allowed_models.length > 0;
                      return (
                        <Fragment key={k.id}>
                          <tr {...rowProps(i)} data-key-id={k.id} className={`${k.active ? "" : "is-dead"} ${hit === k.id ? "is-hit" : ""} ${open ? "is-open" : ""}`}>
                            <td className="td-primary">
                              <span className="row" style={{ gap: 10, alignItems: "flex-start" }}>
                                <span className={`kdot ${k.paused && k.active ? "pause" : k.active ? "live" : "dead"}`} style={{ marginTop: 7 }} />
                                <span style={{ minWidth: 0 }}>
                                  <span className="cell-main cell-trunc" title={k.name}>{k.name}</span>
                                  <span className="cell-sub row" style={{ gap: 6, flexWrap: "wrap" }}>
                                    <CopyId value={String(k.id)} display={`#${k.id}`} label="key id" />
                                    {k.default_project && <span>project {k.default_project}</span>}
                                    {k.route_override && <span title={`Routed to ${k.route_override}`}>routed</span>}
                                  </span>
                                </span>
                              </span>
                            </td>
                            <td data-label="Spend against cap" className="td-wide td-bare" style={{ minWidth: 220 }}>
                              {!live || !k.active ? (
                                <span className="faint">{live ? "expired" : `revoked ${k.revoked_at ? dateOnly(k.revoked_at) : ""}`}</span>
                              ) : u == null ? (
                                spend.error ? <span className="faint" title={spend.error}>unavailable</span> : <span className="skel" style={{ height: 8, width: "100%" }} aria-hidden="true" />
                              ) : (
                                <div style={{ width: "100%" }}>
                                  <Meter used={u} cap={k.spend_cap_usd} projected={projectedSpend(u, k.spend_period)} label={`${k.name} spend against its ${k.spend_period} cap`} />
                                  <span className="meter-sub">per {k.spend_period}</span>
                                </div>
                              )}
                            </td>
                            <td data-label="Models" className="td-m-hide">
                              {k.allowed_models.length === 0 ? <span className="faint">any model</span> : (
                                <button type="button" className="chip" style={{ cursor: "pointer" }} aria-expanded={open} onClick={() => setExpanded(open ? null : k.id)}>
                                  {plural(k.allowed_models.length, "model")}
                                  <IconChevronDown style={{ transform: open ? "rotate(180deg)" : undefined, transition: "transform 240ms var(--settle)" }} />
                                </button>
                              )}
                            </td>
                            <td data-label="Rate" className="num cell-id nowrap td-m-hide">{k.rate_limit_per_min}/min</td>
                            <td data-label="Created" className="cell-id nowrap faint td-m-hide">{dateOnly(k.created_at)}{k.expires_at && <span className="cell-sub">{k.expired ? "expired" : "expires"} {dateOnly(k.expires_at)}</span>}</td>
                            <td data-label="State" className="td-state"><KeyStatus active={k.active} expired={k.expired} paused={k.paused} /></td>
                            <td className="cell-actions">
                              <Menu
                                label={`Actions for ${k.name}`}
                                items={[
                                  ...(live ? [
                                    { label: "Edit limits", icon: <IconPencil />, onSelect: () => setEditing(k) },
                                    { label: k.paused ? "Resume" : "Pause", icon: k.paused ? <IconPlay /> : <IconPause />, onSelect: () => togglePause(k) },
                                  ] : []),
                                  { label: "Copy key id", icon: <IconCopy />, onSelect: async () => { try { await navigator.clipboard.writeText(String(k.id)); } catch { /* blocked */ } toast("Copied key id"); } },
                                  ...(live ? [{ label: "Revoke", icon: <IconTrash />, danger: true, separatorBefore: true, onSelect: () => setRevoking(k) }] : []),
                                ]}
                              >
                                <IconMore />
                              </Menu>
                            </td>
                          </tr>
                          {open && (
                            <tr>
                              <td colSpan={7} style={{ background: "var(--sunk)" }}>
                                <div className="row wrap" style={{ gap: 6 }}>
                                  <span className="caption" style={{ marginRight: 6 }}>Allowlist</span>
                                  {k.allowed_models.map(m => <span key={m} className="chip">{m}</span>)}
                                </div>
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
            <div className="tbl-foot">
              <IconLock style={{ width: 13, height: 13 }} />
              Secrets are stored as hashes; the plaintext is shown once at creation. Spend is counted inside each key's own cap window and leaves out manual adjustments.
            </div>
          </>
        )}
      </section>

      {reveal && <RevealKeyModal created={reveal} onClose={() => setReveal(null)} />}
      {editing && <EditLimitsModal k={editing} used={used(editing)} onClose={() => setEditing(null)} onSaved={keysQ.reload} />}
      {revoking && <RevokeKeyModal k={revoking} onClose={() => setRevoking(null)} onConfirm={confirmRevoke} />}
    </div>
  );
}
