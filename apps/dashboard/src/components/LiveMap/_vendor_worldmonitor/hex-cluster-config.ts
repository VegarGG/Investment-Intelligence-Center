// Adapted from koala73/worldmonitor (AGPL-3.0, © Elie Habib 2024-2026).
// Source: https://github.com/koala73/worldmonitor
// Modified by the IIC project under the same AGPL-3.0 terms for non-commercial use.
//
// Hex-cluster aggregation config for deck.gl's HexagonLayer. The radius
// (in meters) and density-color thresholds were tuned for GDELT-style
// global event volumes (≈ 50–5 000 events / 24h). At lower density the
// dashboard falls back to a ScatterplotLayer; this config only kicks in
// when `events.length > clusterThreshold`.

export interface HexClusterConfig {
  /** Hex cell radius in meters. ~80 km gives a balance of resolution
   *  and legibility at zoom 1.5–4 (global-scale view). */
  radius: number;
  /** Vertical scale factor for the elevation extrusion. */
  elevationScale: number;
  /** Layer alpha. Below 0.5 hexes blend nicely with the basemap. */
  opacity: number;
  /** Switch from per-event ScatterplotLayer to HexagonLayer once the
   *  visible-events count crosses this threshold. */
  clusterThreshold: number;
  /** Min/max for color mapping (low density → high density). */
  colorRange: ReadonlyArray<readonly [number, number, number, number]>;
}

export const DEFAULT_HEX_CONFIG: HexClusterConfig = {
  radius: 80_000,
  elevationScale: 50,
  opacity: 0.45,
  clusterThreshold: 500,
  // Low → high density. Tuned to match deck.gl's "warm" sequential ramp
  // but desaturated to avoid clashing with the per-event tone colors.
  colorRange: [
    [110, 200, 255, 200], // low density — pale blue
    [255, 235, 80, 200], // moderate — yellow
    [255, 165, 0, 220], // notable — orange
    [255, 80, 80, 240], // dense — red
    [180, 0, 200, 255], // very dense — magenta
  ],
};
