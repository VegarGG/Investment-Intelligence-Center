import { create } from "zustand";

import type { Tone } from "../types/iic";

interface ToneState {
  tone: Tone;
  setTone: (tone: Tone) => void;
}

export const useToneStore = create<ToneState>((set) => ({
  tone: "conv",
  setTone: (tone) => set({ tone }),
}));
