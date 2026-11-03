import { useSyncExternalStore } from "react";

export type Theme = "light" | "dark";
export type Density = "comfortable" | "compact";

const THEME_KEY = "ph-theme";
const ACCENT_KEY = "ph-accent";
const DENSITY_KEY = "ph-density";
const DEFAULT_ACCENT = 155;

/** One shared store per preference, so the top bar, the palette and Settings always agree. */
function store<T>(read: () => T, apply: (v: T) => void) {
  let value = read();
  const subs = new Set<() => void>();
  apply(value);
  return {
    get: () => value,
    set: (next: T) => { value = next; apply(next); subs.forEach(f => f()); },
    subscribe: (cb: () => void) => { subs.add(cb); return () => { subs.delete(cb); }; },
  };
}

function safeGet(key: string): string | null {
  try { return window.localStorage.getItem(key); } catch { return null; }
}
function safeSet(key: string, v: string) {
  try { window.localStorage.setItem(key, v); } catch { /* storage can be blocked */ }
}

const themeStore = store<Theme>(
  () => {
    const saved = safeGet(THEME_KEY);
    if (saved === "light" || saved === "dark") return saved;
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  },
  t => {
    document.documentElement.setAttribute("data-theme", t);
    safeSet(THEME_KEY, t);
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", t === "dark" ? "#0b0d10" : "#f4f5f7");
  },
);

const accentStore = store<number>(
  () => {
    const n = Number(safeGet(ACCENT_KEY));
    return safeGet(ACCENT_KEY) != null && Number.isFinite(n) ? n : DEFAULT_ACCENT;
  },
  h => {
    document.documentElement.style.setProperty("--accent-h", String(h));
    safeSet(ACCENT_KEY, String(h));
  },
);

const densityStore = store<Density>(
  () => (safeGet(DENSITY_KEY) === "compact" ? "compact" : "comfortable"),
  d => {
    document.documentElement.setAttribute("data-density", d);
    safeSet(DENSITY_KEY, d);
  },
);

export function useTheme(): [Theme, () => void] {
  const theme = useSyncExternalStore(themeStore.subscribe, themeStore.get);
  return [theme, () => themeStore.set(themeStore.get() === "dark" ? "light" : "dark")];
}

/**
 * OKLCH hue for the accent colour, set on the document root so every derived shade tracks it.
 * Persisted so the picker remembers across reloads.
 */
export function useAccent(): [number, (next: number) => void] {
  const hue = useSyncExternalStore(accentStore.subscribe, accentStore.get);
  return [hue, accentStore.set];
}

export function useDensity(): [Density, (next: Density) => void] {
  const d = useSyncExternalStore(densityStore.subscribe, densityStore.get);
  return [d, densityStore.set];
}

export const ACCENT_PRESETS: Array<{ name: string; hue: number }> = [
  { name: "Emerald", hue: 155 },
  { name: "Teal",    hue: 185 },
  { name: "Sky",     hue: 230 },
  { name: "Indigo",  hue: 270 },
  { name: "Magenta", hue: 320 },
  { name: "Rose",    hue: 10  },
  { name: "Amber",   hue: 70  },
];
