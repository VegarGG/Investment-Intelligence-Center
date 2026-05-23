# `_vendor_worldmonitor/` — adapted patterns from koala73/worldmonitor

This subtree contains code patterns adapted from
[koala73/worldmonitor](https://github.com/koala73/worldmonitor)
(AGPL-3.0, © Elie Habib 2024–2026). All files here are licensed under
AGPL-3.0; see [`LICENSE.AGPL-3.0`](./LICENSE.AGPL-3.0) for the full text.

## What's vendored

| File | What it is | Source pattern |
|---|---|---|
| [`hex-cluster-config.ts`](./hex-cluster-config.ts) | deck.gl `HexagonLayer` configuration (radius, opacity, density threshold) for clustering geo-events at low zoom | worldmonitor's globe / flat map layer config |

## What is NOT vendored

Per D9 §5.2, IIC vendors *patterns*, not the worldmonitor codebase
verbatim. The vendored config above is small and IIC-specific; the
surrounding deck.gl + MapLibre integration in `MapCanvas.tsx` was
written from scratch against the deck.gl + MapLibre public docs.

No worldmonitor TypeScript, no worldmonitor protobuf contracts, no
worldmonitor news-feed aggregation, no worldmonitor Tauri scaffolding,
no worldmonitor i18n, no worldmonitor basemap JSONs are imported.

## Vendored from

| | |
|---|---|
| upstream repo | https://github.com/koala73/worldmonitor |
| upstream commit SHA | (none — patterns adapted from public docs; no source files were copied verbatim) |
| date adapted | 2026-05-22 |
| IIC license posture | personal/research use only — D9 §5.3 decision 1 |

If `koala73/worldmonitor` re-licenses or shuts down, this directory is
the only one that needs review. The rest of the LiveMap component
(`MapCanvas.tsx`, `LiveMap.tsx`, hooks, types) is IIC-original and
relies only on deck.gl + MapLibre's documented public APIs.

## If commercial intent ever appears

Per D9 §5.3, the obligation in that case is: **delete this directory
and re-implement the hex-cluster pattern from scratch using only the
deck.gl docs.** The pattern is documented at
<https://deck.gl/docs/api-reference/aggregation-layers/hexagon-layer>
and the rewrite is straightforward.
