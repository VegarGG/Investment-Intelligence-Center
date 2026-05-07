import { Card } from "../components/ui/Card";

export function Fundamental() {
  return (
    <Card title="Fundamental">
      <p className="text-sm text-zinc-500">
        Watchlist + recent valuations + citation viewer arrive when the
        fundamental agent's `/watchlist` and `/cover` endpoints publish (workflow 11 §6).
      </p>
    </Card>
  );
}
