// /map (P5.3 + P5.4). Polls /api/geo/events every 60 s and renders the
// globe with theme + tone filters. Cache hits the JSON window cached by
// the intel agent so this never hammers GDELT directly.
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Card } from "../components/ui/Card";
import { EventGlobe } from "../components/EventGlobe";

export interface GeoEvent {
  event_id: string;
  ts: string;
  lat: number | null;
  lon: number | null;
  theme: string | null;
  tone: number | null;
  src_url: string | null;
  place: string | null;
}

interface GeoEventsResp {
  window: string;
  since: string;
  themes: string[];
  events: GeoEvent[];
}

async function fetchGeo(window: string, themes: string): Promise<GeoEventsResp> {
  const qs = new URLSearchParams({ window });
  if (themes.trim()) qs.set("themes", themes.trim());
  const r = await fetch(`/api/geo/events?${qs.toString()}`);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export function MapRoute() {
  const [window, setWindow] = useState("24h");
  const [themes, setThemes] = useState("");
  const q = useQuery({
    queryKey: ["geo", window, themes],
    queryFn: () => fetchGeo(window, themes),
    refetchInterval: 60_000,
  });

  return (
    <div className="space-y-4">
      <Card title="Global event map">
        <div className="mb-3 flex items-end gap-3 text-xs">
          <label>
            <div className="text-zinc-500">Window</div>
            <select
              value={window}
              onChange={(e) => setWindow(e.target.value)}
              className="rounded bg-zinc-900 px-2 py-1"
            >
              <option value="1h">1h</option>
              <option value="6h">6h</option>
              <option value="24h">24h</option>
              <option value="7d">7d</option>
            </select>
          </label>
          <label className="flex-1">
            <div className="text-zinc-500">Themes (comma-separated GDELT GKG prefixes)</div>
            <input
              value={themes}
              onChange={(e) => setThemes(e.target.value)}
              placeholder="ECON_,TAX_,WB_"
              className="w-full rounded bg-zinc-900 px-2 py-1 font-mono"
            />
          </label>
          <span className="text-zinc-500">
            {q.data ? `${q.data.events.length} events` : "—"}
          </span>
        </div>
        {q.isError ? (
          <p className="text-rose-400">{(q.error as Error).message}</p>
        ) : (
          <EventGlobe events={q.data?.events ?? []} />
        )}
        <p className="mt-3 text-xs text-zinc-500">
          Data: GDELT 2.0 GKG, refreshed every 15 minutes server-side, polled
          every 60 s here. Red dots = negative tone, green = positive; radius
          scales with absolute tone.
        </p>
      </Card>
    </div>
  );
}
