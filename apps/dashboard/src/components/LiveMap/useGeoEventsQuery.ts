// Historical fetch hook for /api/geo/events.
// Mirrors the existing routes/Map.tsx polling pattern (60s refetch).

import { useQuery } from "@tanstack/react-query";

import type { GeoEventsResp, LiveMapFilters } from "./types";

async function fetchGeo(filters: LiveMapFilters): Promise<GeoEventsResp> {
  const qs = new URLSearchParams({ window: filters.window });
  if (filters.themes.trim()) qs.set("themes", filters.themes.trim());
  const r = await fetch(`/api/geo/events?${qs.toString()}`);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export function useGeoEventsQuery(filters: LiveMapFilters) {
  return useQuery({
    queryKey: ["geo-events", filters.window, filters.themes],
    queryFn: () => fetchGeo(filters),
    refetchInterval: 60_000,
  });
}
