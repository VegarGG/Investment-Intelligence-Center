import { useQuery } from "@tanstack/react-query";

import { AdviceCard } from "../components/AdviceCard";
import { BriefCard } from "../components/BriefCard";
import { LeaderboardTable } from "../components/LeaderboardTable";
import { Card, Skeleton } from "../components/ui/Card";
import { api } from "../lib/api";

export function Home() {
  const brief = useQuery({ queryKey: ["intel", "brief"], queryFn: api.intelBriefToday });
  const advices = useQuery({ queryKey: ["advice", "today"], queryFn: () => api.advice() });
  const board = useQuery({ queryKey: ["leaderboard"], queryFn: api.leaderboard });

  const top5 = (advices.data ?? [])
    .slice()
    .sort((a, b) => b.confidence - a.confidence)
    .slice(0, 5);

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <div className="lg:col-span-1">
        {brief.isLoading ? (
          <Card title="Today's brief">
            <Skeleton className="h-24" />
          </Card>
        ) : (
          <BriefCard brief={brief.data} />
        )}
      </div>
      <div className="lg:col-span-1">
        <Card title="Today's calls">
          {advices.isLoading ? (
            <Skeleton className="h-24" />
          ) : top5.length === 0 ? (
            <p className="text-sm text-zinc-500">
              No advices today — agents are awaiting the next digest.
            </p>
          ) : (
            <ul className="space-y-3">
              {top5.map((a) => (
                <li key={a.id}>
                  <AdviceCard advice={a} />
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
      <div className="lg:col-span-1">
        <Card title="Leaderboard top 3">
          {board.isLoading ? (
            <Skeleton className="h-24" />
          ) : (
            <LeaderboardTable entries={(board.data?.entries ?? []).slice(0, 3)} />
          )}
        </Card>
      </div>
    </div>
  );
}
