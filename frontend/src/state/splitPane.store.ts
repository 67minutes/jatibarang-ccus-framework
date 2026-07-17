import { create } from "zustand";

export type SplitPaneId = "left" | "right" | "bottom";

export interface SplitPaneSize {
  defaultSize: number;
  minSize: number;
  maxSize: number;
}

export const SPLIT_PANE_SIZES: Record<SplitPaneId, SplitPaneSize> = {
  left: { defaultSize: 248, minSize: 180, maxSize: 420 },
  right: { defaultSize: 320, minSize: 260, maxSize: 520 },
  // The bottom pane's effective maximum is also capped to 70% of the center.
  bottom: { defaultSize: 340, minSize: 180, maxSize: Number.POSITIVE_INFINITY },
};

export const BOTTOM_PANE_MAX_FRACTION = 0.7;

export function splitPaneLimits(
  panel: SplitPaneId,
  availableSize?: number,
): { min: number; max: number } {
  const definition = SPLIT_PANE_SIZES[panel];
  if (panel !== "bottom" || availableSize == null || !Number.isFinite(availableSize)) {
    return { min: definition.minSize, max: definition.maxSize };
  }

  return {
    min: definition.minSize,
    max: Math.max(definition.minSize, availableSize * BOTTOM_PANE_MAX_FRACTION),
  };
}

export function clampSplitPaneSize(
  panel: SplitPaneId,
  size: number,
  availableSize?: number,
): number {
  const { min, max } = splitPaneLimits(panel, availableSize);
  return Math.min(max, Math.max(min, Math.round(size)));
}

interface SplitPaneState {
  sizes: Record<SplitPaneId, number>;
  setSize: (panel: SplitPaneId, size: number, availableSize?: number) => void;
  resetSize: (panel: SplitPaneId, availableSize?: number) => void;
  resetAll: () => void;
}

const DEFAULT_SIZES: Record<SplitPaneId, number> = {
  left: SPLIT_PANE_SIZES.left.defaultSize,
  right: SPLIT_PANE_SIZES.right.defaultSize,
  bottom: SPLIT_PANE_SIZES.bottom.defaultSize,
};

/**
 * Session-local panel geometry. Visibility remains in workspace.store so the
 * existing View menu continues to own show/hide commands; hiding a pane never
 * destroys its last usable size.
 */
export const useSplitPaneStore = create<SplitPaneState>((set) => ({
  sizes: { ...DEFAULT_SIZES },
  setSize: (panel, size, availableSize) =>
    set((state) => ({
      sizes: {
        ...state.sizes,
        [panel]: clampSplitPaneSize(panel, size, availableSize),
      },
    })),
  resetSize: (panel, availableSize) =>
    set((state) => ({
      sizes: {
        ...state.sizes,
        [panel]: clampSplitPaneSize(
          panel,
          SPLIT_PANE_SIZES[panel].defaultSize,
          availableSize,
        ),
      },
    })),
  resetAll: () => set({ sizes: { ...DEFAULT_SIZES } }),
}));

