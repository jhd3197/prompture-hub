export interface CurrentUser {
  id: number;
  email: string;
  name: string | null;
  avatar_url: string | null;
  provider: string;
}

export type SpendPeriod = "day" | "week" | "month";

export interface HubKey {
  id: number;
  name: string;
  allowed_models: string[];
  daily_spend_cap_usd: number;
  spend_period: SpendPeriod;
  rate_limit_per_min: number;
  created_at: string;
  revoked_at: string | null;
  active: boolean;
  allowed_ips?: string[];
  expires_at?: string | null;
  expired?: boolean;
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
  served_by?: string | null;
  attempts?: number;
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
  display_name: string | null;
  icon_url: string | null;
  brand_color: string | null;
  is_local: boolean;
}

export interface ModelsResponse {
  groups: ProviderGroup[];
  total: number;
  discovery_error: string | null;
}

export interface AgentCapabilities {
  tool_use: boolean;
  structured_output: boolean;
  questions: boolean;
  session_resume: boolean;
}

export interface AgentInfo {
  id: string;
  name: string;
  available: boolean;
  binary: string;
  source: string | null;
  custom_path: boolean;
  healthy: boolean | null;
  error: string | null;
  capabilities: AgentCapabilities;
  npm_packages: string[];
}

export interface AgentsResponse {
  agents: AgentInfo[];
  discovery_error: string | null;
}

export interface ModalitySection {
  label: string;
  groups: ProviderGroup[];
  total: number;
  discovery_error: string | null;
}

export interface ModalitiesResponse {
  image_gen: ModalitySection;
  video_gen: ModalitySection;
  tts: ModalitySection;
  stt: ModalitySection;
  embeddings: ModalitySection;
  rerank: ModalitySection;
  moderation: ModalitySection;
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
  spend_period: SpendPeriod;
  rate_limit_per_min: number;
}

export interface ConversationSummary {
  id: string;
  title: string | null;
  model: string | null;
  key_id: number;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ConversationMessage {
  id: string;
  role: string;
  content: string;
  tool_calls: unknown | null;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  created_at: string;
}

export interface ConversationDetail {
  id: string;
  title: string | null;
  model: string | null;
  key_id: number;
  meta: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  totals: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    cost_usd: number;
    message_count: number;
  };
  messages: ConversationMessage[];
}

export interface AnalyticsBucket {
  requests: number;
  errors: number;
  blocked: number;
  error_rate: number;
  cost_usd: number;
  tokens: number;
  p50_latency_ms: number | null;
  p95_latency_ms: number | null;
  fallbacks: number;
  fallback_rate: number;
}

export interface Analytics {
  range: { start: string; end: string; days: number };
  totals: AnalyticsBucket;
  by_day: Array<AnalyticsBucket & { date: string }>;
  by_model: Array<AnalyticsBucket & { model: string }>;
  by_provider: Array<AnalyticsBucket & { provider: string }>;
  by_key: Array<AnalyticsBucket & { key_id: number; name: string }>;
  recent_errors: Array<{
    timestamp: string;
    model: string;
    served_by: string | null;
    key_id: number;
    key_name: string | null;
    endpoint: string;
    error: string;
  }>;
}
