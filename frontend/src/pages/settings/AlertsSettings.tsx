import { useEffect, useState } from "react";
import { api } from "../../api";
import { EmptyState } from "../../components/EmptyState";
import { useToast } from "../../components/Toast";
import { IconBolt, IconCheck, IconPlus, IconTrash } from "../../icons";
import type { AlertEvent, AlertKind, AlertRule, HubKey } from "../../types";

const KINDS: Array<{ kind: AlertKind; label: string; threshold: "fraction" | "amount" | null; hint: string }> = [
  { kind: "key_spend", label: "Key spend", threshold: "fraction", hint: "Share of a key's spend cap used this period (default 80%)." },
  { kind: "provider_headroom", label: "Provider rate limit", threshold: "fraction", hint: "Share of a provider rate-limit window left (default 5%)." },
  { kind: "balance_low", label: "Low account balance", threshold: "amount", hint: "Provider account balance below this amount." },
  { kind: "fallback", label: "Fallback used", threshold: null, hint: "A call needed a retry or another model." },
  { kind: "error", label: "Failed call", threshold: null, hint: "A call ended in an error." },
];

function describe(rule: AlertRule): string {
  const meta = KINDS.find(k => k.kind === rule.kind);
  if (rule.threshold == null) return meta?.label ?? rule.kind;
  const value = meta?.threshold === "fraction" ? `${Math.round(rule.threshold * 100)}%` : `${rule.threshold}`;
  return `${meta?.label ?? rule.kind} · ${value}`;
}

