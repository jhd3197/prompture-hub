import { api } from "../api";
import type { HubKey, SpendPeriod } from "../types";
import { useAsync } from "./hooks";

/** UTC days covered by the current cap window: today, since Monday, or since the 1st. */
export function windowDays(period: SpendPeriod, now = new Date()): number {
  if (period === "week") return ((now.getUTCDay() + 6) % 7) + 1;
  if (period === "month") return now.getUTCDate();
  return 1;
}

/** How far through the current UTC cap window we are, 0 to 1. */
export function windowElapsed(period: SpendPeriod, now = new Date()): number {
  const dayFrac = (now.getUTCHours() * 3600 + now.getUTCMinutes() * 60 + now.getUTCSeconds()) / 86400;
  if (period === "day") return dayFrac;
  if (period === "week") return (((now.getUTCDay() + 6) % 7) + dayFrac) / 7;
  const dim = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + 1, 0)).getUTCDate();
  return (now.getUTCDate() - 1 + dayFrac) / dim;
}

/** Spend a straight-line pace would reach by the reset. Returns null while too little of the window has passed. */
export function projectedSpend(spent: number, period: SpendPeriod, now = new Date()): number | null {
  const f = windowElapsed(period, now);
  return spent > 0 && f >= 0.15 ? spent / f : null;
}

/**
 * Spend per key inside its own cap window. Derived from /api/analytics (by_key), so it counts usage rows only and
 * leaves out manual spend adjustments.
 */
export function useKeySpend(keys: HubKey[] | null) {
  const periods = Array.from(new Set((keys ?? []).filter(k => k.active).map(k => k.spend_period))).sort();
  return useAsync(async () => {
    const out = new Map<number, number>();
    await Promise.all(periods.map(async p => {
      const a = await api.analytics(windowDays(p));
      for (const row of a.by_key) {
        const k = (keys ?? []).find(x => x.id === row.key_id);
        if (k && k.spend_period === p) out.set(row.key_id, row.cost_usd);
      }
    }));
    return out;
  }, [periods.join(","), (keys ?? []).map(k => `${k.id}${k.spend_period}${k.active}`).join()]);
}
