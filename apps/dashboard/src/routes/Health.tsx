import { useQuery } from "@tanstack/react-query";

import { Badge, Card, Skeleton } from "../components/ui/Card";
import { api } from "../lib/api";
import { formatPct } from "../lib/format";

export function Health() {
  const host = useQuery({ queryKey: ["health", "host"], queryFn: api.hostMetrics });
  const containers = useQuery({ queryKey: ["health", "containers"], queryFn: api.containers });
  const llm = useQuery({ queryKey: ["health", "llm"], queryFn: api.llmSpend });

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <Card title="Host">
        {host.isLoading ? (
          <Skeleton className="h-32" />
        ) : (
          <dl className="grid grid-cols-2 gap-y-1 text-sm">
            <dt className="text-zinc-400">CPU temp</dt>
            <dd>{host.data?.cpu_temp_c?.toFixed(1) ?? "—"}°C</dd>
            <dt className="text-zinc-400">CPU %</dt>
            <dd>{host.data?.cpu_pct?.toFixed(0) ?? "—"}%</dd>
            <dt className="text-zinc-400">RAM %</dt>
            <dd>{host.data?.ram_pct?.toFixed(0) ?? "—"}%</dd>
            <dt className="text-zinc-400">NVMe temp</dt>
            <dd>{host.data?.nvme_temp_c?.toFixed(1) ?? "—"}°C</dd>
            <dt className="text-zinc-400">NVMe wear</dt>
            <dd>{host.data?.nvme_wear_pct?.toFixed(1) ?? "—"}%</dd>
            <dt className="text-zinc-400">Disk free</dt>
            <dd>{host.data?.disk_free_gb?.toFixed(0) ?? "—"} GB</dd>
            <dt className="text-zinc-400">UPS battery</dt>
            <dd>{host.data?.ups_battery_pct?.toFixed(0) ?? "—"}%</dd>
          </dl>
        )}
      </Card>
      <Card title="Containers">
        {containers.isLoading ? (
          <Skeleton className="h-32" />
        ) : (
          <ul className="space-y-1 text-sm">
            {(containers.data ?? []).map((c) => (
              <li key={c.name} className="flex items-center justify-between">
                <span>{c.name}</span>
                <Badge tone={c.state === "running" ? "good" : c.state === "exited" ? "bad" : "warn"}>
                  {c.state}
                </Badge>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title="LLM spend">
        {llm.isLoading ? (
          <Skeleton className="h-32" />
        ) : (
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-zinc-400">Month-to-date</span>
              <span>${llm.data?.month_to_date_usd.toFixed(2)} / ${llm.data?.monthly_cap_usd.toFixed(0)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-400">Breaker</span>
              <Badge
                tone={llm.data?.breaker_state === "open" ? "bad" : llm.data?.breaker_state === "half_open" ? "warn" : "good"}
              >
                {llm.data?.breaker_state ?? "—"}
              </Badge>
            </div>
            <div>
              <div className="mb-1 text-xs text-zinc-500">Spend by caller (24h)</div>
              <ul className="space-y-1 text-xs">
                {Object.entries(llm.data?.by_caller_24h_usd ?? {}).map(([k, v]) => (
                  <li key={k} className="flex justify-between">
                    <span className="font-mono">{k}</span>
                    <span>${v.toFixed(2)}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="flex justify-between border-t border-zinc-800 pt-2">
              <span className="text-zinc-400">Burn pct of cap</span>
              <span>
                {formatPct(
                  llm.data && llm.data.monthly_cap_usd > 0
                    ? llm.data.month_to_date_usd / llm.data.monthly_cap_usd
                    : null,
                )}
              </span>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
