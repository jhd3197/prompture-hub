export interface CurrentUser {
  id: number;
  email: string;
  name: string | null;
  avatar_url: string | null;
  provider: string;
}

export interface HubKey {
  id: number;
  name: string;
  allowed_models: string[];
  daily_spend_cap_usd: number;
  rate_limit_per_min: number;
  created_at: string;
  revoked_at: string | null;
  active: boolean;
  prefix?: string;
}

export interface UsageRow {
  id: number;
  key_id: number;
  model: string;
  endpoint: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  latency_ms: number;
  status: string;
  timestamp: string;
}

export interface Overview {
  spend_24h: number;
  active_key_count: number;
  total_call_count: number;
  recent_usage: UsageRow[];
  recent_keys: HubKey[];
}

export interface ProviderGroup {
  provider: string;
  models: string[];
}

export interface ModelsResponse {
  groups: ProviderGroup[];
  total: number;
  discovery_error: string | null;
}

export interface AuthProviders {
  google: boolean;
  github: boolean;
  auth_configured: boolean;
}

export interface CreatedKey {
  id: number;
  name: string;
  key: string;
  allowed_models: string[];
  daily_spend_cap_usd: number;
  rate_limit_per_min: number;
}
