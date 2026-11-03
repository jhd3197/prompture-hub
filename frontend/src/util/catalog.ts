import { useSyncExternalStore } from "react";
import { api } from "../api";
import type { ConversationSummary, HubKey } from "../types";

/**
 * A tiny shared cache of lists the app has already loaded, so the command palette can jump to a
 * key or a session without its own round trip. Pages publish what they fetch; the palette fills
 * any gap the first time it opens.
 */
interface Catalog { keys: HubKey[] | null; sessions: ConversationSummary[] | null }

let state: Catalog = { keys: null, sessions: null };
const subs = new Set<() => void>();
const emit = () => subs.forEach(f => f());

export function publishKeys(keys: HubKey[]): void { state = { ...state, keys }; emit(); }
export function publishSessions(sessions: ConversationSummary[]): void { state = { ...state, sessions }; emit(); }

export async function ensureCatalog(): Promise<void> {
  const jobs: Promise<void>[] = [];
  if (!state.keys) jobs.push(api.listKeys().then(publishKeys).catch(() => {}));
  if (!state.sessions) jobs.push(api.listConversations().then(publishSessions).catch(() => {}));
  await Promise.all(jobs);
}

export function useCatalog(): Catalog {
  return useSyncExternalStore(
    cb => { subs.add(cb); return () => { subs.delete(cb); }; },
    () => state,
  );
}
