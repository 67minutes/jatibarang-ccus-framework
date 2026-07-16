import { create } from "zustand";
import type { CellField } from "../api/types";

/**
 * Workspace view state: the viewport encoding, layer visibility, panel
 * visibility, and the active mode of the center region. This is presentation
 * state only — no study data lives here (see ledger.store for runs).
 */

export type DashboardTab =
  | "ranking"
  | "economics"
  | "production"
  | "run"
  | "compose";

export interface LayerVisibility {
  routes: boolean;
  boosters: boolean;
  exclusions: boolean;
  labels: boolean;
}

interface WorkspaceState {
  viewport: "2d" | "3d";
  colorField: CellField;
  heightField: CellField;
  verticalExaggeration: number;
  layers: LayerVisibility;
  timelineStep: number;
  timelinePlaying: boolean;
  activeTab: DashboardTab;
  panels: { tree: boolean; inspector: boolean; dashboard: boolean };

  setViewport: (v: "2d" | "3d") => void;
  toggleViewport: () => void;
  setColorField: (f: CellField) => void;
  setHeightField: (f: CellField) => void;
  setExaggeration: (x: number) => void;
  toggleLayer: (layer: keyof LayerVisibility) => void;
  setTimelineStep: (step: number) => void;
  toggleTimelinePlaying: () => void;
  setActiveTab: (tab: DashboardTab) => void;
  togglePanel: (panel: "tree" | "inspector" | "dashboard") => void;
}

export const EXAGGERATION_MIN = 1;
export const EXAGGERATION_MAX = 10;

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  viewport: "2d",
  colorField: "gas_saturation",
  heightField: "z_co2",
  verticalExaggeration: 5,
  layers: { routes: true, boosters: true, exclusions: true, labels: true },
  timelineStep: 0,
  timelinePlaying: false,
  activeTab: "compose",
  panels: { tree: true, inspector: true, dashboard: true },

  setViewport: (viewport) => set({ viewport }),
  toggleViewport: () =>
    set((s) => ({ viewport: s.viewport === "2d" ? "3d" : "2d" })),
  setColorField: (colorField) => set({ colorField }),
  setHeightField: (heightField) => set({ heightField }),
  setExaggeration: (verticalExaggeration) =>
    set({
      verticalExaggeration: Math.min(
        EXAGGERATION_MAX,
        Math.max(EXAGGERATION_MIN, verticalExaggeration),
      ),
    }),
  toggleLayer: (layer) =>
    set((s) => ({ layers: { ...s.layers, [layer]: !s.layers[layer] } })),
  setTimelineStep: (timelineStep) => set({ timelineStep }),
  toggleTimelinePlaying: () =>
    set((s) => ({ timelinePlaying: !s.timelinePlaying })),
  setActiveTab: (activeTab) => set({ activeTab }),
  togglePanel: (panel) =>
    set((s) => ({ panels: { ...s.panels, [panel]: !s.panels[panel] } })),
}));
