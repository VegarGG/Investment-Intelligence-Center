// LiveMap smoke (D9 §5.8 L2, vitest version).
//
// Asserts the empty-state path renders cleanly when /api/geo/events
// returns zero events. Full L3-L7 (deck.gl layer assertions, streaming,
// hex cluster at scale) need a real DOM + WebGL context — those move
// to playwright once the harness lands.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LiveMap } from "../components/LiveMap";

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("LiveMap", () => {
  beforeEach(() => {
    // happy-dom doesn't ship WebSocket; stub it so the stream hook is inert.
    (globalThis as unknown as { WebSocket: unknown }).WebSocket = class {
      onopen?: () => void;
      onmessage?: (e: { data: string }) => void;
      onclose?: () => void;
      onerror?: () => void;
      close() {}
    };

    global.fetch = vi.fn(async () =>
      new Response(
        JSON.stringify({ window: "24h", since: "2026-01-01T00:00:00Z", themes: [], events: [] }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    ) as unknown as typeof fetch;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the filter panel and a no-events empty state", async () => {
    wrap(<LiveMap disableStream />);

    expect(screen.getByText(/Window/i)).toBeInTheDocument();
    expect(screen.getByText(/Themes/i)).toBeInTheDocument();
    expect(await screen.findByTestId("livemap-empty")).toHaveTextContent(/no events/i);
  });
});
