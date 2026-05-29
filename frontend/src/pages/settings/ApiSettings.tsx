import { useEffect, useMemo, useState } from "react";
import { CopyButton } from "../../components/CopyButton";
import { EmptyState } from "../../components/EmptyState";
import {
  IconAlert, IconChevronRight, IconCode, IconExternal, IconSearch, IconX,
} from "../../icons";

interface OpenApiOperation {
  tags?: string[];
  summary?: string;
  description?: string;
  parameters?: Array<Record<string, unknown>>;
  requestBody?: Record<string, unknown>;
  responses?: Record<string, Record<string, unknown>>;
}

type Methods = "get" | "post" | "put" | "delete" | "patch";

interface OpenApiSchema {
  openapi: string;
  info: { title: string; version: string };
  paths: Record<string, Partial<Record<Methods, OpenApiOperation>>>;
}

interface FlatOp {
  path: string;
  method: Methods;
  op: OpenApiOperation;
  tag: string;
}

const METHOD_COLOR: Record<Methods, string> = {
  get:    "var(--info)",
  post:   "var(--accent-strong)",
  put:    "var(--warn)",
  patch:  "var(--warn)",
  delete: "var(--danger)",
};

function flatten(schema: OpenApiSchema): FlatOp[] {
  const out: FlatOp[] = [];
  for (const [path, methods] of Object.entries(schema.paths)) {
    for (const method of ["get", "post", "put", "delete", "patch"] as Methods[]) {
      const op = methods[method];
      if (!op) continue;
      const tag = op.tags?.[0] || "other";
      out.push({ path, method, op, tag });
    }
  }
  out.sort((a, b) => {
    if (a.tag !== b.tag) return a.tag.localeCompare(b.tag);
    if (a.path !== b.path) return a.path.localeCompare(b.path);
    return a.method.localeCompare(b.method);
  });
  return out;
}

function OperationRow({ flat }: { flat: FlatOp }) {
  const [open, setOpen] = useState(false);
  const { method, path, op } = flat;
  return (
    <div
      className="card"
      style={{
        padding: 0,
        marginBottom: 4,
        background: "var(--surface)",
        boxShadow: "none",
      }}
    >
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          width: "100%",
          padding: "10px 14px",
          border: "none",
          background: "transparent",
          textAlign: "left",
          cursor: "pointer",
          color: "inherit",
        }}
      >
        <IconChevronRight
          style={{
            width: 14, height: 14,
            transform: open ? "rotate(90deg)" : "none",
            transition: "transform .15s",
            color: "var(--text-3)",
          }}
        />
        <span
          className="mono"
          style={{
            color: METHOD_COLOR[method],
            fontWeight: 800,
            fontSize: 11,
            textTransform: "uppercase",
            letterSpacing: "0.04em",
            minWidth: 50,
            textAlign: "right",
          }}
        >
          {method}
        </span>
        <code
          className="mono"
          style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}
        >
          {path}
        </code>
        {op.summary && (
          <span
            className="faint"
            style={{
              fontSize: 12.5,
              marginLeft: "auto",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              maxWidth: "50%",
            }}
          >
            {op.summary}
          </span>
        )}
      </button>

      {open && (
        <div
          style={{
            padding: "12px 14px 14px 40px",
            borderTop: "1px solid var(--border)",
            background: "var(--surface-2)",
            fontSize: 13,
          }}
        >
          {op.description && (
            <p style={{ margin: "0 0 12px", color: "var(--text-2)", whiteSpace: "pre-wrap" }}>
              {op.description}
            </p>
          )}

          {op.parameters && op.parameters.length > 0 && (
            <details style={{ marginBottom: 10 }}>
              <summary className="faint" style={{ cursor: "pointer", fontSize: 12 }}>
                {op.parameters.length} parameter{op.parameters.length !== 1 ? "s" : ""}
              </summary>
              <pre
                className="code"
                style={{ marginTop: 6, fontSize: 11, maxHeight: 200, overflow: "auto" }}
              >
                {JSON.stringify(op.parameters, null, 2)}
              </pre>
            </details>
          )}

          {op.requestBody && (
            <details style={{ marginBottom: 10 }}>
              <summary className="faint" style={{ cursor: "pointer", fontSize: 12 }}>
                Request body
              </summary>
              <pre
                className="code"
                style={{ marginTop: 6, fontSize: 11, maxHeight: 240, overflow: "auto" }}
              >
                {JSON.stringify(op.requestBody, null, 2)}
              </pre>
            </details>
          )}

          {op.responses && (
            <details>
              <summary className="faint" style={{ cursor: "pointer", fontSize: 12 }}>
                Responses ({Object.keys(op.responses).join(", ")})
              </summary>
              <pre
                className="code"
                style={{ marginTop: 6, fontSize: 11, maxHeight: 280, overflow: "auto" }}
              >
                {JSON.stringify(op.responses, null, 2)}
              </pre>
            </details>
          )}
        </div>
      )}
    </div>
  );
}

