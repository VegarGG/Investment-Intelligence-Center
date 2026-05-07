import { useQuery } from "@tanstack/react-query";

import { Card, Skeleton } from "../components/ui/Card";
import { api } from "../lib/api";
import { bandLabel, formatPnlR, formatTime, formatUsd } from "../lib/format";

export function TradeTape() {
  const open = useQuery({ queryKey: ["positions", "open"], queryFn: api.positionsOpen });
  const closed = useQuery({
    queryKey: ["positions", "closed"],
    queryFn: api.positionsClosed,
  });

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <Card title="Open positions">
        {open.isLoading ? (
          <Skeleton className="h-32" />
        ) : (open.data ?? []).length === 0 ? (
          <p className="text-sm text-zinc-500">No open positions.</p>
        ) : (
          <table className="min-w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wider text-zinc-500">
              <tr>
                <th className="px-2 py-2">Ticker</th>
                <th className="px-2 py-2">Agent</th>
                <th className="px-2 py-2">Dir</th>
                <th className="px-2 py-2">Entry</th>
                <th className="px-2 py-2">Mark</th>
                <th className="px-2 py-2">Target</th>
                <th className="px-2 py-2">Stop</th>
                <th className="px-2 py-2">P&amp;L</th>
              </tr>
            </thead>
            <tbody>
              {(open.data ?? []).map((p) => (
                <tr key={p.advice_id} className="border-t border-zinc-800">
                  <td className="px-2 py-2 font-mono">{p.ticker}</td>
                  <td className="px-2 py-2">{p.agent}</td>
                  <td className="px-2 py-2 uppercase">{p.direction}</td>
                  <td className="px-2 py-2">{p.entry_px.toFixed(2)}</td>
                  <td className="px-2 py-2">{p.mark_px?.toFixed(2) ?? "—"}</td>
                  <td className="px-2 py-2">{bandLabel(p.target_band)}</td>
                  <td className="px-2 py-2">{p.stop_loss.toFixed(2)}</td>
                  <td className="px-2 py-2">{formatUsd(p.unrealized_pnl_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      <Card title="Recent fills">
        {closed.isLoading ? (
          <Skeleton className="h-32" />
        ) : (closed.data ?? []).length === 0 ? (
          <p className="text-sm text-zinc-500">No recent fills.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {(closed.data ?? []).slice(0, 25).map((p) => (
              <li
                key={p.advice_id}
                className="flex items-center justify-between border-b border-zinc-800 py-1"
              >
                <span className="font-mono">{p.ticker}</span>
                <span className="text-xs text-zinc-500">{p.agent}</span>
                <span>{formatPnlR(p.pnl_r)}</span>
                <span className="text-xs uppercase text-zinc-400">{p.exit_reason}</span>
                <span className="text-xs text-zinc-500">{formatTime(p.closed_at)}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
