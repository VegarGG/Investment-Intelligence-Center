/**
 * Tiny SSE helper for the Secretary `/chat` endpoint (workflow 21 §5.8).
 *
 * `EventSource` is GET-only, so a POST-style chat requires a fetch with
 * a streaming reader. This helper wraps that pattern for `useChat`.
 */

export interface SseToken {
  data: string;
  event?: string;
}

export interface ChatRequest {
  message: string;
  signal?: AbortSignal;
}

export async function* streamChat(req: ChatRequest): AsyncIterableIterator<SseToken> {
  const resp = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ message: req.message }),
    signal: req.signal,
  });
  if (!resp.ok || !resp.body) {
    throw new Error(`chat stream failed: ${resp.status}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const chunk = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const parsed = parseSseChunk(chunk);
      if (parsed) yield parsed;
    }
  }
}

function parseSseChunk(chunk: string): SseToken | null {
  let event: string | undefined;
  const data: string[] = [];
  for (const line of chunk.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).trim());
  }
  if (data.length === 0) return null;
  return { event, data: data.join("\n") };
}
