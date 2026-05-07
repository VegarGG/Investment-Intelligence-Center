import type { Tone } from "../types/iic";

export const TONE_LABELS: Record<Tone, string> = {
  terse: "Terse",
  conv: "Conversational",
  edu: "Educational",
};

export const TONE_DESCRIPTIONS: Record<Tone, string> = {
  terse: "Numbers first, no analogies. For trading hours.",
  conv: "Plain language with light explanations. Default.",
  edu: "Family-friendly. Analogies, no acronyms, company names instead of tickers.",
};

export const ALL_TONES: Tone[] = ["terse", "conv", "edu"];
