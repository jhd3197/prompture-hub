export const usd = (v: number | null | undefined, digits?: number): string => {
  if (v == null) return "n/a";
  const d = digits ?? (Math.abs(v) < 1 ? 4 : 2);
  return `$${v.toFixed(d)}`;
};

/** Signed currency delta: +$0.12 / -$0.03 */
export const signedUsd = (v: number | null): string =>
  v == null ? "n/a" : `${v > 0 ? "+" : v < 0 ? "-" : ""}${usd(Math.abs(v))}`;

export const pct = (v: number): string => `${(v * 100).toFixed(v > 0 && v < 0.01 ? 2 : 1)}%`;

export const ms = (v: number | null | undefined): string =>
  v == null ? "n/a" : v >= 1000 ? `${(v / 1000).toFixed(1)}s` : `${Math.round(v)}ms`;

export const int = (v: number): string => v.toLocaleString();

export const compact = (v: number): string =>
  Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(v);

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "never";
  const sec = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
  if (sec < 604800) return `${Math.floor(sec / 86400)}d ago`;
  return new Date(iso).toLocaleDateString();
}

/** "2026-11-03" (a UTC calendar day from the API) to "Nov 3". */
export function shortDate(day: string): string {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export const dateTime = (iso: string): string => new Date(iso).toLocaleString();
export const dateOnly = (iso: string): string => new Date(iso).toLocaleDateString();

/** Short route-friendly error text from whatever a failed request threw. */
export function errText(e: unknown): string {
  if (e instanceof Error) return e.message;
  return String(e);
}

export const plural = (n: number, one: string, many = `${one}s`): string => `${n} ${n === 1 ? one : many}`;
