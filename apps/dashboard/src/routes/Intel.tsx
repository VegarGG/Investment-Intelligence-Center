import { useQuery } from "@tanstack/react-query";

import { BiasBalanceChart } from "../components/BiasBalanceChart";
import { Card, Skeleton } from "../components/ui/Card";
import { api } from "../lib/api";

export function Intel() {
  const digest = useQuery({ queryKey: ["intel", "digest"], queryFn: api.intelDigestToday });

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <Card title="Macro thesis">
        {digest.isLoading ? (
          <Skeleton className="h-24" />
        ) : (
          <p className="text-sm text-zinc-300">
            {digest.data?.macro_thesis ?? "No macro thesis yet."}
          </p>
        )}
      </Card>
      <Card title="Bias balance">
        {digest.isLoading ? (
          <Skeleton className="h-32" />
        ) : (
          <BiasBalanceChart balance={digest.data?.bias_balance} />
        )}
      </Card>
      <Card title="Top events" className="lg:col-span-2">
        {digest.isLoading ? (
          <Skeleton className="h-32" />
        ) : (digest.data?.events ?? []).length === 0 ? (
          <p className="text-sm text-zinc-500">No events yet.</p>
        ) : (
          <ol className="space-y-2 text-sm">
            {(digest.data?.events ?? []).slice(0, 15).map((e) => (
              <li key={e.id} className="flex items-baseline gap-3">
                <span className="text-xs text-zinc-500">#{e.rank}</span>
                <span className="font-medium text-zinc-200">{e.headline}</span>
                <span className="text-xs text-zinc-500">{e.why_it_matters}</span>
              </li>
            ))}
          </ol>
        )}
      </Card>
    </div>
  );
}
