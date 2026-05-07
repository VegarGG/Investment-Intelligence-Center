import type { LeaderboardEntry } from "../types/iic";
import { formatPct } from "../lib/format";
import { Badge } from "./ui/Card";

export function LeaderboardTable({ entries }: { entries: LeaderboardEntry[] }) {
  if (entries.length === 0) {
    return (
      <p className="text-sm text-zinc-500">
        No agents ranked yet — the backtester needs ≥20 closed trades and ≥60 days live.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead className="text-left text-xs uppercase tracking-wider text-zinc-500">
          <tr>
            <th className="px-3 py-2">Agent</th>
            <th className="px-3 py-2">Score</th>
            <th className="px-3 py-2">Sharpe</th>
            <th className="px-3 py-2">Hit Rate</th>
            <th className="px-3 py-2">R Avg</th>
            <th className="px-3 py-2">Max DD</th>
            <th className="px-3 py-2">Trades</th>
            <th className="px-3 py-2">Status</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => (
            <tr key={entry.agent} className="border-t border-zinc-800">
              <td className="px-3 py-2 font-mono text-zinc-200">{entry.agent}</td>
              <td className="px-3 py-2">{entry.score.toFixed(3)}</td>
              <td className="px-3 py-2">{entry.sharpe.toFixed(2)}</td>
              <td className="px-3 py-2">{formatPct(entry.hit_rate)}</td>
              <td className="px-3 py-2">{entry.r_avg.toFixed(2)}R</td>
              <td className="px-3 py-2">{entry.max_dd_pct.toFixed(1)}%</td>
              <td className="px-3 py-2">{entry.trades_closed}</td>
              <td className="px-3 py-2">
                {entry.provisional ? (
                  <Badge tone="warn">provisional</Badge>
                ) : (
                  <Badge tone="good">ranked</Badge>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
