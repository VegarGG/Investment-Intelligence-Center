// /map route entry. Delegates to the LiveMap component (D9 §5).
// The old EventGlobe-based implementation is being retired in Phase C
// of D9 V2 — flat map only per decision 2/6.
//
// The `GeoEvent` type used to live here; it now lives next to the
// rest of the LiveMap code at ../components/LiveMap/types.ts.
// Re-exported here for callers that imported it from this path.

export { LiveMap as MapRoute } from "../components/LiveMap";
export type { GeoEvent } from "../components/LiveMap";
