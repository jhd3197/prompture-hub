import {
  createContext, useCallback, useContext, useEffect, useId, useMemo, useRef, useState, type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { useLocation, useNavigate } from "react-router-dom";
import {
  IconActivity, IconBolt, IconCog, IconCopy, IconDevice, IconDocs, IconDollar, IconExternal, IconGrid, IconHome,
  IconKey, IconKeyboard, IconLogout, IconMessages, IconMoon, IconPlus, IconSearch, IconSliders, IconSun, IconX,
} from "../icons";
import { ensureCatalog, useCatalog } from "../util/catalog";
import { useFocusTrap } from "../util/hooks";
import { useDensity, useTheme } from "../theme";
import { useToast } from "./Toast";

/* ---------- fuzzy match: ordered subsequence with word-start and run bonuses ---------- */
export function fuzzy(query: string, text: string): { score: number; marks: number[] } | null {
  const q = query.toLowerCase().replace(/\s+/g, "");
  if (!q) return { score: 0, marks: [] };
  const t = text.toLowerCase();
  const marks: number[] = [];
  let score = 0;
  let ti = 0;
  let run = 0;
  for (const ch of q) {
    const at = t.indexOf(ch, ti);
    if (at < 0) return null;
    const wordStart = at === 0 || /[\s/_\-.:]/.test(t[at - 1]);
    run = at === ti && marks.length ? run + 1 : 0;
    score += 1 + (wordStart ? 4 : 0) + run * 3 - Math.min(at - ti, 6) * 0.3;
    marks.push(at);
    ti = at + 1;
  }
  if (t.startsWith(q)) score += 8;
  return { score: score - t.length * 0.02, marks };
}

function Highlight({ text, marks }: { text: string; marks: number[] }) {
  if (!marks.length) return <>{text}</>;
  const set = new Set(marks);
  return <>{Array.from(text).map((c, i) => (set.has(i) ? <mark key={i}>{c}</mark> : c))}</>;
}

/* ---------- commands ---------- */
interface Command {
  id: string;
  group: "Pages" | "Actions" | "Keys" | "Sessions";
  label: string;
  sub?: string;
  keywords?: string;
  icon: ReactNode;
  hint?: string[];
  run: () => void;
}

const PAGES: Array<{ to: string; label: string; chord: string; icon: ReactNode; kw: string }> = [
  { to: "/", label: "Home", chord: "h", icon: <IconHome />, kw: "overview dashboard" },
  { to: "/analytics", label: "Analytics", chord: "a", icon: <IconActivity />, kw: "usage traffic errors latency" },
  { to: "/billing", label: "Billing", chord: "b", icon: <IconDollar />, kw: "reconciliation spend provider" },
  { to: "/keys", label: "Keys", chord: "k", icon: <IconKey />, kw: "hub keys caps limits" },
  { to: "/conversations", label: "Sessions", chord: "c", icon: <IconMessages />, kw: "conversations chat" },
  { to: "/models", label: "Models", chord: "m", icon: <IconGrid />, kw: "providers routes" },
  { to: "/pair", label: "Pair a device", chord: "p", icon: <IconDevice />, kw: "companion code" },
  { to: "/settings", label: "Settings", chord: "s", icon: <IconCog />, kw: "appearance network api devices alerts endpoints" },
];

interface Ctx { openPalette: () => void; openShortcuts: () => void }
const CommandCtx = createContext<Ctx>({ openPalette: () => {}, openShortcuts: () => {} });
export const useCommands = () => useContext(CommandCtx);

const isTyping = (t: EventTarget | null): boolean => {
  const el = t as HTMLElement | null;
  if (!el) return false;
  return el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName);
};