export function ApiSettings() {
  const [schema, setSchema] = useState<OpenApiSchema | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");

  useEffect(() => {
    let alive = true;
    fetch("/openapi.json")
      .then(r => r.ok ? r.json() : Promise.reject(`${r.status} ${r.statusText}`))
      .then(s => { if (alive) { setSchema(s); setLoading(false); } })
      .catch(e => { if (alive) { setError(String(e)); setLoading(false); } });
    return () => { alive = false; };
  }, []);

  const flat = useMemo(() => schema ? flatten(schema) : [], [schema]);

  const q = query.trim().toLowerCase();
  const filtered = q
    ? flat.filter(f =>
        f.path.toLowerCase().includes(q) ||
        f.method.toLowerCase().includes(q) ||
        f.tag.toLowerCase().includes(q) ||
        (f.op.summary && f.op.summary.toLowerCase().includes(q)),
      )
    : flat;

  // Group by tag.
  const grouped: Array<[string, FlatOp[]]> = useMemo(() => {
    const m = new Map<string, FlatOp[]>();
    for (const f of filtered) {
      const arr = m.get(f.tag) || [];
      arr.push(f);
      m.set(f.tag, arr);
    }
    return Array.from(m.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [filtered]);

  if (loading && !schema) return <div className="empty"><p>Loading OpenAPI…</p></div>;
  if (error) return <EmptyState icon={<IconAlert />} title="Couldn't load OpenAPI">{error}</EmptyState>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div className="card card-pad">
        <div className="row between" style={{ marginBottom: 8 }}>
          <div>
            <h2 className="section-title">API surface</h2>
            <p className="muted" style={{ margin: "4px 0 0", fontSize: 13 }}>
              <strong className="tnum">{flat.length}</strong> operations across{" "}
              <strong>{new Set(flat.map(f => f.tag)).size}</strong> groups.{" "}
              Generated from the live <code className="mono">/openapi.json</code>.
            </p>
          </div>
          <div className="row" style={{ gap: 8 }}>
            <a
              href="/docs"
              target="_blank"
              rel="noopener noreferrer"
              className="btn btn-sm"
              title="Open the auto-generated Swagger UI in a new tab"
            >
              <IconExternal style={{ width: 13, height: 13 }} />Swagger UI
            </a>
            <CopyButton
              text={`${window.location.origin}/openapi.json`}
              label="Copy schema URL"
              className="btn btn-sm"
            />
          </div>
        </div>

        <div className="toolbar" style={{ marginTop: 14 }}>
          <div className="search" style={{ flex: 1 }}>
            <IconSearch />
            <input
              placeholder="Search by path, method, summary… e.g. /v1/chat, conversations, delete"
              value={query}
              onChange={e => setQuery(e.target.value)}
              aria-label="Filter API operations"
            />
          </div>
          {query && (
            <button className="btn btn-sm btn-ghost" onClick={() => setQuery("")}>
              <IconX />Clear
            </button>
          )}
        </div>
      </div>

      {grouped.length === 0 ? (
        <EmptyState icon={<IconCode />} title="No operations match">
          Try clearing the filter or {query && <code className="mono">{query}</code>} broadening the search.
        </EmptyState>
      ) : (
        grouped.map(([tag, ops]) => (
          <div key={tag} className="card" style={{ padding: 0 }}>
            <div
              className="card-head"
              style={{
                padding: "10px 14px",
                background: "var(--surface-2)",
              }}
            >
              <h3 style={{ fontSize: 13, textTransform: "uppercase", letterSpacing: "0.04em" }}>
                {tag}
              </h3>
              <span className="sub">
                {ops.length} operation{ops.length !== 1 ? "s" : ""}
              </span>
            </div>
            <div style={{ padding: 6 }}>
              {ops.map(op => (
                <OperationRow key={`${op.method}-${op.path}`} flat={op} />
              ))}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
