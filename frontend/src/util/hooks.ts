import { useCallback, useEffect, useRef, useState, type RefObject } from "react";
import { errText } from "./format";

export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

/** Sets the tab title for the current route. */
export function usePageTitle(title: string): void {
  useEffect(() => {
    document.title = `${title} · Prompture Hub`;
  }, [title]);
}

export interface Async<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
  setData: (next: T) => void;
}

/** Runs `fn` on mount and whenever `deps` change; the latest call wins. `reload` re-runs it without clearing data. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []): Async<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const seq = useRef(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    const mine = ++seq.current;
    setLoading(true);
    setError(null);
    fnRef.current()
      .then(v => { if (mine === seq.current) setData(v); })
      .catch(e => { if (mine === seq.current) setError(errText(e)); })
      .finally(() => { if (mine === seq.current) setLoading(false); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  useEffect(() => () => { seq.current += 1; }, []);
  const reload = useCallback(() => setTick(t => t + 1), []);
  return { data, error, loading, reload, setData };
}

/** Eases from 0 to `value` once; renders `value` straight away under reduced motion. */
export function useCountUp(value: number, duration = 700): number {
  const [shown, setShown] = useState(() => (prefersReducedMotion() ? value : 0));
  const from = useRef(prefersReducedMotion() ? value : 0);
  useEffect(() => {
    if (prefersReducedMotion()) { setShown(value); from.current = value; return; }
    const start = performance.now();
    const origin = from.current;
    let raf = 0;
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      const v = origin + (value - origin) * eased;
      setShown(v);
      from.current = v;
      if (t < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [value, duration]);
  return shown;
}

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** Keeps Tab inside `ref` while `active`, focuses the first field on open and restores focus on close. */
export function useFocusTrap(ref: RefObject<HTMLElement>, active = true, initial?: RefObject<HTMLElement>): void {
  useEffect(() => {
    if (!active) return;
    const root = ref.current;
    if (!root) return;
    const opener = document.activeElement as HTMLElement | null;
    const first = initial?.current ?? root.querySelector<HTMLElement>(FOCUSABLE) ?? root;
    first.focus({ preventScroll: true });
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return;
      const nodes = Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(n => n.offsetParent !== null);
      if (nodes.length === 0) { e.preventDefault(); return; }
      const a = nodes[0];
      const z = nodes[nodes.length - 1];
      if (e.shiftKey && (document.activeElement === a || !root.contains(document.activeElement))) { e.preventDefault(); z.focus(); }
      else if (!e.shiftKey && (document.activeElement === z || !root.contains(document.activeElement))) { e.preventDefault(); a.focus(); }
    };
    root.addEventListener("keydown", onKey);
    return () => {
      root.removeEventListener("keydown", onKey);
      if (opener && document.contains(opener)) opener.focus({ preventScroll: true });
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);
}

/** Roving focus for table rows: ArrowUp/Down/Home/End move between `tr[data-row]`. Only one row is a tab stop. */
export function useRowNav() {
  const [active, setActive] = useState(0);
  const onKeyDown = (e: React.KeyboardEvent<HTMLElement>) => {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) return;
    const target = e.target as HTMLElement;
    if (target.closest("button, a, input, select, textarea") && target.tagName !== "TR") return;
    const rows = Array.from(e.currentTarget.querySelectorAll<HTMLElement>("tr[data-row]"));
    const cur = rows.findIndex(r => r === document.activeElement);
    if (cur < 0) return;
    e.preventDefault();
    const next = e.key === "Home" ? 0 : e.key === "End" ? rows.length - 1 : Math.max(0, Math.min(rows.length - 1, cur + (e.key === "ArrowDown" ? 1 : -1)));
    setActive(next);
    rows[next].focus();
  };
  const rowProps = (i: number) => ({ "data-row": "", tabIndex: i === active ? 0 : -1, onFocus: () => setActive(i) });
  return { tbodyProps: { onKeyDown }, rowProps };
}

export type SortDir = "asc" | "desc";

/** Click-to-sort state: first click on a column sorts descending (biggest first) unless `ascFirst`. */
export function useSort<K extends string>(initial: K, dir: SortDir = "desc") {
  const [key, setKey] = useState<K>(initial);
  const [d, setD] = useState<SortDir>(dir);
  const toggle = (k: K, ascFirst = false) => {
    if (k === key) setD(x => (x === "asc" ? "desc" : "asc"));
    else { setKey(k); setD(ascFirst ? "asc" : "desc"); }
  };
  const ariaSort = (k: K): "ascending" | "descending" | "none" => (k === key ? (d === "asc" ? "ascending" : "descending") : "none");
  return { key, dir: d, toggle, ariaSort };
}

export function sortRows<T>(rows: T[], get: (r: T) => number | string, dir: SortDir): T[] {
  const m = dir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const x = get(a);
    const y = get(b);
    if (typeof x === "number" && typeof y === "number") return (x - y) * m;
    return String(x).localeCompare(String(y)) * m;
  });
}