export function CommandProvider({ children }: { children: ReactNode }) {
  const [palette, setPalette] = useState(false);
  const [sheet, setSheet] = useState(false);
  const [pending, setPending] = useState(false);
  const navigate = useNavigate();
  const loc = useLocation();
  const chord = useRef<number | null>(null);

  const openPalette = useCallback(() => { setSheet(false); setPalette(true); }, []);
  const openShortcuts = useCallback(() => { setPalette(false); setSheet(true); }, []);

  useEffect(() => {
    const clear = () => { if (chord.current) window.clearTimeout(chord.current); chord.current = null; setPending(false); };
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented) return;
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault(); clear();
        setSheet(false); setPalette(p => !p);
        return;
      }
      if (e.metaKey || e.ctrlKey || e.altKey || isTyping(e.target)) return;
      if (document.querySelector('[aria-modal="true"]')) return;
      if (pending) {
        const hit = PAGES.find(p => p.chord === e.key.toLowerCase());
        clear();
        if (hit) { e.preventDefault(); navigate(hit.to); }
        return;
      }
      if (e.key === "/") { e.preventDefault(); openPalette(); }
      else if (e.key === "?") { e.preventDefault(); openShortcuts(); }
      else if (e.key === "g") {
        setPending(true);
        chord.current = window.setTimeout(clear, 1400);
      } else if (e.key === "c") { e.preventDefault(); navigate("/keys/new"); }
    };
    window.addEventListener("keydown", onKey);
    return () => { window.removeEventListener("keydown", onKey); if (chord.current) window.clearTimeout(chord.current); };
  }, [pending, navigate, openPalette, openShortcuts]);

  // Any navigation closes whatever is open.
  useEffect(() => { setPalette(false); setSheet(false); }, [loc.pathname]);

  return (
    <CommandCtx.Provider value={{ openPalette, openShortcuts }}>
      {children}
      {palette && <Palette onClose={() => setPalette(false)} openShortcuts={openShortcuts} />}
      {sheet && <ShortcutSheet onClose={() => setSheet(false)} />}
      {pending && (
        <div className="chord-hint" role="status">
          <span className="kbd">g</span> then
          {PAGES.map(p => <span key={p.chord}><span className="kbd">{p.chord}</span> {p.label.replace("Pair a device", "Pair")}</span>)}
        </div>
      )}
    </CommandCtx.Provider>
  );
}

