import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import {
  IconChevronRight, IconSearch, IconX,
} from "../icons";
import type { ProviderGroup } from "../types";
import { ProviderLogo } from "./ProviderLogo";

interface Props {
  /** Currently selected models, as ``provider/model`` strings. */
  value: string[];
  onChange: (next: string[]) => void;
}

/**
 * Provider-grouped checkbox tree. Each provider row shows its logo,
 * display name, and a "selected / total" counter; clicking expands the
 * model list. Per-provider "select all" toggles every model under that
 * provider in or out, individual models have their own checkboxes.
 *
 * Empty selection means "any model" — see the caller's hint copy.
 */
export function ModelGroupedPicker({ value, onChange }: Props) {
  const [groups, setGroups] = useState<ProviderGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [openProviders, setOpenProviders] = useState<Set<string>>(new Set());

  useEffect(() => {
    let alive = true;
    api.models()
      .then(d => { if (alive) { setGroups(d.groups); setLoading(false); } })
      .catch(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);

  const selectedSet = useMemo(() => new Set(value), [value]);

  const toggleProvider = (provider: string) => {
    setOpenProviders(prev => {
      const next = new Set(prev);
      if (next.has(provider)) next.delete(provider);
      else next.add(provider);
      return next;
    });
  };

  const toggleModel = (route: string) => {
    if (selectedSet.has(route)) {
      onChange(value.filter(v => v !== route));
    } else {
      onChange([...value, route]);
    }
  };

  const toggleAllInProvider = (provider: string, models: string[], allOn: boolean) => {
    const routes = models.map(m => `${provider}/${m}`);
    if (allOn) {
      onChange(value.filter(v => !routes.includes(v)));
    } else {
      const existing = new Set(value);
      for (const r of routes) existing.add(r);
      onChange(Array.from(existing));
    }
  };

  const clearAll = () => onChange([]);

  const q = query.trim().toLowerCase();
  const filteredGroups = q
    ? groups
        .map(g => ({
          ...g,
          models: g.models.filter(m =>
            `${g.provider}/${m}`.toLowerCase().includes(q) ||
            (g.display_name && g.display_name.toLowerCase().includes(q)),
          ),
        }))
        .filter(g => g.models.length > 0)
    : groups;

  const totalSelected = value.length;
  const totalAvailable = groups.reduce((n, g) => n + g.models.length, 0);

  return (
    <div
      style={{
        border: "1px solid var(--border-strong)",
        borderRadius: "var(--r-md)",
        background: "var(--surface)",
        display: "flex",
        flexDirection: "column",
        maxHeight: 460,
        minHeight: 280,
      }}
    >
      {/* search bar */}
      <div
        style={{
          padding: 10,
          borderBottom: "1px solid var(--border)",
          background: "var(--surface-2)",
          display: "flex",
          alignItems: "center",
          gap: 8,
        }}
      >
        <div className="search" style={{ flex: 1 }}>
          <IconSearch />
          <input
            placeholder="Search models or providers… e.g. claude, gpt-4, openai/"
            value={query}
            onChange={e => setQuery(e.target.value)}
            aria-label="Filter models"
          />
        </div>
        <span
          className="badge"
          title={`${totalSelected} of ${totalAvailable} models selected`}
          style={{ whiteSpace: "nowrap" }}
        >
          <strong className="tnum">{totalSelected}</strong>
          <span className="faint">/ {totalAvailable}</span>
        </span>
        {totalSelected > 0 && (
          <button
            type="button"
            className="btn btn-sm btn-ghost"
            onClick={clearAll}
            title="Clear all selections"
          >
            <IconX style={{ width: 12, height: 12 }} />
            Clear
          </button>
        )}
      </div>

      {/* body */}
      <div style={{ flex: 1, overflow: "auto", padding: 8 }}>
        {loading ? (
          <p className="faint" style={{ padding: 14, margin: 0, fontSize: 13 }}>
            Loading models…
          </p>
        ) : filteredGroups.length === 0 ? (
          <p className="faint" style={{ padding: 14, margin: 0, fontSize: 13 }}>
            {q
              ? <>No matches for <code className="mono">{query}</code>.</>
              : "No models discoverable. Add a provider API key to .env and restart."}
          </p>
        ) : (
          filteredGroups.map(g => {
            const isOpen = openProviders.has(g.provider) || !!q;
            const initials = g.provider.slice(0, 2).toUpperCase();
            const allRoutes = g.models.map(m => `${g.provider}/${m}`);
            const selectedCount = allRoutes.filter(r => selectedSet.has(r)).length;
            const allOn = selectedCount === allRoutes.length && allRoutes.length > 0;
            const someOn = selectedCount > 0 && !allOn;

            return (
              <div key={g.provider} style={{ marginBottom: 6 }}>
                <div
                  className={`provider-bar ${isOpen ? "open" : ""}`}
                  style={{ cursor: "pointer", padding: "8px 12px" }}
                  onClick={() => toggleProvider(g.provider)}
                  role="button"
                  tabIndex={0}
                  aria-expanded={isOpen}
                  onKeyDown={e => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      toggleProvider(g.provider);
                    }
                  }}
                >
                  <span className="provider-chevron">
                    <IconChevronRight style={{ width: 14, height: 14 }} />
                  </span>
                  <ProviderLogo
                    iconUrl={g.icon_url}
                    brandColor={g.brand_color}
                    fallback={initials}
                    size={28}
                  />
                  <div className="grow" style={{ minWidth: 0 }}>
                    <div className="row" style={{ gap: 8 }}>
                      <span className="provider-name" style={{ fontSize: 13.5 }}>
                        {g.display_name || g.provider}
                      </span>
                      <span className="mono faint" style={{ fontSize: 11 }}>
                        {g.provider}/
                      </span>
                      {g.is_local && (
                        <span className="badge" style={{ fontSize: 10 }}>local</span>
                      )}
                    </div>
                    <div className="provider-meta" style={{ fontSize: 11.5 }}>
                      {selectedCount > 0 ? (
                        <span style={{ color: "var(--accent-strong)", fontWeight: 600 }}>
                          {selectedCount} of {allRoutes.length} selected
                        </span>
                      ) : (
                        <span>{allRoutes.length} model{allRoutes.length !== 1 ? "s" : ""}</span>
                      )}
                    </div>
                  </div>
                  <label
                    className="row"
                    style={{ gap: 6, fontSize: 12 }}
                    onClick={e => e.stopPropagation()}
                  >
                    <input
                      type="checkbox"
                      checked={allOn}
                      ref={el => { if (el) el.indeterminate = someOn; }}
                      onChange={() => toggleAllInProvider(g.provider, g.models, allOn)}
                      style={{ accentColor: "var(--accent)" }}
                    />
                    <span className="faint">All</span>
                  </label>
                </div>

                {isOpen && (
                  <div className="model-table" style={{ marginBottom: 4 }}>
                    {g.models.map(m => {
                      const route = `${g.provider}/${m}`;
                      const checked = selectedSet.has(route);
                      return (
                        <label
                          key={route}
                          className="model-row"
                          style={{
                            cursor: "pointer",
                            gridTemplateColumns: "20px 1fr",
                            background: checked ? "var(--accent-softer)" : undefined,
                          }}
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => toggleModel(route)}
                            style={{ accentColor: "var(--accent)" }}
                          />
                          <span className="route-pill" title={route}>
                            <span className="rp-prov">{g.provider}</span>
                            <span className="rp-sep">/</span>
                            <span className="rp-model">{m}</span>
                          </span>
                        </label>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
