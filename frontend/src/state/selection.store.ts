import { create } from "zustand";

/**
 * The shared selection model (design §4.1) — the spine of the workbench.
 *
 * A single global selection is written by the project tree, the 3D/2D scene,
 * and the ranking table alike, and read by the inspector, economics, and
 * production panels. The carbon-price context is part of selection: moving the
 * scrubber re-pivots which plan is shown, with no API call.
 */

export type SelectionKind = "source" | "well" | "route" | "facility" | "none";

export interface Selection {
  kind: SelectionKind;
  /** Object id: candidate_id, source id, or segment/route id. */
  id: string | null;
  /** Optional scenario id when a specific well x schedule cell is meant. */
  scenarioId?: string | null;
}

interface SelectionState {
  selection: Selection;
  /** Carbon-price scenario id currently in focus (drives the plan pivot). */
  carbonPriceId: string | null;
  select: (selection: Selection) => void;
  clear: () => void;
  setCarbonPrice: (carbonPriceId: string | null) => void;
}

const EMPTY: Selection = { kind: "none", id: null, scenarioId: null };

export const useSelectionStore = create<SelectionState>((set) => ({
  selection: EMPTY,
  carbonPriceId: null,
  select: (selection) => set({ selection }),
  clear: () => set({ selection: EMPTY }),
  setCarbonPrice: (carbonPriceId) => set({ carbonPriceId }),
}));
