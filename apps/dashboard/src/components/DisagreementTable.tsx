import { bandLabel, formatPct } from "../lib/format";
import type { AdviceV1 } from "../types/iic";

export interface DisagreementProps {
  ticker: string;
  advices: AdviceV1[];
  windowDays?: number;
}

export function DisagreementTable({
  ticker,
  advices,
  windowDays = 7,
}: DisagreementProps) {
  const cutoff = Date.now() - windowDays * 86400 * 1000;
  const relevant = advices.filter(
    (a) =>
      a.asset.ticker.toUpperCase() === ticker.toUpperCase() &&
      Date.parse(a.issued_at) >= cutoff,
  );
  const directions = new Set(relevant.map((a) => a.direction));
  if (directions.size < 2) {
    return (
      <p className="text-sm text-zinc-500">
        No disagreement on {ticker} in the last {windowDays} days.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead className="text-left text-xs uppercase tracking-wider text-zinc-500">
          <tr>
            <th className="px-3 py-2">Agent</th>
            <th className="px-3 py-2">Direction</th>
            <th className="px-3 py-2">Entry</th>
            <th className="px-3 py-2">Target</th>
            <th className="px-3 py-2">Confidence</th>
            <th className="px-3 py-2">Thesis</th>
          </tr>
        </thead>
        <tbody>
          {relevant.map((a) => (
            <tr key={a.id} className="border-t border-zinc-800">
              <td className="px-3 py-2 font-mono">{a.agent}</td>
              <td className="px-3 py-2 uppercase">{a.direction}</td>
              <td className="px-3 py-2">{bandLabel(a.entry_band)}</td>
              <td className="px-3 py-2">{bandLabel(a.target_band)}</td>
              <td className="px-3 py-2">{formatPct(a.confidence)}</td>
              <td className="px-3 py-2 text-zinc-300">
                {a.thesis.slice(0, 80)}
                {a.thesis.length > 80 ? "…" : ""}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
