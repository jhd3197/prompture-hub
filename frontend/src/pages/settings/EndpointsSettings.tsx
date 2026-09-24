import { useEffect, useState } from "react";
import { api } from "../../api";
import { EmptyState } from "../../components/EmptyState";
import { useToast } from "../../components/Toast";
import { IconPlus, IconRefresh, IconRoute, IconTrash } from "../../icons";
import type { CustomEndpoint, EndpointUsage } from "../../types";

const STATUS_BADGE: Record<string, string> = {
  online: "badge badge-live",
  slow: "badge badge-warn",
  unreachable: "badge badge-danger",
  error: "badge badge-danger",
};

function usd(v: number): string {
  return `$${v.toFixed(v < 1 ? 4 : 2)}`;
}

function EndpointRow({ ep, onChanged }: { ep: CustomEndpoint; onChanged: () => void }) {
  const toast = useToast();
  const [usage, setUsage] = useState<EndpointUsage | null>(null);
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    api.endpointUsage(ep.id, 7).then(setUsage).catch(() => setUsage(null));
  }, [ep.id]);

  const check = async () => {
    setChecking(true);
    try {
      const res = await api.checkEndpoint(ep.id);
      toast(res.last_status === "online" || res.last_status === "slow"
        ? `${ep.name}: ${res.last_status}, ${res.models.length} models`
        : `${ep.name}: ${res.last_status}${res.detail ? ` (${res.detail})` : ""}`);
      onChanged();
    } finally {
      setChecking(false);
    }
  };

  const remove = async () => {
    await api.deleteEndpoint(ep.id);
    toast(`Removed ${ep.name}`);
    onChanged();
  };

  return (
    <tr>
      <td>
        <div className="strong" style={{ fontWeight: 600 }}>{ep.name}</div>
        <div className="mono faint" style={{ fontSize: 11.5 }}>{ep.base_url}</div>
      </td>
      <td>
        {ep.last_status
          ? <span className={STATUS_BADGE[ep.last_status] ?? "badge"}>{ep.last_status}{ep.last_latency_ms != null && ` · ${ep.last_latency_ms} ms`}</span>
          : <span className="badge">not checked</span>}
      </td>
      <td className="faint" style={{ fontSize: 12.5 }}>
        {ep.models.length ? `${ep.models.length} models` : "—"}
      </td>
      <td className="num mono tnum" style={{ fontSize: 12.5 }}>
        {usage ? `${usage.totals.requests} calls · ${usd(usage.totals.cost_usd)}` : "—"}
      </td>
      <td className="num">
        <div className="row" style={{ gap: 6, justifyContent: "flex-end" }}>
          <button className="btn btn-sm" onClick={check} disabled={checking}>
            <IconRefresh style={{ width: 13, height: 13 }} />{checking ? "Checking…" : "Check"}
          </button>
          <button className="btn btn-sm btn-danger" onClick={remove} aria-label={`Remove ${ep.name}`}><IconTrash /></button>
        </div>
      </td>
    </tr>
  );
}

export function EndpointsSettings() {
  const toast = useToast();
  const [items, setItems] = useState<CustomEndpoint[] | null>(null);
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [keyEnv, setKeyEnv] = useState("");

  const load = async () => {
    try {
      setItems(await api.endpoints());
    } catch (e) {
      toast(`Couldn't load endpoints: ${e}`);
    }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.createEndpoint({ name: name.trim().toLowerCase(), base_url: baseUrl.trim(), api_key_env: keyEnv.trim() || null });
      toast(`Added ${name}`);
      setName(""); setBaseUrl(""); setKeyEnv("");
      load();
    } catch (err) {
      toast(`Couldn't add endpoint: ${err}`);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <div className="card">
        <div className="card-head"><h3>Custom endpoints</h3><span className="sub">last 7 days</span></div>
        {items === null ? (
          <div className="empty"><p>Loading…</p></div>
        ) : items.length === 0 ? (
          <EmptyState icon={<IconRoute />} title="No custom endpoints">
            Add any OpenAI-compatible server (vLLM, llama.cpp, a private gateway). Its models become{" "}
            <code className="mono">openai_compatible/&lt;name&gt;/&lt;model&gt;</code>, metered like every other provider.
          </EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="tbl">
              <thead><tr><th>Endpoint</th><th>Health</th><th>Models</th><th className="num">Usage</th><th className="num">Action</th></tr></thead>
              <tbody>{items.map(ep => <EndpointRow key={ep.id} ep={ep} onChanged={load} />)}</tbody>
            </table>
          </div>
        )}
      </div>

      <form className="card card-pad" onSubmit={create} style={{ display: "grid", gap: 12, gridTemplateColumns: "1fr 2fr 1fr" }}>
        <h2 className="section-title" style={{ gridColumn: "1 / -1", margin: 0 }}>Add an endpoint</h2>
        <div className="field">
          <label htmlFor="ep-name">Name</label>
          <input id="ep-name" className="input mono" placeholder="gpu-box" value={name} onChange={e => setName(e.target.value)} required />
        </div>
        <div className="field">
          <label htmlFor="ep-url">Base URL</label>
          <input id="ep-url" className="input mono" placeholder="http://192.168.1.20:8001/v1" value={baseUrl} onChange={e => setBaseUrl(e.target.value)} required />
        </div>
        <div className="field">
          <label htmlFor="ep-env">API key env var</label>
          <input id="ep-env" className="input mono" placeholder="optional, e.g. GPU_BOX_KEY" value={keyEnv} onChange={e => setKeyEnv(e.target.value)} />
        </div>
        <p className="hint muted" style={{ gridColumn: "1 / -2", margin: 0, fontSize: 12 }}>
          The key itself stays in the hub's environment (<code className="mono">.env</code>); only the variable's name is stored.
        </p>
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <button className="btn btn-primary"><IconPlus />Add</button>
        </div>
      </form>
    </div>
  );
}
