/**
 * Thin REST client for the orchestrator + secretary endpoints
 * (workflow 21 §6). All paths route through `/api/...`.
 */

import type {
  AdviceV1,
  BacktestLeaderboardV1,
  ClosedPositionRow,
  ContainerStatus,
  HostMetrics,
  IntelBriefV1,
  IntelDigestV1,
  LlmSpendSnapshot,
  OpenPositionRow,
  Tone,
} from "../types/iic";

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!resp.ok) {
    throw new ApiError(resp.status, await safeText(resp));
  }
  return (await resp.json()) as T;
}

async function safeText(resp: Response): Promise<string> {
  try {
    return await resp.text();
  } catch {
    return "";
  }
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

export const api = {
  intelBriefToday: () => request<IntelBriefV1>("/intel/brief/today"),
  intelDigestToday: () => request<IntelDigestV1>("/intel/digest/today"),
  advice: (params?: { since?: string; agent?: string }) => {
    const qs = new URLSearchParams(params ?? {}).toString();
    return request<AdviceV1[]>(`/advice${qs ? `?${qs}` : ""}`);
  },
  leaderboard: () => request<BacktestLeaderboardV1>("/leaderboard"),
  positionsOpen: () => request<OpenPositionRow[]>("/positions/open"),
  positionsClosed: () => request<ClosedPositionRow[]>("/positions/closed"),
  hostMetrics: () => request<HostMetrics>("/health/host"),
  containers: () => request<ContainerStatus[]>("/health/containers"),
  llmSpend: () => request<LlmSpendSnapshot>("/health/llm"),
  setTone: (tone: Tone) =>
    request<{ ok: true }>("/secretary/tone", {
      method: "PUT",
      body: JSON.stringify({ tone }),
    }),
  dashboardToken: () => request<{ token: string; exp: number }>("/dashboard/token"),
};

// ---- admin API (P3) --------------------------------------------------------
// Routed through /api/admin/... by the reverse proxy in prod; goes straight
// to http://iic-admin-api:8090/admin/... in dev.
const ADMIN_BASE = "/api/admin";

async function adminRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${ADMIN_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!resp.ok) throw new ApiError(resp.status, await safeText(resp));
  return (await resp.json()) as T;
}

export interface AdminFileSnapshot {
  path: string;
  content: string;
  sha256: string;
}
export interface AdminApplyResult {
  path: string;
  after_sha256: string;
  audit_id: string;
  chain_hash: string;
}
export interface AdminSecret {
  name: string;
  present: boolean;
  path: string | null;
}
export interface AdminConnectorStatus {
  name: string;
  state: "ok" | "error" | "unconfigured";
  detail: string | null;
}
export interface AdminScheduleEntry {
  job_id: string;
  enabled: boolean;
  cron: string | null;
  timezone: string | null;
}

export const admin = {
  health: () => adminRequest<{ status: string; editable_paths: string[] }>("/health"),
  readFile: (rel: string) => adminRequest<AdminFileSnapshot>(`/files/${rel}`),
  proposeFile: (rel: string, content: string) =>
    adminRequest<{ before_sha256: string; after_sha256: string }>(
      `/files/${rel}/propose`,
      { method: "POST", body: JSON.stringify({ content }) },
    ),
  applyFile: (rel: string, content: string, reason?: string) =>
    adminRequest<AdminApplyResult>(`/files/${rel}/apply`, {
      method: "POST",
      body: JSON.stringify({ content, reason }),
    }),
  listSecrets: () => adminRequest<{ secrets: AdminSecret[] }>("/secrets"),
  rotateSecret: (name: string, value: string) =>
    adminRequest<{ name: string; audit_id: string }>(`/secrets/${name}/rotate`, {
      method: "POST",
      body: JSON.stringify({ value }),
    }),
  listConnectors: () => adminRequest<{ connectors: string[] }>("/connectors"),
  testConnector: (name: string) =>
    adminRequest<AdminConnectorStatus>(`/connectors/${name}/test`, { method: "POST" }),
  getSchedules: () => adminRequest<{ schedules: AdminScheduleEntry[] }>("/schedules"),
  applySchedules: (schedules: AdminScheduleEntry[]) =>
    adminRequest<AdminApplyResult>("/schedules/apply", {
      method: "POST",
      body: JSON.stringify({ schedules }),
    }),
  listCrons: () =>
    adminRequest<{ crons: Array<{ name: string; trigger: Record<string, unknown> }> }>(
      "/crons",
    ),
  auditHead: () => adminRequest<{ head: string | null }>("/audit/head"),
};
