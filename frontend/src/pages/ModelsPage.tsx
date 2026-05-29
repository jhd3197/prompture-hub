import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api";
import { AgentCard } from "../components/AgentCard";
import { EmptyState } from "../components/EmptyState";
import { ProviderLogo } from "../components/ProviderLogo";
import { SnippetModal } from "../components/SnippetModal";
import {
  IconAlert, IconChevronRight, IconCopy, IconGrid, IconKey, IconLayers,
  IconRefresh, IconRoute, IconSearch, IconTerminal, IconX,
} from "../icons";
import type {
  AgentsResponse, ModalitiesResponse, ModalitySection,
  ModelsResponse, ProviderGroup,
} from "../types";

type Tab = "models" | "agents" | "modalities";

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
  group, query, forceOpen, onPick,
}: {
  group: ProviderGroup;
  query: string;
  forceOpen: boolean;
  onPick: (route: string) => void;
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
        <ProviderLogo
          iconUrl={group.icon_url}
          brandColor={group.brand_color}
          fallback={initials}
        />
        <div className="grow" style={{ minWidth: 0 }}>
          <div className="row" style={{ gap: 9 }}>
            <span className="provider-name">
              {group.display_name || group.provider}
            </span>
            <span className="mono faint" style={{ fontSize: 11.5 }}>{group.provider}/</span>
            {group.is_local && <span className="badge" style={{ fontSize: 10.5 }}>local</span>}
          </div>
          <div className="provider-meta">
            {matched.length} model{matched.length !== 1 ? "s" : ""}{q ? " match" : ""}
          </div>
        </div>
        <span className="badge badge-live"><span className="dot"></span>Available</span>
      </div>

      {isOpen && (
        <div className="model-table">
          {matched.map(model => {
            const route = `${group.provider}/${model}`;
            return (
              <div
                className="model-row"
                key={route}
                onClick={() => onPick(route)}
                role="button"
                tabIndex={0}
                onKeyDown={e => {
                  if (e.key === "Enter") onPick(route);
                }}
              >
                <div style={{ minWidth: 0 }}>
                  <span className="route-pill" title={route}>
                    <span className="rp-prov">{group.provider}</span>
                    <span className="rp-sep">/</span>
                    <span className="rp-model">{model}</span>
                  </span>
                </div>
                <span
                  className="row"
                  style={{ gap: 5, color: "var(--text-3)", fontSize: 12 }}
                >
                  <IconCopy style={{ width: 13, height: 13 }} />
                  snippet
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab panels
// ---------------------------------------------------------------------------

function ModelsTab({
  data, loading, query, onPick,
}: {
  data: ModelsResponse | null;
  loading: boolean;
  query: string;
  onPick: (route: string) => void;
}) {
  if (loading && !data) return <div className="empty"><p>Discovering models…</p></div>;
  if (data && data.groups.length === 0) {
    return (
      <EmptyState icon={<IconGrid />} title="No chat models discoverable">
        Add a provider API key (e.g. <code className="mono">OPENAI_API_KEY</code>) to <code className="mono">.env</code> and restart the hub to light up its models here.
      </EmptyState>
    );
  }
  return (
    <>
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
      {data?.groups.map(g => (
        <ProviderRow
          key={g.provider}
          group={g}
          query={query}
          forceOpen={!!query}
          onPick={onPick}
        />
      ))}
    </>
  );
}

function AgentsTab() {
  const [data, setData] = useState<AgentsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      setData(await api.agents());
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  if (loading && !data) return <div className="empty"><p>Discovering agents…</p></div>;
  if (error) {
    return (
      <EmptyState icon={<IconAlert />} title="Couldn't discover agents">{error}</EmptyState>
    );
  }
  if (!data || data.agents.length === 0) {
    return (
      <EmptyState icon={<IconTerminal />} title="No coding agents detected">
        Install at least one supported CLI (Claude Code, Codex, Gemini, Qwen, Aider, OpenCode, Cursor Agent, Crush) and refresh.
      </EmptyState>
    );
  }

  const available = data.agents.filter(a => a.available).length;

  return (
    <>
      <div className="card card-pad mb24" style={{
        background: "var(--accent-softer)",
        borderColor: "transparent",
      }}>
        <div className="row" style={{ gap: 12, alignItems: "flex-start" }}>
          <span className="empty-ico" style={{
            width: 38, height: 38, marginBottom: 0, borderRadius: 10,
          }}>
            <IconTerminal style={{ width: 19, height: 19 }} />
          </span>
          <div>
            <div className="strong" style={{ fontWeight: 700, fontSize: 14.5 }}>
              {available} of {data.agents.length} coding agents ready on this host
            </div>
            <div className="muted" style={{ fontSize: 13, marginTop: 3, maxWidth: "70ch" }}>
              Prompture discovers terminal coding-agent CLIs on the operator's
              machine. The cards below describe what each agent supports;
              "Not installed" rows include the install command.
            </div>
          </div>
        </div>
      </div>

      <div className="agent-grid">
        {data.agents.map(a => <AgentCard key={a.id} agent={a} />)}
      </div>
    </>
  );
}

function ModalitiesTab() {
  const [data, setData] = useState<ModalitiesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [picked, setPicked] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      setData(await api.modalities());
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  if (loading && !data) return <div className="empty"><p>Discovering modalities…</p></div>;
  if (error) {
    return <EmptyState icon={<IconAlert />} title="Couldn't discover modalities">{error}</EmptyState>;
  }
  if (!data) return null;

  const sections: Array<[string, ModalitySection]> = [
    ["image_gen", data.image_gen],
    ["video_gen", data.video_gen],
    ["tts", data.tts],
    ["stt", data.stt],
    ["embeddings", data.embeddings],
    ["rerank", data.rerank],
    ["moderation", data.moderation],
  ];

  const populated = sections.filter(([, s]) => s.total > 0);

  if (populated.length === 0) {
    return (
      <EmptyState icon={<IconLayers />} title="No specialised modalities configured">
        Add API keys for image / video / audio / embedding / rerank /
        moderation providers (e.g. <code className="mono">ELEVENLABS_API_KEY</code>,
        {" "}<code className="mono">RUNWAY_API_KEY</code>) and restart.
      </EmptyState>
    );
  }

  return (
    <>
      {populated.map(([key, section]) => (
        <div key={key} style={{ marginBottom: 28 }}>
          <div className="row between" style={{ marginBottom: 10 }}>
            <h2 className="section-title">{section.label}</h2>
            <span className="faint" style={{ fontSize: 12.5 }}>
              <strong className="mono tnum">{section.total}</strong> model{section.total !== 1 ? "s" : ""}
              {" "}across <strong>{section.groups.length}</strong> provider{section.groups.length !== 1 ? "s" : ""}
            </span>
          </div>
          {section.discovery_error && (
            <div className="discovery-fail mb16" role="alert" style={{
              borderRadius: "var(--r-md)",
              border: "1px solid var(--warn)",
              background: "var(--warn-soft)",
            }}>
              <IconAlert />
              <span className="mono">{section.discovery_error}</span>
            </div>
          )}
          {section.groups.map(g => (
            <ProviderRow
              key={`${key}-${g.provider}`}
              group={g}
              query=""
              forceOpen={false}
              onPick={setPicked}
            />
          ))}
        </div>
      ))}
      {picked && <SnippetModal route={picked} onClose={() => setPicked(null)} />}
    </>
  );
}

// ---------------------------------------------------------------------------

export function ModelsPage() {
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab) || "models";

  const [data, setData] = useState<ModelsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState<string | null>(null);

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

  const setTab = (t: Tab) => {
    setParams(p => {
      const next = new URLSearchParams(p);
      if (t === "models") next.delete("tab");
      else next.set("tab", t);
      return next;
    });
  };

  return (
    <div className="container">
      <div className="page-head">
        <div className="grow">
          <h1 className="page-title">Models &amp; agents</h1>
          <p className="page-sub">
            Everything the hub can route, addressed as{" "}
            <code className="mono" style={{
              background: "var(--accent-softer)",
              color: "var(--accent-strong)",
              padding: "1px 6px",
              borderRadius: 4,
            }}>provider/model</code>.{" "}
            <strong className="mono tnum">{totalModels}</strong> chat models across{" "}
            <strong>{providerCount}</strong> providers, plus coding agents and
            specialised modalities.
          </p>
        </div>
        <button className="btn" onClick={load}>
          <IconRefresh style={{ width: 14, height: 14 }} />Refresh
        </button>
      </div>

      <div className="row mb24" style={{ gap: 10 }}>
        <div className="seg">
          <button
            className={tab === "models" ? "on" : ""}
            onClick={() => setTab("models")}
          >
            <IconGrid />Chat models
          </button>
          <button
            className={tab === "agents" ? "on" : ""}
            onClick={() => setTab("agents")}
          >
            <IconTerminal />Coding agents
          </button>
          <button
            className={tab === "modalities" ? "on" : ""}
            onClick={() => setTab("modalities")}
          >
            <IconLayers />Other modalities
          </button>
        </div>
      </div>

      {tab === "models" && (
        <>
          <RoutingExplain />

          <div className="toolbar mb16">
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

          <ModelsTab data={data} loading={loading} query={query} onPick={setPicked} />
        </>
      )}

      {tab === "agents" && <AgentsTab />}
      {tab === "modalities" && <ModalitiesTab />}

      {picked && <SnippetModal route={picked} onClose={() => setPicked(null)} />}
    </div>
  );
}
