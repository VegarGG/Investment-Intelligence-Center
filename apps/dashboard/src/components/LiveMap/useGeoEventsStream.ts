// WebSocket hook for /api/stream/geo_events.
// Receives newline-delimited JSON GeoEvent rows as they land in
// lake.geo_events. Maintains a bounded in-memory buffer (most-recent
// `max` events) so reconnect storms don't OOM the tab.

import { useEffect, useRef, useState } from "react";

import type { GeoEvent } from "./types";

interface Opts {
  enabled?: boolean;
  max?: number;
}

export function useGeoEventsStream({ enabled = true, max = 5000 }: Opts = {}) {
  const [events, setEvents] = useState<GeoEvent[]>([]);
  const [status, setStatus] = useState<"connecting" | "open" | "closed" | "error">("closed");
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!enabled) return;

    // Relative URL → nginx /api/stream/ proxy forwards to agent_intelligence.
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${proto}//${location.host}/api/stream/geo_events`;

    setStatus("connecting");
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => setStatus("open");
    ws.onerror = () => setStatus("error");
    ws.onclose = () => setStatus("closed");
    ws.onmessage = (msg) => {
      try {
        const ev: GeoEvent = JSON.parse(msg.data);
        setEvents((prev) => {
          const next = [ev, ...prev];
          return next.length > max ? next.slice(0, max) : next;
        });
      } catch {
        // Server sends one JSON object per message; ignore malformed frames.
      }
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [enabled, max]);

  return { events, status };
}
