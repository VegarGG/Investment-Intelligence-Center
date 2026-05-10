import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Card } from "../components/ui/Card";
import type { TradingRoomBriefV1 } from "../types/board";

// v2.5 N3.4 / T2.6 — Trading-room page. Renders the latest BoardDecisionV1
// brief inline plus a "Dissent" expander. Polls `/api/trading_room/latest`
// every 30 s; the NATS-WS bridge will push real-time updates in N3.5.

async function fetchLatest(): Promise<TradingRoomBriefV1 | null> {
  const res = await fetch("/api/trading_room/latest");
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`fetch failed: ${res.status}`);
  return (await res.json()) as TradingRoomBriefV1;
}

function ConfidenceBar({ confidence }: { confidence: number }) {
  const pct = Math.round(Math.max(0, Math.min(1, confidence)) * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 flex-1 rounded-full bg-zinc-800">
        <div
          className="h-2 rounded-full bg-emerald-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-zinc-400">{pct}%</span>
    </div>
  );
}

export function TradingRoom() {
  const [showDissent, setShowDissent] = useState(false);
  const { data, isLoading, error } = useQuery({
    queryKey: ["trading_room_latest"],
    queryFn: fetchLatest,
    refetchInterval: 30_000,
  });

  if (isLoading) {
    return (
      <Card title="Trading Room">
        <p className="text-sm text-zinc-500">Loading latest brief…</p>
      </Card>
    );
  }

  if (error) {
    return (
      <Card title="Trading Room">
        <p className="text-sm text-red-400">
          Failed to load brief: {(error as Error).message}
        </p>
      </Card>
    );
  }

  if (!data) {
    return (
      <Card title="Trading Room">
        <p className="text-sm text-zinc-500">
          No trading-room briefs yet. The room wakes only on high-impact events
          that pass the Event-Triage Gate.
        </p>
      </Card>
    );
  }

  const { decision } = data;

  return (
    <div className="flex flex-col gap-4">
      <Card title={`Trading Room — ${data.ticker}`}>
        <div className="mb-3 flex items-center justify-between text-xs text-zinc-500">
          <span>{new Date(data.issued_at).toLocaleString()}</span>
          <span>
            Plans considered: {decision.considered_plan_ids.length} · Chosen:{" "}
            <code className="rounded bg-zinc-800 px-1">{decision.chosen_plan_id}</code>
          </span>
        </div>
        <ConfidenceBar confidence={decision.confidence} />
        <pre className="mt-4 whitespace-pre-wrap font-mono text-sm text-zinc-200">
          {data.markdown}
        </pre>
      </Card>

      <Card title="Dissent">
        <button
          type="button"
          onClick={() => setShowDissent((v) => !v)}
          className="rounded border border-zinc-700 px-3 py-1 text-xs text-zinc-300 hover:bg-zinc-800"
          data-testid="dissent-toggle"
        >
          {showDissent ? "Hide" : "Show"} dissent record
        </button>
        {showDissent && (
          <pre
            data-testid="dissent-body"
            className="mt-3 whitespace-pre-wrap font-mono text-sm text-zinc-300"
          >
            {decision.dissent_record || "(no dissent)"}
          </pre>
        )}
      </Card>
    </div>
  );
}
