/**
 * Ambient type for the optional `nats.ws` runtime dependency.
 *
 * The dashboard lazy-imports `nats.ws` only when the WebSocket bridge
 * is actually used; we declare a minimal shape here so the typechecker
 * doesn't complain at build time even when the package isn't installed.
 */

declare module "nats.ws" {
  export interface NatsLikeMessage {
    data: Uint8Array;
  }

  export interface NatsLikeConnection {
    subscribe: (subject: string) => AsyncIterable<NatsLikeMessage>;
    close: () => Promise<void>;
  }

  export function connect(opts: { servers: string; token: string }): Promise<NatsLikeConnection>;
}
