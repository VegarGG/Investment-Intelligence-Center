import { useState } from "react";

import { Card } from "../../components/ui/Card";

/**
 * Workflow 21 §8 — admin must NOT write directly. POSTs a "propose"
 * request that turns into a GitHub PR via the repo's actions.
 */
export function WatchlistAdmin() {
  const [yaml, setYaml] = useState(`# Paste a watchlist.yaml diff here.
- ticker: INTC
  venue: NASDAQ
  sector: Semiconductors
  thesis_tag: turnaround
  peers: [AMD, NVDA, QCOM, AVGO, TXN]
`);
  const [status, setStatus] = useState<string>("");

  const onPropose = async () => {
    setStatus("Submitting…");
    try {
      const resp = await fetch("/api/admin/watchlist/propose", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ yaml }),
      });
      if (!resp.ok) throw new Error(await resp.text());
      const { url } = (await resp.json()) as { url: string };
      setStatus(`PR opened: ${url}`);
    } catch (err) {
      setStatus(`Submit failed: ${err instanceof Error ? err.message : err}`);
    }
  };

  return (
    <Card title="Watchlist admin (proposal flow)">
      <p className="mb-3 text-xs text-zinc-500">
        Edits never write directly to disk — the dashboard posts a proposal that the
        repo turns into a pull request. Manual review remains a gate.
      </p>
      <textarea
        className="mb-3 h-64 w-full rounded-md border border-zinc-700 bg-zinc-900 p-3 font-mono text-sm"
        value={yaml}
        onChange={(e) => setYaml(e.target.value)}
        spellCheck={false}
      />
      <div className="flex items-center gap-3">
        <button
          onClick={() => void onPropose()}
          className="rounded-md border border-emerald-700 bg-emerald-900/40 px-3 py-2 text-sm"
        >
          Propose change
        </button>
        <span className="text-xs text-zinc-400">{status}</span>
      </div>
    </Card>
  );
}
