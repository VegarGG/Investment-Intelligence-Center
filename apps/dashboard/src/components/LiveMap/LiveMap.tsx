// LiveMap — top-level container. Composes:
//   - FilterPanel for window / theme / tone cutoff
//   - MapCanvas (deck.gl + MapLibre) for the rendering
//   - EventDrawer for click-through
//   - useGeoEventsQuery for the historical fetch (poll every 60s)
//   - useGeoEventsStream for incremental WS updates (merged into the
//     poll result, deduplicated on event_id)
//
// Tone cutoff is applied client-side rather than at the API layer so
// the slider feels instant.

import { useMemo, useState } from "react";

import { Card } from "../ui/Card";
import { EventDrawer } from "./EventDrawer";
import { FilterPanel } from "./FilterPanel";
import { MapCanvas } from "./MapCanvas";
import type { GeoEvent, LiveMapFilters } from "./types";
import { useGeoEventsQuery } from "./useGeoEventsQuery";
import { useGeoEventsStream } from "./useGeoEventsStream";

interface Props {
  /** Disable the live WS stream (useful for tests). */
  disableStream?: boolean;
}

export function LiveMap({ disableStream = false }: Props) {
  const [filters, setFilters] = useState<LiveMapFilters>({
    window: "24h",
    themes: "",
    toneCutoff: 0,
  });
  const [selected, setSelected] = useState<GeoEvent | null>(null);

  const q = useGeoEventsQuery(filters);
  const stream = useGeoEventsStream({ enabled: !disableStream });

  // Merge poll + stream, dedupe on event_id, then apply tone cutoff.
  const visible = useMemo(() => {
    const seen = new Set<string>();
    const merged: GeoEvent[] = [];
    for (const e of stream.events) {
      if (!seen.has(e.event_id)) {
        seen.add(e.event_id);
        merged.push(e);
      }
    }
    for (const e of q.data?.events ?? []) {
      if (!seen.has(e.event_id)) {
        seen.add(e.event_id);
        merged.push(e);
      }
    }
    if (filters.toneCutoff <= 0) return merged;
    return merged.filter((e) => Math.abs(e.tone ?? 0) >= filters.toneCutoff);
  }, [stream.events, q.data, filters.toneCutoff]);

  return (
    <div className="space-y-4">
      <Card title="Live event map">
        <FilterPanel
          value={filters}
          onChange={setFilters}
          count={visible.length}
          streamStatus={stream.status}
        />
        {q.isError ? (
          <p className="text-rose-400" data-testid="livemap-error">
            {(q.error as Error).message}
          </p>
        ) : visible.length === 0 && !q.isLoading ? (
          <div
            className="grid h-[560px] place-items-center text-zinc-500"
            data-testid="livemap-empty"
          >
            No events in window.
          </div>
        ) : (
          <div className="relative">
            <MapCanvas events={visible} onSelect={setSelected} />
            <EventDrawer event={selected} onClose={() => setSelected(null)} />
          </div>
        )}
        <p className="mt-3 text-xs text-zinc-500">
          Data: GDELT 2.0 GKG, refreshed every 15 minutes server-side. Historical fetch
          polls every 60s; new events stream live via WebSocket. Red = negative tone,
          green = positive; marker size scales with |tone|. Basemap: MapLibre demotiles
          (replace with a self-hosted style for production).
        </p>
      </Card>
    </div>
  );
}
