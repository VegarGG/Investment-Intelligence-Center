import { bandLabel, formatPct, formatTimestamp } from "../lib/format";
import type { AdviceV1 } from "../types/iic";
import { Badge } from "./ui/Card";

export function AdviceCard({ advice }: { advice: AdviceV1 }) {
  const direction = advice.direction;
  const tone =
    direction === "long" ? "good" : direction === "short" ? "bad" : "default";
  return (
    <article className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-4">
      <header className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Badge tone={tone}>{direction.toUpperCase()}</Badge>
          <span className="font-mono text-base">{advice.asset.ticker}</span>
          <span className="text-xs text-zinc-500">{advice.asset.venue}</span>
        </div>
        <Badge>{advice.agent}</Badge>
      </header>
      <p className="mb-3 line-clamp-3 text-sm text-zinc-300">{advice.thesis}</p>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-zinc-400">
        <dt>entry</dt>
        <dd className="text-zinc-200">{bandLabel(advice.entry_band)}</dd>
        <dt>target</dt>
        <dd className="text-zinc-200">{bandLabel(advice.target_band)}</dd>
        <dt>stop</dt>
        <dd className="text-zinc-200">{advice.stop_loss.toFixed(2)}</dd>
        <dt>confidence</dt>
        <dd className="text-zinc-200">{formatPct(advice.confidence)}</dd>
        <dt>horizon</dt>
        <dd className="text-zinc-200">{advice.horizon_days}d</dd>
        <dt>issued</dt>
        <dd className="text-zinc-200">{formatTimestamp(advice.issued_at)}</dd>
      </dl>
    </article>
  );
}