function Palette({ onClose, openShortcuts }: { onClose: () => void; openShortcuts: () => void }) {
  const navigate = useNavigate();
  const toast = useToast();
  const [theme, toggleTheme] = useTheme();
  const [density, setDensity] = useDensity();
  const { keys, sessions } = useCatalog();
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const root = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const uid = useId();
  useFocusTrap(root, true, input);

  useEffect(() => { ensureCatalog(); }, []);
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, []);

  const go = useCallback((to: string) => () => navigate(to), [navigate]);
  const copy = useCallback((text: string, what: string) => async () => {
    try { await navigator.clipboard.writeText(text); } catch { /* clipboard can be blocked */ }
    toast(`Copied ${what}`);
  }, [toast]);

  const commands = useMemo<Command[]>(() => {
    const out: Command[] = PAGES.map(p => ({
      id: `page:${p.to}`, group: "Pages", label: p.label, keywords: p.kw, icon: p.icon, hint: ["g", p.chord], run: go(p.to),
    }));
    out.push(
      { id: "act:new-key", group: "Actions", label: "Create a hub key", keywords: "new issue add", icon: <IconPlus />, hint: ["c"], run: go("/keys/new") },
      { id: "act:theme", group: "Actions", label: theme === "dark" ? "Switch to light theme" : "Switch to dark theme", keywords: "appearance mode", icon: theme === "dark" ? <IconSun /> : <IconMoon />, run: toggleTheme },
      { id: "act:density", group: "Actions", label: density === "compact" ? "Use comfortable table density" : "Use compact table density", keywords: "rows tables", icon: <IconSliders />, run: () => setDensity(density === "compact" ? "comfortable" : "compact") },
      { id: "act:hub-url", group: "Actions", label: "Copy hub URL", keywords: "origin address base", icon: <IconCopy />, run: copy(window.location.origin, "hub URL") },
      { id: "act:api-url", group: "Actions", label: "Copy API base URL", keywords: "v1 openai endpoint", icon: <IconCopy />, run: copy(`${window.location.origin}/v1`, "API base URL") },
      { id: "act:alerts", group: "Actions", label: "Alert rules", keywords: "notifications webhook ntfy", icon: <IconBolt />, run: go("/settings/alerts") },
      { id: "act:docs", group: "Actions", label: "Open API docs", keywords: "swagger openapi", icon: <IconDocs />, run: () => { window.open("/docs", "_blank", "noopener"); } },
      { id: "act:keys-help", group: "Actions", label: "Keyboard shortcuts", keywords: "help keys hotkeys", icon: <IconKeyboard />, hint: ["?"], run: openShortcuts },
      { id: "act:logout", group: "Actions", label: "Log out", keywords: "sign out", icon: <IconLogout />, run: () => { window.location.href = "/auth/logout"; } },
    );
    for (const k of keys ?? []) {
      out.push({
        id: `key:${k.id}`, group: "Keys", label: k.name, sub: `key #${k.id}${k.active ? "" : k.revoked_at ? " revoked" : " expired"}`,
        keywords: `${k.default_project ?? ""} ${k.prefix ?? ""}`, icon: <IconKey />, run: go(`/keys?key=${k.id}`),
      });
    }
    for (const s of (sessions ?? []).slice(0, 40)) {
      out.push({
        id: `ses:${s.id}`, group: "Sessions", label: s.title || s.id, sub: s.model ?? undefined,
        keywords: s.model ?? "", icon: <IconMessages />, run: go(`/conversations?s=${encodeURIComponent(s.id)}`),
      });
    }
    return out;
  }, [theme, density, keys, sessions, go, copy, toggleTheme, setDensity, openShortcuts]);

  const results = useMemo(() => {
    const order: Command["group"][] = ["Pages", "Actions", "Keys", "Sessions"];
    const caps: Record<string, number> = q ? { Pages: 6, Actions: 6, Keys: 6, Sessions: 5 } : { Pages: 8, Actions: 9, Keys: 4, Sessions: 3 };
    const groups = order.map(g => {
      const items = commands
        .filter(c => c.group === g)
        .map(c => {
          const m = fuzzy(q, c.label) ?? (c.keywords || c.sub ? fuzzy(q, `${c.keywords ?? ""} ${c.sub ?? ""}`) : null);
          const own = fuzzy(q, c.label);
          return m ? { c, score: (own ? own.score + 10 : m.score), marks: own?.marks ?? [] } : null;
        })
        .filter((x): x is { c: Command; score: number; marks: number[] } => !!x);
      if (q) items.sort((a, b) => b.score - a.score);
      return { g, items: items.slice(0, caps[g]) };
    }).filter(x => x.items.length);
    return groups;
  }, [commands, q]);

  const flat = useMemo(() => results.flatMap(r => r.items), [results]);
  useEffect(() => setActive(0), [q]);
  useEffect(() => {
    list.current?.querySelector<HTMLElement>(`[data-idx="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active]);

  const run = (i: number) => { const hit = flat[i]; if (!hit) return; onClose(); hit.c.run(); };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setActive(a => Math.min(flat.length - 1, a + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive(a => Math.max(0, a - 1)); }
    else if (e.key === "Home") { e.preventDefault(); setActive(0); }
    else if (e.key === "End") { e.preventDefault(); setActive(flat.length - 1); }
    else if (e.key === "Enter") { e.preventDefault(); run(active); }
    else if (e.key === "Escape") { e.preventDefault(); onClose(); }
  };

  let idx = -1;
  return createPortal(
    <div className="overlay palette-overlay" onMouseDown={onClose}>
      <div
        ref={root} className="palette" role="dialog" aria-modal="true" aria-label="Command palette"
        onMouseDown={e => e.stopPropagation()} onKeyDown={onKey}
      >
        <div className="palette-input">
          <IconSearch />
          <input
            ref={input} value={q} onChange={e => setQ(e.target.value)} placeholder="Search pages, keys, sessions and actions"
            role="combobox" aria-expanded="true" aria-controls={`${uid}-list`} aria-autocomplete="list"
            aria-activedescendant={flat[active] ? `${uid}-${active}` : undefined} aria-label="Search commands"
            autoComplete="off" spellCheck={false}
          />
          <button type="button" className="icon-btn" aria-label="Close palette" onClick={onClose}><IconX /></button>
        </div>
        <div className="palette-list" id={`${uid}-list`} role="listbox" aria-label="Results" ref={list}>
          {flat.length === 0 && <div className="palette-empty">Nothing matches &ldquo;{q}&rdquo;. Try a page name, a key name or an action.</div>}
          {results.map(r => (
            <div role="group" aria-labelledby={`${uid}-g-${r.g}`} key={r.g}>
              <div className="palette-group caption" id={`${uid}-g-${r.g}`}>{r.g}</div>
              {r.items.map(({ c, marks }) => {
                idx += 1;
                const i = idx;
                return (
                  <div
                    key={c.id} id={`${uid}-${i}`} data-idx={i} role="option" aria-selected={i === active}
                    className="palette-opt" onMouseMove={() => active !== i && setActive(i)} onClick={() => run(i)}
                  >
                    {c.icon}
                    <span className="opt-main">
                      <Highlight text={c.label} marks={marks} />
                      {c.sub && <span className="opt-sub">{c.sub}</span>}
                    </span>
                    {c.hint && <span className="kbd-group" aria-hidden="true">{c.hint.map(h => <span className="kbd" key={h}>{h}</span>)}</span>}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
        <div className="palette-foot" aria-hidden="true">
          <span><span className="kbd">↑</span><span className="kbd">↓</span> move</span>
          <span><span className="kbd">↵</span> open</span>
          <span><span className="kbd">esc</span> close</span>
          <span style={{ marginLeft: "auto" }}><span className="kbd">g</span> then a letter jumps to a page</span>
        </div>
      </div>
    </div>,
    document.body,
  );
}

function ShortcutSheet({ onClose }: { onClose: () => void }) {
  const root = useRef<HTMLDivElement>(null);
  const id = useId();
  useFocusTrap(root);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const Row = ({ keys, label }: { keys: string[]; label: string }) => (
    <>
      <dt>{label}</dt>
      <dd><span className="kbd-group">{keys.map((k, i) => <span key={i} className="kbd">{k}</span>)}</span></dd>
    </>
  );
  return createPortal(
    <div className="overlay" onMouseDown={onClose}>
      <div ref={root} className="modal" role="dialog" aria-modal="true" aria-labelledby={id} onMouseDown={e => e.stopPropagation()}>
        <div className="modal-head">
          <div className="row between">
            <h2 id={id}>Keyboard shortcuts</h2>
            <button type="button" className="icon-btn" aria-label="Close dialog" onClick={onClose}><IconX /></button>
          </div>
        </div>
        <div className="modal-body">
          <div>
            <p className="caption shortcut-group">Anywhere</p>
            <dl className="shortcut-grid">
              <Row keys={["Ctrl", "K"]} label="Open the palette (Cmd K on Mac)" />
              <Row keys={["/"]} label="Open the palette" />
              <Row keys={["?"]} label="Show this sheet" />
              <Row keys={["c"]} label="Create a hub key" />
            </dl>
          </div>
          <div>
            <p className="caption shortcut-group">Go to (press g, then a letter)</p>
            <dl className="shortcut-grid">
              {PAGES.map(p => <Row key={p.to} keys={["g", p.chord]} label={p.label} />)}
            </dl>
          </div>
          <div>
            <p className="caption shortcut-group">Palette and tables</p>
            <dl className="shortcut-grid">
              <Row keys={["↑", "↓"]} label="Move through results or table rows" />
              <Row keys={["↵"]} label="Run the highlighted result" />
              <Row keys={["Esc"]} label="Close the open panel" />
            </dl>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
