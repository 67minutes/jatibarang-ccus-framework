import { create } from "zustand";
import type { CellField } from "../api/types";
import type { StaticReservoirField } from "../viewport/reservoirGeometry";

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
  terrain: boolean;
  roads: boolean;
  coastline: boolean;
  places: boolean;
  wells: boolean;
  routes: boolean;
  boosters: boolean;
  exclusions: boolean;
  influence: boolean;
  labels: boolean;
  reservoir: boolean;
  reservoirGrid: boolean;
  propertyFill: boolean;
  facies: boolean;
  barriers: boolean;
  fractures: boolean;
  dynamicResponse: boolean;
  responseColumns: boolean;
}

export type ViewportTool = "select" | "orbit" | "probe" | "measure" | "elevation";

export interface MeasurementPoint {
  latitude: number;
  longitude: number;
  elevation_m: number;
}

export interface GridProbeReadout {
  i: number;
  j: number;
  colorField: CellField;
  colorValue: number;
  heightField: CellField;
  heightValue: number;
  staticField?: StaticReservoirField;
  staticValue?: number;
  porosity?: number;
  facies?: number;
  structure_m?: number;
  barrier?: number;
  fracture?: number;
}

interface WorkspaceState {
  viewport: "2d" | "3d";
  colorField: CellField;
  heightField: CellField;
  verticalExaggeration: number;
  reservoirVerticalExaggeration: number;
  reservoirStaticField: StaticReservoirField;
  dynamicOpacity: number;
  plumeThreshold: number;
  terrainPalette: "geologic" | "monochrome";
  cameraMotion: boolean;
  layers: LayerVisibility;
  timelineStep: number;
  timelineFrameCount: number;
  timelinePlaying: boolean;
  activeTool: ViewportTool;
  measurementPoints: MeasurementPoint[];
  gridProbe: GridProbeReadout | null;
  activeTab: DashboardTab;
  panels: { tree: boolean; inspector: boolean; dashboard: boolean };

  setViewport: (v: "2d" | "3d") => void;
  toggleViewport: () => void;
  setColorField: (f: CellField) => void;
  setHeightField: (f: CellField) => void;
  setExaggeration: (x: number) => void;
  setReservoirExaggeration: (x: number) => void;
  setReservoirStaticField: (field: StaticReservoirField) => void;
  setDynamicOpacity: (opacity: number) => void;
  setPlumeThreshold: (threshold: number) => void;
  setTerrainPalette: (palette: "geologic" | "monochrome") => void;
  setCameraMotion: (enabled: boolean) => void;
  toggleLayer: (layer: keyof LayerVisibility) => void;
  setTimelineStep: (step: number) => void;
  setTimelineFrameCount: (count: number) => void;
  toggleTimelinePlaying: () => void;
  setActiveTool: (tool: ViewportTool) => void;
  addMeasurementPoint: (point: MeasurementPoint) => void;
  clearMeasurement: () => void;
  setGridProbe: (readout: GridProbeReadout | null) => void;
  setActiveTab: (tab: DashboardTab) => void;
  togglePanel: (panel: "tree" | "inspector" | "dashboard") => void;
}

export const EXAGGERATION_MIN = 1;
export const EXAGGERATION_MAX = 10;
export const RESERVOIR_EXAGGERATION_MIN = 1;
export const RESERVOIR_EXAGGERATION_MAX = 20;

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  viewport: "3d",
  colorField: "z_co2",
  heightField: "z_co2",
  verticalExaggeration: 5,
  reservoirVerticalExaggeration: 8,
  reservoirStaticField: "permeability_md",
  dynamicOpacity: 0.58,
  plumeThreshold: 0.01,
  terrainPalette: "geologic",
  cameraMotion: true,
  layers: {
    terrain: true,
    roads: true,
    coastline: true,
    places: true,
    wells: true,
    routes: true,
    boosters: true,
    exclusions: true,
    influence: true,
    labels: true,
    reservoir: true,
    reservoirGrid: true,
    propertyFill: true,
    facies: false,
    barriers: false,
    fractures: false,
    dynamicResponse: true,
    responseColumns: false,
  },
  timelineStep: 24,
  timelineFrameCount: 0,
  timelinePlaying: false,
  activeTool: "select",
  measurementPoints: [],
  gridProbe: null,
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
  setReservoirExaggeration: (reservoirVerticalExaggeration) =>
    set({
      reservoirVerticalExaggeration: Math.min(
        RESERVOIR_EXAGGERATION_MAX,
        Math.max(RESERVOIR_EXAGGERATION_MIN, reservoirVerticalExaggeration),
      ),
    }),
  setReservoirStaticField: (reservoirStaticField) => set({ reservoirStaticField }),
  setDynamicOpacity: (dynamicOpacity) =>
    set({ dynamicOpacity: Math.min(0.9, Math.max(0.05, dynamicOpacity)) }),
  setPlumeThreshold: (plumeThreshold) =>
    set({ plumeThreshold: Math.min(1, Math.max(0, plumeThreshold)) }),
  setTerrainPalette: (terrainPalette) => set({ terrainPalette }),
  setCameraMotion: (cameraMotion) => set({ cameraMotion }),
  toggleLayer: (layer) =>
    set((s) => ({ layers: { ...s.layers, [layer]: !s.layers[layer] } })),
  setTimelineStep: (timelineStep) =>
    set((s) => ({
      timelineStep: Math.max(
        0,
        Math.min(Math.max(0, s.timelineFrameCount - 1), timelineStep),
      ),
    })),
  setTimelineFrameCount: (timelineFrameCount) =>
    set((s) => ({
      timelineFrameCount,
      timelineStep:
        s.timelineFrameCount === 0 && timelineFrameCount > 0
          ? Math.min(timelineFrameCount - 1, Math.floor(timelineFrameCount * 0.72))
          : Math.min(Math.max(0, timelineFrameCount - 1), s.timelineStep),
    })),
  toggleTimelinePlaying: () =>
    set((s) => ({ timelinePlaying: !s.timelinePlaying })),
  setActiveTool: (activeTool) =>
    set({
      activeTool,
      gridProbe: null,
      measurementPoints: [],
    }),
  addMeasurementPoint: (point) =>
    set((s) => ({
      measurementPoints:
        s.measurementPoints.length >= 2
          ? [point]
          : [...s.measurementPoints, point],
    })),
  clearMeasurement: () => set({ measurementPoints: [] }),
  setGridProbe: (gridProbe) => set({ gridProbe }),
  setActiveTab: (activeTab) => set({ activeTab }),
  togglePanel: (panel) =>
    set((s) => ({ panels: { ...s.panels, [panel]: !s.panels[panel] } })),
}));
