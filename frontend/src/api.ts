import type {
  AuthProviders, CreatedKey, CurrentUser, HubKey, ModelsResponse, Overview,
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
    rate_limit_per_min: number;
  }) => request<CreatedKey>("/api/keys", {
    method: "POST",
    body: JSON.stringify(data),
  }),
  revokeKey: (id: number) =>
    request<void>(`/api/keys/${id}/revoke`, { method: "POST" }),
  models: () => request<ModelsResponse>("/api/models"),
  logoutHref: "/auth/logout",
  loginHref: (provider: "google" | "github") => `/auth/${provider}/start`,
};
