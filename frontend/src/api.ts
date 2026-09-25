import type {
  AgentsResponse, AlertEvent, AlertKind, AlertRule, Analytics, AuthProviders, ConversationDetail,
  ConversationSummary, CreatedKey, CurrentUser, CustomEndpoint, Device, EndpointUsage, HubKey,
  ModalitiesResponse, ModelsResponse, Overview, PairingInfo,
} from "./types";

export type AlertRuleInput = {
  name: string;
  kind: AlertKind;
  threshold?: number | null;
  key_id?: number | null;
  target?: string | null;
  webhook_url?: string | null;
  ntfy_url?: string | null;
  cooldown_minutes?: number;
  enabled?: boolean;
};

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
    expires_in_days?: number | null;
    allowed_ips?: string[];
  }) => request<CreatedKey>("/api/keys", {
    method: "POST",
    body: JSON.stringify(data),
  }),
  revokeKey: (id: number) =>
    request<void>(`/api/keys/${id}/revoke`, { method: "POST" }),
  models: () => request<ModelsResponse>("/api/models"),
  analytics: (days: number, project?: string | null) =>
    request<Analytics>(
      `/api/analytics?days=${days}${project ? `&project=${encodeURIComponent(project)}` : ""}`,
    ),

  // Key controls (shared with paired companions; the dashboard session is accepted too).
  pauseKey: (id: number) => request<HubKey>(`/v1/keys/${id}/pause`, { method: "POST" }),
  resumeKey: (id: number) => request<HubKey>(`/v1/keys/${id}/resume`, { method: "POST" }),
  updateKey: (id: number, data: {
    daily_spend_cap_usd?: number;
    spend_period?: "day" | "week" | "month";
    route_override?: string;
    default_project?: string;
  }) => request<HubKey>(`/v1/keys/${id}`, { method: "PATCH", body: JSON.stringify(data) }),

  // Companion devices
  pairing: (code: string) => request<PairingInfo>(`/api/companion/pairings/${encodeURIComponent(code)}`),
  approvePairing: (code: string, data: { name?: string; scopes: string[] }) =>
    request<{ status: string; name: string; scopes: string[] }>(
      `/api/companion/pairings/${encodeURIComponent(code)}/approve`,
      { method: "POST", body: JSON.stringify(data) },
    ),
  denyPairing: (code: string) =>
    request<void>(`/api/companion/pairings/${encodeURIComponent(code)}/deny`, { method: "POST" }),
  devices: () => request<Device[]>("/api/companion/devices"),
  revokeDevice: (id: number) => request<void>(`/api/companion/devices/${id}/revoke`, { method: "POST" }),

  // Alerts
  alertRules: () => request<AlertRule[]>("/api/alerts/rules"),
  createAlertRule: (data: AlertRuleInput) =>
    request<AlertRule>("/api/alerts/rules", { method: "POST", body: JSON.stringify(data) }),
  updateAlertRule: (id: number, data: Partial<AlertRuleInput>) =>
    request<AlertRule>(`/api/alerts/rules/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteAlertRule: (id: number) => request<void>(`/api/alerts/rules/${id}`, { method: "DELETE" }),
  alerts: (unacknowledged = false) => request<AlertEvent[]>(`/api/alerts?unacknowledged=${unacknowledged}`),
  ackAlert: (id: number) => request<AlertEvent>(`/api/alerts/${id}/ack`, { method: "POST" }),

  // Custom endpoints
  endpoints: () => request<CustomEndpoint[]>("/api/endpoints"),
  createEndpoint: (data: { name: string; base_url: string; api_key_env?: string | null }) =>
    request<CustomEndpoint>("/api/endpoints", { method: "POST", body: JSON.stringify(data) }),
  deleteEndpoint: (id: number) => request<void>(`/api/endpoints/${id}`, { method: "DELETE" }),
  checkEndpoint: (id: number) => request<CustomEndpoint>(`/api/endpoints/${id}/check`, { method: "POST" }),
  endpointUsage: (id: number, days = 7) => request<EndpointUsage>(`/api/endpoints/${id}/usage?days=${days}`),
  agents: () => request<AgentsResponse>("/api/agents"),
  modalities: () => request<ModalitiesResponse>("/api/modalities"),
  workspaceDirs: () => request<{
    workspace: string;
    dirs: string[];
    truncated: boolean;
    max_depth: number;
  }>("/api/workspace/dirs"),
  systemInfo: () => request<{
    platform: string;
    platform_release: string;
    is_wsl: boolean;
    python_version: string;
    hub_host: string;
    hub_port: number;
    hub_base_url: string;
    bind_is_local: boolean;
    interfaces: Array<{ name: string; address: string }>;
    tunneling: {
      cloudflared_installed: boolean;
      ngrok_installed: boolean;
      tailscale_installed: boolean;
    };
    lan_share_supported: boolean;
  }>("/api/system/info"),
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
