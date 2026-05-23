// deck.gl + MapLibre canvas (D9 §5.7). Per-event ScatterplotLayer when
// the visible-event count is small; HexagonLayer cluster takes over at
// scale. Hex-cluster config is adapted from worldmonitor; see
// _vendor_worldmonitor/README.md for license posture.

import { useMemo } from "react";
import DeckGL from "@deck.gl/react";
import { ScatterplotLayer } from "@deck.gl/layers";
import { HexagonLayer } from "@deck.gl/aggregation-layers";
import { MapView } from "@deck.gl/core";
import { Map as MapLibre } from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";

import type { GeoEvent } from "./types";
import { DEFAULT_HEX_CONFIG } from "./_vendor_worldmonitor/hex-cluster-config";

interface Props {
  events: GeoEvent[];
  onSelect?: (e: GeoEvent | null) => void;
  height?: number;
  /** Override the basemap. Default is the public MapLibre demo style;
   *  swap to a self-hosted style JSON for prod. */
  mapStyle?: string;
}

const DEFAULT_STYLE = "https://demotiles.maplibre.org/style.json";

// Tone ∈ [-10, +10] post-normalization. Negative = red, positive = green;
// |tone| drives saturation, so neutral events (~0) read as muted blue.
function toneColor(tone: number | null): [number, number, number, number] {
  const t = tone ?? 0;
  const mag = Math.min(1, Math.abs(t) / 10);
  const alpha = 160 + Math.round(mag * 80);
  if (t < -0.3) return [248, 113, 113, alpha];
  if (t > 0.3) return [52, 211, 153, alpha];
  return [148, 163, 184, alpha];
}

// Marker size scales with |tone| so high-magnitude events pop visually.
function toneRadius(tone: number | null): number {
  return 30_000 + Math.min(1.5, Math.abs(tone ?? 0) / 5) * 60_000;
}

interface Point extends GeoEvent {
  // deck.gl needs concrete [lon, lat]; null-island fallback for null coords.
  position: [number, number];
}

export function MapCanvas({ events, onSelect, height = 560, mapStyle = DEFAULT_STYLE }: Props) {
  const points = useMemo<Point[]>(
    () =>
      events
        .filter((e) => e.lat != null && e.lon != null)
        .map((e) => ({ ...e, position: [e.lon as number, e.lat as number] })),
    [events],
  );

  const dense = points.length > DEFAULT_HEX_CONFIG.clusterThreshold;

  const layers = [
    new HexagonLayer<Point>({
      id: "hex",
      data: points,
      getPosition: (p) => p.position,
      radius: DEFAULT_HEX_CONFIG.radius,
      elevationScale: DEFAULT_HEX_CONFIG.elevationScale,
      opacity: DEFAULT_HEX_CONFIG.opacity,
      colorRange: DEFAULT_HEX_CONFIG.colorRange.map((c) => [...c]) as [number, number, number, number][],
      pickable: false,
      visible: dense,
    }),
    new ScatterplotLayer<Point>({
      id: "points",
      data: points,
      getPosition: (p) => p.position,
      getRadius: (p) => toneRadius(p.tone),
      getFillColor: (p) => toneColor(p.tone),
      pickable: true,
      stroked: true,
      lineWidthMinPixels: 0.5,
      visible: !dense,
      onClick: (info) => onSelect?.(info.object ?? null),
    }),
  ];

  return (
    <div style={{ position: "relative", width: "100%", height }} data-testid="livemap-canvas">
      <DeckGL
        initialViewState={{ longitude: 0, latitude: 20, zoom: 1.4, pitch: 0, bearing: 0 }}
        controller={true}
        layers={layers}
        views={new MapView({ repeat: true })}
        style={{ position: "absolute", inset: "0" }}
      >
        <MapLibre mapStyle={mapStyle} attributionControl={true} />
      </DeckGL>
    </div>
  );
}
