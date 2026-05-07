import ReactMarkdown from "react-markdown";
import { useRef, useState } from "react";
import rehypeSanitize from "rehype-sanitize";

import { ToneSlider } from "../components/ToneSlider";
import { Card } from "../components/ui/Card";
import { streamChat } from "../lib/sse";

interface Turn {
  role: "user" | "assistant";
  text: string;
}

export function Chat() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const onSend = async () => {
    const text = input.trim();
    if (!text || streaming) return;
    setInput("");
    setTurns((t) => [...t, { role: "user", text }, { role: "assistant", text: "" }]);
    setStreaming(true);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      for await (const tok of streamChat({ message: text, signal: controller.signal })) {
        setTurns((prev) => {
          const next = prev.slice();
          const last = next[next.length - 1];
          next[next.length - 1] = { ...last, text: last.text + tok.data };
          return next;
        });
      }
    } catch (err) {
      setTurns((prev) => {
        const next = prev.slice();
        const last = next[next.length - 1];
        next[next.length - 1] = {
          ...last,
          text: `${last.text}\n\n*chat stream failed: ${err instanceof Error ? err.message : err}*`,
        };
        return next;
      });
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  };

  const onCancel = () => {
    abortRef.current?.abort();
  };

  return (
    <Card title="Chat with the Secretary">
      <div className="mb-3 flex justify-end">
        <ToneSlider />
      </div>
      <ul className="mb-3 max-h-[60vh] space-y-3 overflow-y-auto">
        {turns.map((turn, i) => (
          <li
            key={i}
            className={`rounded-md p-3 text-sm ${
              turn.role === "user"
                ? "bg-zinc-800/40 text-zinc-200"
                : "bg-emerald-900/20 text-emerald-100"
            }`}
          >
            <div className="prose prose-invert prose-sm max-w-none">
              <ReactMarkdown rehypePlugins={[rehypeSanitize]}>
                {turn.text || (turn.role === "assistant" ? "_thinking…_" : "")}
              </ReactMarkdown>
            </div>
          </li>
        ))}
      </ul>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void onSend();
        }}
      >
        <input
          type="text"
          className="flex-1 rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm"
          placeholder="Ask the Secretary…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={streaming}
        />
        {streaming ? (
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md border border-rose-700 bg-rose-900/40 px-3 py-2 text-sm"
          >
            Stop
          </button>
        ) : (
          <button
            type="submit"
            className="rounded-md border border-emerald-700 bg-emerald-900/40 px-3 py-2 text-sm"
          >
            Send
          </button>
        )}
      </form>
    </Card>
  );
}
