// GeoEvent shape — matches the real lake.geo_events schema (migration 0010)
// as returned by GET /api/geo/events. D9 §5.5's schema guess was incorrect
// (it assumed severity/category/actor1/actor2/summary fields that don't
// exist). Real shape is GDELT-shaped: theme + tone + place.

export interface GeoEvent {
  event_id: string;
  ts: string; // ISO-8601
  lat: number | null;
  lon: number | null;
  theme: string | null;
  tone: number | null; // GDELT tone ∈ [-100, +100] in raw; usually [-10, +10] post-norm
  src_url: string | null;
  place: string | null;
}

export interface GeoEventsResp {
  window: string;
  since: string;
  themes: string[];
  events: GeoEvent[];
}

// Filter state held by the parent and threaded into both query + UI.
export interface LiveMapFilters {
  window: string; // "1h" | "6h" | "24h" | "7d"
  themes: string; // comma-separated GDELT theme prefixes
  toneCutoff: number; // hide |tone| < cutoff; 0 = show all
}
