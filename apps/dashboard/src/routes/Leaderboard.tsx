import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { LeaderboardTable } from "../components/LeaderboardTable";
import { Card, Skeleton } from "../components/ui/Card";
import { api } from "../lib/api";

type AgentClass = "all" | "fundamental" | "quant" | "persona";

const FILTERS: { value: AgentClass; label: string }[] = [
  { value: "all", label: "All" },
  { value: "fundamental", label: "Fundamental" },
  { value: "quant", label: "Quant" },
  { value: "persona", label: "Persona" },
];

export function Leaderboard() {
  const board = useQuery({ queryKey: ["leaderboard"], queryFn: api.leaderboard });
  const [filter, setFilter] = useState<AgentClass>("all");

  const filtered = useMemo(() => {
    const entries = board.data?.entries ?? [];
    if (filter === "all") return entries;
    return entries.filter((e) => {
      if (filter === "persona") return e.agent.startsWith("persona.");
      return e.agent === filter;
    });
  }, [board.data, filter]);

  return (
    <Card title="Leaderboard">
      <div className="mb-3 flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            onClick={() => setFilter(f.value)}
            className={`rounded-full border px-3 py-1 text-xs ${
              filter === f.value
                ? "border-emerald-700 bg-emerald-900/40 text-emerald-200"
                : "border-zinc-700 text-zinc-400"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>
      {board.isLoading ? <Skeleton className="h-32" /> : <LeaderboardTable entries={filtered} />}
    </Card>
  );
}