function NewRuleForm({ keys, onCreated }: { keys: HubKey[]; onCreated: () => void }) {
  const toast = useToast();
  const [kind, setKind] = useState<AlertKind>("key_spend");
  const [name, setName] = useState("");
  const [threshold, setThreshold] = useState("");
  const [keyId, setKeyId] = useState("");
  const [target, setTarget] = useState("");
  const [webhook, setWebhook] = useState("");
  const [ntfy, setNtfy] = useState("");
  const [cooldown, setCooldown] = useState("60");
  const meta = KINDS.find(k => k.kind === kind)!;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    let value: number | null = null;
    if (meta.threshold && threshold.trim()) {
      value = Number(threshold);
      if (meta.threshold === "fraction") value = value / 100;
    }
    try {
      await api.createAlertRule({
        name: name.trim() || meta.label,
        kind,
        threshold: value,
        key_id: keyId ? Number(keyId) : null,
        target: target.trim() || null,
        webhook_url: webhook.trim() || null,
        ntfy_url: ntfy.trim() || null,
        cooldown_minutes: Number(cooldown) || 0,
      });
      toast("Alert rule created");
      setName(""); setThreshold(""); setTarget(""); setWebhook(""); setNtfy("");
      onCreated();
    } catch (err) {
      toast(`Couldn't create rule: ${err}`);
    }
  };

  const keyScoped = kind === "key_spend" || kind === "fallback" || kind === "error";

  return (
    <form className="card card-pad" onSubmit={submit} style={{ display: "grid", gap: 12, gridTemplateColumns: "1fr 1fr" }}>
      <h2 className="section-title" style={{ gridColumn: "1 / -1", margin: 0 }}>New rule</h2>
      <div className="field">
        <label htmlFor="ar-kind">When</label>
        <select id="ar-kind" className="input" value={kind} onChange={e => setKind(e.target.value as AlertKind)}>
          {KINDS.map(k => <option key={k.kind} value={k.kind}>{k.label}</option>)}
        </select>
        <span className="hint">{meta.hint}</span>
      </div>
      <div className="field">
        <label htmlFor="ar-name">Name</label>
        <input id="ar-name" className="input" placeholder={meta.label} value={name} onChange={e => setName(e.target.value)} />
      </div>
      {meta.threshold && (
        <div className="field">
          <label htmlFor="ar-threshold">{meta.threshold === "fraction" ? "Threshold (%)" : "Threshold (amount)"}</label>
          <input
            id="ar-threshold" className="input mono tnum" inputMode="decimal"
            placeholder={meta.threshold === "fraction" ? "default" : "5"}
            value={threshold} onChange={e => setThreshold(e.target.value)}
          />
        </div>
      )}
      {keyScoped ? (
        <div className="field">
          <label htmlFor="ar-key">Key</label>
          <select id="ar-key" className="input" value={keyId} onChange={e => setKeyId(e.target.value)}>
            <option value="">Any key</option>
            {keys.filter(k => k.active).map(k => <option key={k.id} value={k.id}>{k.name}</option>)}
          </select>
        </div>
      ) : (
        <div className="field">
          <label htmlFor="ar-target">{kind === "balance_low" ? "Account source" : "Model"}</label>
          <input
            id="ar-target" className="input mono" placeholder={kind === "balance_low" ? "any (e.g. openrouter)" : "any (e.g. openai/gpt-4o)"}
            value={target} onChange={e => setTarget(e.target.value)}
          />
        </div>
      )}
      <div className="field">
        <label htmlFor="ar-webhook">Webhook URL</label>
        <input id="ar-webhook" className="input mono" placeholder="optional" value={webhook} onChange={e => setWebhook(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor="ar-ntfy">ntfy topic URL</label>
        <input id="ar-ntfy" className="input mono" placeholder="optional, e.g. https://ntfy.sh/my-hub" value={ntfy} onChange={e => setNtfy(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor="ar-cooldown">Repeat at most every (minutes)</label>
        <input id="ar-cooldown" className="input mono tnum" inputMode="numeric" value={cooldown} onChange={e => setCooldown(e.target.value)} />
      </div>
      <div style={{ gridColumn: "1 / -1", display: "flex", justifyContent: "flex-end" }}>
        <button className="btn btn-primary"><IconPlus />Add rule</button>
      </div>
    </form>
  );
}

export function AlertsSettings() {
  const toast = useToast();
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [events, setEvents] = useState<AlertEvent[]>([]);
  const [keys, setKeys] = useState<HubKey[]>([]);

  const load = async () => {
    try {
      const [r, e, k] = await Promise.all([api.alertRules(), api.alerts(), api.listKeys()]);
      setRules(r); setEvents(e); setKeys(k);
    } catch (err) {
      toast(`Couldn't load alerts: ${err}`);
    }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);

  const toggle = async (rule: AlertRule) => {
    await api.updateAlertRule(rule.id, { enabled: !rule.enabled });
    load();
  };
  const remove = async (rule: AlertRule) => {
    await api.deleteAlertRule(rule.id);
    toast(`Deleted ${rule.name}`);
    load();
  };
  const ack = async (event: AlertEvent) => {
    await api.ackAlert(event.alert_id);
    load();
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <div className="card">
        <div className="card-head"><h3>Rules</h3><span className="sub">{rules.length} configured</span></div>
        {rules.length === 0 ? (
          <EmptyState icon={<IconBolt />} title="No alert rules">
            Alerts show up on the live stream for paired devices, and can also post to a webhook or an ntfy topic.
          </EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="tbl">
              <thead><tr><th>Name</th><th>Condition</th><th>Channels</th><th>Enabled</th><th className="num">Action</th></tr></thead>
              <tbody>
                {rules.map(r => (
                  <tr key={r.id}>
                    <td className="strong">{r.name}</td>
                    <td>{describe(r)}{r.target && <span className="faint mono"> · {r.target}</span>}</td>
                    <td className="faint" style={{ fontSize: 12.5 }}>
                      {["live", r.webhook_url && "webhook", r.ntfy_url && "ntfy"].filter(Boolean).join(", ")}
                    </td>
                    <td><input type="checkbox" checked={r.enabled} onChange={() => toggle(r)} aria-label={`Enable ${r.name}`} /></td>
                    <td className="num">
                      <button className="btn btn-sm btn-danger" onClick={() => remove(r)} aria-label={`Delete ${r.name}`}><IconTrash /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <NewRuleForm keys={keys} onCreated={load} />

      <div className="card">
        <div className="card-head"><h3>Recent alerts</h3><span className="sub">newest first</span></div>
        {events.length === 0 ? (
          <div className="empty"><p>Nothing has fired yet.</p></div>
        ) : (
          <div className="table-wrap">
            <table className="tbl">
              <thead><tr><th>When</th><th>Rule</th><th>Message</th><th className="num">Status</th></tr></thead>
              <tbody>
                {events.map(e => (
                  <tr key={e.alert_id}>
                    <td className="faint" style={{ whiteSpace: "nowrap", fontSize: 12.5 }}>{new Date(e.created_at).toLocaleString()}</td>
                    <td>{e.rule}</td>
                    <td>{e.message}</td>
                    <td className="num">
                      {e.acknowledged_at
                        ? <span className="badge">acknowledged</span>
                        : <button className="btn btn-sm" onClick={() => ack(e)}><IconCheck />Acknowledge</button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
