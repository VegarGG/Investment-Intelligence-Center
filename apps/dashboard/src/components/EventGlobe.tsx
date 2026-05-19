// Geo globe (P5.3). Lazy-loads react-globe.gl so the rest of the
// dashboard doesn't pay the Three.js bundle cost on first paint.
import { Suspense, lazy, useMemo } from "react";

import type { GeoEvent } from "../routes/Map";

const Globe = lazy(() => import("react-globe.gl").then((m) => ({ default: m.default })));

interface Props {
  events: GeoEvent[];
  height?: number;
}

export function EventGlobe({ events, height = 500 }: Props) {
  const points = useMemo(
    () =>
      events.map((e) => ({
        lat: e.lat ?? 0,
        lng: e.lon ?? 0,
        size: 0.2 + Math.min(1.5, Math.abs(e.tone ?? 0) / 5),
        color: (e.tone ?? 0) < 0 ? "#f87171" : "#34d399",
        label:
          `<div style="background:#0a0a0a;padding:6px;border-radius:4px">` +
          `<strong>${e.theme ?? "GDELT event"}</strong><br/>` +
          `${e.place ?? "?"}<br/>` +
          `tone=${(e.tone ?? 0).toFixed(2)}` +
          `</div>`,
      })),
    [events],
  );

  return (
    <Suspense fallback={<div className="h-[500px] grid place-items-center text-zinc-500">Loading globe…</div>}>
      <Globe
        height={height}
        backgroundColor="rgba(0,0,0,0)"
        globeImageUrl="//unpkg.com/three-globe/example/img/earth-night.jpg"
        pointsData={points}
        pointAltitude={(d: { size: number }) => d.size * 0.05}
        pointColor={(d: { color: string }) => d.color}
        pointRadius={(d: { size: number }) => d.size}
        pointLabel={(d: { label: string }) => d.label}
      />
    </Suspense>
  );
}
