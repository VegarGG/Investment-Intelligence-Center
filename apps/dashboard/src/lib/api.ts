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
