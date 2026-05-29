import type {
  AgentsResponse, AuthProviders, ConversationDetail, ConversationSummary,
  CreatedKey, CurrentUser, HubKey, ModalitiesResponse, ModelsResponse, Overview,
} from "./types";

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await fetch(path, {
    credentials: "same-origin",
    headers: {
      "Accept": "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...(init.headers || {}),
    },
    ...init,
  });
  if (!res.ok) {
    let body: unknown = null;
    try { body = await res.json(); } catch { /* ignore */ }
    throw new ApiError(res.status, `${res.status} ${res.statusText}`, body);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  me: () => request<CurrentUser>("/api/me"),
  providers: () => request<AuthProviders>("/api/auth/providers"),
  overview: () => request<Overview>("/api/overview"),
  listKeys: () => request<HubKey[]>("/api/keys"),
  createKey: (data: {
    name: string;
    allowed_models: string[];
    daily_spend_cap_usd: number;
    spend_period: "day" | "week" | "month";
    rate_limit_per_min: number;
  }) => request<CreatedKey>("/api/keys", {
    method: "POST",
    body: JSON.stringify(data),
  }),
  revokeKey: (id: number) =>
    request<void>(`/api/keys/${id}/revoke`, { method: "POST" }),
  models: () => request<ModelsResponse>("/api/models"),
  agents: () => request<AgentsResponse>("/api/agents"),
  modalities: () => request<ModalitiesResponse>("/api/modalities"),
  workspaceDirs: () => request<{
    workspace: string;
    dirs: string[];
    truncated: boolean;
    max_depth: number;
  }>("/api/workspace/dirs"),
  runAgent: (body: {
    agent: string;
    task: string;
    approval_mode?: string;
    model?: string | null;
    extra_args?: string[];
    output_format?: string;
    session_id?: string | null;
    cwd?: string | null;
  }) => request<{
    agent: string;
    command: string[];
    cwd: string;
    returncode: number;
    duration_seconds: number;
    output: string;
    events: Array<Record<string, unknown>>;
    usage: {
      prompt_tokens: number;
      completion_tokens: number;
      total_tokens: number;
      cost_usd: number;
    };
  }>("/api/agents/run", {
    method: "POST",
    body: JSON.stringify(body),
  }),
  listConversations: () =>
    request<ConversationSummary[]>("/api/conversations"),
  getConversation: (id: string) =>
    request<ConversationDetail>(`/api/conversations/${id}`),
  deleteConversation: (id: string) =>
    request<void>(`/api/conversations/${id}`, { method: "DELETE" }),
  logoutHref: "/auth/logout",
  loginHref: (provider: "google" | "github") => `/auth/${provider}/start`,
};
