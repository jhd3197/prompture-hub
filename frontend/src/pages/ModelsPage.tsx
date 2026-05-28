import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { EmptyState } from "../components/EmptyState";
import {
  IconAlert, IconChevronRight, IconGrid, IconKey, IconLayers,
  IconRefresh, IconRoute, IconSearch, IconX,
} from "../icons";
import type { ModelsResponse, ProviderGroup } from "../types";

function RoutingExplain() {
  return (
    <div className="route-explain">
      <div className="rc">
        <div className="rk"><IconKey />The hub key → policy</div>
        <div className="rv">
          The <code>Bearer</code> token sets the whitelist, spend cap and rate limit. It never names a provider.
        </div>
      </div>
      <div className="rc">
        <div className="rk"><IconRoute />provider/model → driver</div>
        <div className="rv">
          The prefix routes to the driver: <code>openai/gpt-4o</code>, <code>claude/…</code>, <code>ollama/…</code>.
        </div>
      </div>
      <div className="rc">
        <div className="rk"><IconLayers />The path → surface</div>
        <div className="rv">
          <code>/v1/chat/completions</code>, <code>/v1/embeddings</code>, <code>/v1/extract</code> picks the API shape, not the provider.
        </div>
      </div>
    </div>
  );
}

function ProviderRow({
  group, query, forceOpen,
}: {
  group: ProviderGroup;
  query: string;
  forceOpen: boolean;
}) {
  const [open, setOpen] = useState(false);
  const isOpen = forceOpen || open;

  const q = query.trim().toLowerCase();
  const matched = q
    ? group.models.filter(m =>
        m.toLowerCase().includes(q) ||
        group.provider.toLowerCase().includes(q),
      )
    : group.models;

  if (q && matched.length === 0) return null;

  const initials = group.provider.slice(0, 2).toUpperCase();

  return (
    <div className="provider-group fade-in">
      <div
        className={`provider-bar ${isOpen ? "open" : ""}`}
        onClick={() => setOpen(o => !o)}
        role="button"
        tabIndex={0}
        aria-expanded={isOpen}
        onKeyDown={e => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setOpen(o => !o);
          }
        }}
      >
        <span className="provider-chevron">
          <IconChevronRight style={{ width: 16, height: 16 }} />
        </span>
        <span className="provider-logo">{initials}</span>
        <div className="grow" style={{ minWidth: 0 }}>
          <div className="row" style={{ gap: 9 }}>
            <span className="provider-name">{group.provider}</span>
            <span className="mono faint" style={{ fontSize: 11.5 }}>{group.provider}/</span>
          </div>
          <div className="provider-meta">
            {matched.length} model{matched.length !== 1 ? "s" : ""}{q ? " match" : ""}
          </div>
        </div>
        <span className="badge badge-live"><span className="dot"></span>Available</span>
      </div>

      {isOpen && (
        <div className="model-table">
          {matched.map(model => (
            <div className="model-row" key={`${group.provider}/${model}`}>
              <div style={{ minWidth: 0 }}>
                <span className="route-pill" title={`${group.provider}/${model}`}>
                  <span className="rp-prov">{group.provider}</span>
                  <span className="rp-sep">/</span>
                  <span className="rp-model">{model}</span>
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function ModelsPage() {
  const [data, setData] = useState<ModelsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      setData(await api.models());
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const totalModels = useMemo(() => data?.total ?? 0, [data]);
  const providerCount = useMemo(() => data?.groups.length ?? 0, [data]);

  return (
    <div className="container">
      <div className="page-head">
        <div className="grow">
          <h1 className="page-title">Models</h1>
          <p className="page-sub">
            Everything the hub can route, addressed as{" "}
            <code className="mono" style={{
              background: "var(--accent-softer)",
              color: "var(--accent-strong)",
              padding: "1px 6px",
              borderRadius: 4,
            }}>provider/model</code>.{" "}
            <strong className="mono tnum">{totalModels}</strong> models across{" "}
            <strong>{providerCount}</strong> providers.
          </p>
        </div>
        <button className="btn" onClick={load}>
          <IconRefresh style={{ width: 14, height: 14 }} />Refresh
        </button>
      </div>

      <RoutingExplain />

      <div className="toolbar mb24">
        <div className="search">
          <IconSearch />
          <input
            placeholder="Search by route or name…  e.g. openai/gpt-4o, claude, ollama"
            value={query}
            onChange={e => setQuery(e.target.value)}
            aria-label="Search models"
          />
        </div>
        {query && (
          <button className="btn btn-sm btn-ghost" onClick={() => setQuery("")}>
            <IconX />Clear
          </button>
        )}
      </div>

      {error && (
        <div className="discovery-fail mb16" role="alert" style={{
          borderRadius: "var(--r-md)",
          border: "1px solid var(--warn)",
          background: "var(--warn-soft)",
        }}>
          <IconAlert />
          <div>
            <strong>Couldn't list models.</strong> {error}
            <div className="mt8">
              <button className="btn btn-sm" onClick={load}>
                <IconRefresh style={{ width: 13, height: 13 }} />Retry
              </button>
            </div>
          </div>
        </div>
      )}

      {data?.discovery_error && (
        <div className="discovery-fail mb16" role="alert" style={{
          borderRadius: "var(--r-md)",
          border: "1px solid var(--warn)",
          background: "var(--warn-soft)",
        }}>
          <IconAlert />
          <span>Partial discovery error: <span className="mono">{data.discovery_error}</span></span>
        </div>
      )}

      {loading && !data ? (
        <div className="empty"><p>Discovering models…</p></div>
      ) : data && data.groups.length === 0 ? (
        <EmptyState icon={<IconGrid />} title="No models discoverable">
          Add a provider API key (e.g. <code className="mono">OPENAI_API_KEY</code>) to <code className="mono">.env</code> and restart the hub to light up its models here.
        </EmptyState>
      ) : (
        data?.groups.map(g => (
          <ProviderRow
            key={g.provider}
            group={g}
            query={query}
            forceOpen={!!query}
          />
        ))
      )}
    </div>
  );
}
