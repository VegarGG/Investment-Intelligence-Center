// Right-side panel that opens when a map point is clicked. Shows the
// event's theme, place, tone, source URL.

import type { GeoEvent } from "./types";

interface Props {
  event: GeoEvent | null;
  onClose: () => void;
}

export function EventDrawer({ event, onClose }: Props) {
  if (!event) return null;
  return (
    <div
      className="absolute right-0 top-0 z-10 h-full w-72 overflow-y-auto border-l border-zinc-800 bg-zinc-950/95 p-4 text-sm shadow-xl"
      data-testid="livemap-drawer"
    >
      <button
        type="button"
        onClick={onClose}
        className="float-right text-xs text-zinc-500 hover:text-zinc-300"
        aria-label="Close event drawer"
      >
        ✕
      </button>
      <h3 className="font-medium text-zinc-200">{event.theme ?? "GDELT event"}</h3>
      <p className="mt-1 text-xs text-zinc-500">{new Date(event.ts).toUTCString()}</p>

      <dl className="mt-3 space-y-2 text-xs">
        <div>
          <dt className="text-zinc-500">Place</dt>
          <dd className="text-zinc-200">{event.place ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-zinc-500">Tone</dt>
          <dd className={tonalClass(event.tone)}>
            {event.tone == null ? "—" : event.tone.toFixed(2)}
          </dd>
        </div>
        <div>
          <dt className="text-zinc-500">Lat / Lon</dt>
          <dd className="font-mono text-zinc-200">
            {event.lat?.toFixed(3) ?? "—"}, {event.lon?.toFixed(3) ?? "—"}
          </dd>
        </div>
        {event.src_url && (
          <div>
            <dt className="text-zinc-500">Source</dt>
            <dd>
              <a
                href={event.src_url}
                target="_blank"
                rel="noreferrer noopener"
                className="break-all text-blue-400 hover:underline"
              >
                {event.src_url}
              </a>
            </dd>
          </div>
        )}
        <div>
          <dt className="text-zinc-500">Event ID</dt>
          <dd className="break-all font-mono text-xs text-zinc-500">{event.event_id}</dd>
        </div>
      </dl>
    </div>
  );
}

function tonalClass(tone: number | null): string {
  if (tone == null) return "text-zinc-200";
  if (tone < -0.3) return "text-rose-400";
  if (tone > 0.3) return "text-emerald-400";
  return "text-zinc-300";
}
