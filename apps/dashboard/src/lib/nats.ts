/**
 * NATS WebSocket subscription hook (workflow 21 §5.7).
 *
 * The actual `nats.ws` import is loaded lazily so the bundle doesn't
 * pay the cost when the dashboard renders without live data. Falls back
 * to TanStack polling when the WS handshake fails.
 */

import { useEffect, useRef, useState } from "react";

import { api } from "./api";

interface NatsLikeConnection {
  subscribe: (subject: string) => AsyncIterable<{ data: Uint8Array }>;
  close: () => Promise<void>;
}

type NatsConnectFn = (opts: { servers: string; token: string }) => Promise<NatsLikeConnection>;

let connectImpl: NatsConnectFn | null = null;

export function setConnectImpl(fn: NatsConnectFn | null): void {
  connectImpl = fn;
}

async function defaultConnect(opts: { servers: string; token: string }): Promise<NatsLikeConnection> {
  if (connectImpl) return connectImpl(opts);
  // Lazy ESM import — keeps the cold bundle small.
  const mod = (await import(/* @vite-ignore */ "nats.ws")) as {
    connect: (o: { servers: string; token: string }) => Promise<NatsLikeConnection>;
  };
  return mod.connect(opts);
}

export interface SubscriptionState<T> {
  events: T[];
  connected: boolean;
  error: string | null;
}

export function useSubscription<T>(
  subject: string,
  parse: (raw: string) => T,
  buffer = 50,
): SubscriptionState<T> {
  const [state, setState] = useState<SubscriptionState<T>>({
    events: [],
    connected: false,
    error: null,
  });
  const conn = useRef<NatsLikeConnection | null>(null);
  const cancelled = useRef(false);

  useEffect(() => {
    cancelled.current = false;

    (async () => {
      try {
        const { token } = await api.dashboardToken();
        const c = await defaultConnect({
          servers: `wss://${window.location.host}/nats`,
          token,
        });
        conn.current = c;
        if (cancelled.current) {
          await c.close();
          return;
        }
        setState((s) => ({ ...s, connected: true, error: null }));
        const decoder = new TextDecoder();
        for await (const msg of c.subscribe(subject)) {
          if (cancelled.current) break;
          try {
            const evt = parse(decoder.decode(msg.data));
            setState((s) => ({
              ...s,
              events: [evt, ...s.events].slice(0, buffer),
            }));
          } catch {
            // ignore decode failures — keep stream alive
          }
        }
      } catch (err) {
        if (!cancelled.current) {
          setState((s) => ({
            ...s,
            connected: false,
            error: err instanceof Error ? err.message : String(err),
          }));
        }
      }
    })();

    return () => {
      cancelled.current = true;
      conn.current?.close().catch(() => undefined);
    };
  }, [subject, buffer, parse]);

  return state;
}
