// Filter inputs for the LiveMap. Compact horizontal layout matching the
// rest of the dashboard's Card chrome.

import type { LiveMapFilters } from "./types";

interface Props {
  value: LiveMapFilters;
  onChange: (next: LiveMapFilters) => void;
  count?: number;
  streamStatus?: string;
}

export function FilterPanel({ value, onChange, count, streamStatus }: Props) {
  return (
    <div className="mb-3 flex flex-wrap items-end gap-3 text-xs">
      <label>
        <div className="text-zinc-500">Window</div>
        <select
          value={value.window}
          onChange={(e) => onChange({ ...value, window: e.target.value })}
          className="rounded bg-zinc-900 px-2 py-1"
        >
          <option value="1h">1h</option>
          <option value="6h">6h</option>
          <option value="24h">24h</option>
          <option value="7d">7d</option>
        </select>
      </label>

      <label className="flex-1 min-w-[12rem]">
        <div className="text-zinc-500">Themes (comma-separated GDELT prefixes)</div>
        <input
          value={value.themes}
          onChange={(e) => onChange({ ...value, themes: e.target.value })}
          placeholder="ECON_,TAX_,WB_"
          className="w-full rounded bg-zinc-900 px-2 py-1 font-mono"
        />
      </label>

      <label>
        <div className="text-zinc-500">|tone| ≥</div>
        <input
          type="number"
          step="0.5"
          min={0}
          max={10}
          value={value.toneCutoff}
          onChange={(e) => onChange({ ...value, toneCutoff: Number(e.target.value) })}
          className="w-16 rounded bg-zinc-900 px-2 py-1"
        />
      </label>

      <span className="text-zinc-500">
        {count == null ? "—" : `${count} events`}
        {streamStatus && streamStatus !== "open" ? ` · stream ${streamStatus}` : ""}
      </span>
    </div>
  );
}
