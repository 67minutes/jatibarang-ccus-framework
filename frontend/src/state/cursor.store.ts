import { create } from "zustand";

/**
 * Ambient cursor readout for the status bar (design §3.6). Written by the
 * viewport as the pointer moves over the scene; cleared when it leaves.
 */
export interface CursorReadout {
  i: number;
  j: number;
  latitude: number | null;
  longitude: number | null;
  elevation_m: number | null;
}

interface CursorState {
  readout: CursorReadout | null;
  setReadout: (readout: CursorReadout | null) => void;
}

export const useCursorStore = create<CursorState>((set) => ({
  readout: null,
  setReadout: (readout) => set({ readout }),
}));
