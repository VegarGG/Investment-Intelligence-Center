import { ALL_TONES, TONE_DESCRIPTIONS, TONE_LABELS } from "../lib/tone";
import { useToneStore } from "../store/tone";
import type { Tone } from "../types/iic";
import { api } from "../lib/api";

export function ToneSlider() {
  const tone = useToneStore((s) => s.tone);
  const setTone = useToneStore((s) => s.setTone);

  const onChange = (next: Tone) => {
    setTone(next);
    void api.setTone(next).catch(() => {
      // Network failure leaves the local state changed; the next render
      // is allowed to show stale state. The pending sync banner handles
      // user-visible feedback in a real app.
    });
  };

  return (
    <div className="flex items-center gap-2 text-sm">
      <label className="text-zinc-400" htmlFor="tone">
        Tone
      </label>
      <select
        id="tone"
        className="rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1 text-sm"
        value={tone}
        onChange={(e) => onChange(e.target.value as Tone)}
        aria-label="Conversation tone"
      >
        {ALL_TONES.map((t) => (
          <option key={t} value={t} title={TONE_DESCRIPTIONS[t]}>
            {TONE_LABELS[t]}
          </option>
        ))}
      </select>
    </div>
  );
}
