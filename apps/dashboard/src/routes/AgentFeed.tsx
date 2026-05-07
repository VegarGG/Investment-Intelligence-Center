import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import { AdviceCard } from "../components/AdviceCard";
import { Card, Skeleton } from "../components/ui/Card";
import { api } from "../lib/api";

export function AgentFeed() {
  const { agent = "" } = useParams<{ agent: string }>();
  const advices = useQuery({
    queryKey: ["advice", agent],
    queryFn: () => api.advice({ agent }),
  });

  return (
    <Card title={`${agent} feed`}>
      {advices.isLoading ? (
        <Skeleton className="h-32" />
      ) : (advices.data ?? []).length === 0 ? (
        <p className="text-sm text-zinc-500">No advices from {agent} yet.</p>
      ) : (
        <ul className="space-y-3">
          {(advices.data ?? []).map((a) => (
            <li key={a.id}>
              <AdviceCard advice={a} />
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
