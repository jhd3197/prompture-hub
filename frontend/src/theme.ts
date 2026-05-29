import { useEffect, useState } from "react";

export type Theme = "light" | "dark";

const THEME_KEY = "ph-theme";
const ACCENT_KEY = "ph-accent";
const DEFAULT_ACCENT = 155; // green — matches design system default

function getInitialTheme(): Theme {
  if (typeof window === "undefined") return "light";
  const saved = window.localStorage.getItem(THEME_KEY);
  if (saved === "light" || saved === "dark") return saved;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

function getInitialAccent(): number {
  if (typeof window === "undefined") return DEFAULT_ACCENT;
  const saved = window.localStorage.getItem(ACCENT_KEY);
  const n = saved == null ? NaN : Number(saved);
  return Number.isFinite(n) ? n : DEFAULT_ACCENT;
}

export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(getInitialTheme);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    window.localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  const toggle = () => setTheme(t => (t === "dark" ? "light" : "dark"));
  return [theme, toggle];
}

/**
 * OKLCH hue for the accent colour. Set on document root so every
 * ``var(--accent)`` derived shade tracks the choice. Persisted to
 * ``localStorage`` so the picker remembers across reloads.
 *
 * Defaults to 155 (green) — the design's stock accent.
 */
export function useAccent(): [number, (next: number) => void] {
  const [hue, setHue] = useState<number>(getInitialAccent);

  useEffect(() => {
    document.documentElement.style.setProperty("--accent-h", String(hue));
    window.localStorage.setItem(ACCENT_KEY, String(hue));
  }, [hue]);

  return [hue, setHue];
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
