import { describe, expect, it, vi } from "vitest";

import { streamChat } from "../lib/sse";

function mockResponse(stream: ReadableStream<Uint8Array>): Response {
  return new Response(stream, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
}

describe("streamChat", () => {
  it("yields SSE chunks parsed from data: lines", async () => {
    const enc = new TextEncoder();
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(enc.encode("data: hello\n\n"));
        controller.enqueue(enc.encode("event: token\ndata: world\n\n"));
        controller.close();
      },
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(mockResponse(body)),
    );

    const tokens: { event?: string; data: string }[] = [];
    for await (const tok of streamChat({ message: "hi" })) {
      tokens.push(tok);
    }
    expect(tokens).toEqual([
      { event: undefined, data: "hello" },
      { event: "token", data: "world" },
    ]);

    vi.unstubAllGlobals();
  });

  it("throws on non-2xx", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { status: 500 })),
    );
    const iter = streamChat({ message: "hi" });
    await expect(iter.next()).rejects.toThrow(/500/);
    vi.unstubAllGlobals();
  });
});
