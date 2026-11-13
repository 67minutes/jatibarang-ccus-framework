import { create, type StoreApi, type UseBoundStore } from "zustand";
import type { RoadLayers, ReservoirImportResponse } from "../api/client";
import type { FieldSetupMemo } from "../memo/studyMemo";
import type { TerrainData } from "../viewport/terrain";

/** Hash-addressed terrain registered by the local backend. */
export interface TerrainRef {
  terrain_id: string;
  sha256: string;
  source_path: string;
  extent: {
    minLon: number;
    maxLon: number;
    minLat: number;
    maxLat: number;
  };
}

/** User-declared placement for an otherwise ungeoreferenced reservoir model. */
export interface FieldPlacement {
  name: string;
  center_lat: number;
  center_lon: number;
  rotation_deg: number;
}

/** Lightweight reference to one imported reservoir model and its launch pads. */
export interface ReservoirRef {
  model_id: string;
  sha256: string;
  source_file: string;
  native_fingerprint: string;
  covered_fingerprints: string[];
  bank_id: string | null;
  bank_sha256: string | null;
  well_ij: [number, number];
  length_x_m: number;
  length_y_m: number;
}

export interface RoadsRef {
  road_network_id: string;
  sha256: string;
  source_path: string;
}

export interface PlacedWell {
  /** Stable request/selection identity. Renaming never changes this value. */
  id: string;
  /** Human-facing label, independently editable from the stable id. */
  name: string;
  kind: "native" | "placed";
  lat: number;
  lon: number;
}

export interface PlacedSource {
  id: string;
  name: string;
  lat: number;
  lon: number;
  annual_capacity_t: number;
  outlet_pressure_bar: number;
  outlet_temperature_c: number;
  co2_purity: number;
  max_mass_flow_kg_s: number;
}

export type SceneLevel = "earth" | "basin" | "field";

interface FieldState {
  terrain: TerrainRef | null;
  /** Runtime overview used by the viewport; deliberately excluded from memos. */
  overviewData: TerrainData | null;
  reservoir: ReservoirRef | null;
  /**
   * Complete import payload needed to build a pre-run reservoir scene and an
   * inline screening request. It may be large, so it is held by reference for
   * this session only and is deliberately absent from FieldSetupMemo.
   */
  reservoirRuntime: ReservoirImportResponse | null;
  /** Optional well-specific geology assignment; absent wells use the primary model. */
  reservoirAssignments: Record<string, ReservoirRef>;
  /** Session-only payloads paired with reservoirAssignments. */
  reservoirRuntimes: Record<string, ReservoirImportResponse>;
  roads: RoadsRef | null;
  /** Simplified runtime map layers; deliberately excluded from memos. */
  roadLayers: RoadLayers | null;
  placement: FieldPlacement | null;
  /** The first well is the model's native well whenever a reservoir is set. */
  wells: PlacedWell[];
  sources: PlacedSource[];
  level: SceneLevel;

  setup: (
    terrain: TerrainRef,
    reservoir: ReservoirRef,
    placement: FieldPlacement,
    overviewData?: TerrainData | null,
    reservoirRuntime?: ReservoirImportResponse | null,
    reservoirAssignments?: Record<string, ReservoirRef>,
    reservoirRuntimes?: Record<string, ReservoirImportResponse>,
  ) => void;
  setRoads: (roads: RoadsRef | null, layers: RoadLayers | null) => void;
  moveField: (center_lat: number, center_lon: number) => void;
  rotateField: (rotation_deg: number) => void;
  addWell: (lat: number, lon: number) => PlacedWell;
  moveWell: (id: string, lat: number, lon: number) => void;
  renameWell: (id: string, name: string) => void;
  removeWell: (id: string) => void;
  addSource: (source: Omit<PlacedSource, "id">) => PlacedSource;
  updateSource: (
    id: string,
    patch: Partial<Omit<PlacedSource, "id">>,
  ) => void;
  removeSource: (id: string) => void;
  enterBasin: () => void;
  exitBasin: () => void;
  enterField: () => void;
  exitField: () => void;
  reset: () => void;
  hydrate: (setup: FieldSetupMemo) => void;
}

const EMPTY_STATE = {
  terrain: null,
  overviewData: null,
  reservoir: null,
  reservoirRuntime: null,
  reservoirAssignments: {},
  reservoirRuntimes: {},
  roads: null,
  roadLayers: null,
  placement: null,
  wells: [],
  sources: [],
  level: "earth" as const,
};

function degreesToRadians(value: number): number {
  return (value * Math.PI) / 180;
}

/**
 * Convert the native MRST well cell to a map coordinate relative to the field
 * anchor. The imported model has no surveyed orientation; rotation is the
 * user's local-proxy placement only.
 */
export function nativeWellPosition(
  placement: FieldPlacement,
  reservoir: ReservoirRef,
): { lat: number; lon: number } {
  const dx =
    (reservoir.well_ij[1] + 0.5 - 32) * (reservoir.length_x_m / 64);
  const dy =
    (reservoir.well_ij[0] + 0.5 - 32) * (reservoir.length_y_m / 64);
  const angle = degreesToRadians(placement.rotation_deg);
  const east = dx * Math.cos(angle) - dy * Math.sin(angle);
  const north = dx * Math.sin(angle) + dy * Math.cos(angle);
  const metresPerDegreeLongitude =
    111_320 * Math.cos(degreesToRadians(placement.center_lat));

  return {
    lat: placement.center_lat + north / 111_320,
    lon: placement.center_lon + east / metresPerDegreeLongitude,
  };
}

function nativeWell(
  placement: FieldPlacement,
  reservoir: ReservoirRef,
  name = "W01",
): PlacedWell {
  const position = nativeWellPosition(placement, reservoir);
  return { id: "W01", name, kind: "native", ...position };
}

function nextId(prefix: string, ids: string[]): string {
  const highest = ids.reduce((max, id) => {
    const match = new RegExp(`^${prefix}(\\d+)$`, "i").exec(id);
    return match ? Math.max(max, Number(match[1])) : max;
  }, 0);
  return `${prefix}${String(highest + 1).padStart(2, "0")}`;
}

function rederiveNativeWell(
  wells: PlacedWell[],
  placement: FieldPlacement,
  reservoir: ReservoirRef,
): PlacedWell[] {
  const currentNative = wells.find((well) => well.kind === "native");
  const updated = nativeWell(
    placement,
    reservoir,
    currentNative?.name || currentNative?.id || "W01",
  );
  return [updated, ...wells.filter((well) => well.kind !== "native")];
}

export const useFieldStore: UseBoundStore<StoreApi<FieldState>> =
  create<FieldState>((set, get) => ({
    ...EMPTY_STATE,

    setup: (
      terrain,
      reservoir,
      placement,
      overviewData = null,
      reservoirRuntime = null,
      reservoirAssignments = { W01: reservoir },
      reservoirRuntimes = reservoirRuntime ? { W01: reservoirRuntime } : {},
    ) =>
      set({
        terrain,
        overviewData,
        reservoir,
        reservoirRuntime,
        reservoirAssignments,
        reservoirRuntimes,
        roads: null,
        roadLayers: null,
        placement,
        wells: [nativeWell(placement, reservoir)],
        sources: [],
        level: "basin",
      }),

    setRoads: (roads, roadLayers) => set({ roads, roadLayers }),

    moveField: (center_lat, center_lon) =>
      set((state) => {
        if (!state.placement || !state.reservoir) return {};
        const placement = { ...state.placement, center_lat, center_lon };
        return {
          placement,
          wells: rederiveNativeWell(state.wells, placement, state.reservoir),
        };
      }),

    rotateField: (rotation_deg) =>
      set((state) => {
        if (!state.placement || !state.reservoir) return {};
        const placement = { ...state.placement, rotation_deg };
        return {
          placement,
          wells: rederiveNativeWell(state.wells, placement, state.reservoir),
        };
      }),

    addWell: (lat, lon) => {
      const id = nextId(
        "W",
        get().wells.map((well) => well.id),
      );
      const well: PlacedWell = { id, name: id, kind: "placed", lat, lon };
      set((state) => ({ wells: [...state.wells, well] }));
      return well;
    },

    moveWell: (id, lat, lon) =>
      set((state) => ({
        wells: state.wells.map((well) =>
          well.id === id && well.kind === "placed"
            ? { ...well, lat, lon }
            : well,
        ),
      })),

    renameWell: (id, name) => {
      const displayName = name.trim();
      if (!displayName) return;
      set((state) => ({
        wells: state.wells.map((well) =>
          well.id === id ? { ...well, name: displayName } : well,
        ),
      }));
    },

    removeWell: (id) =>
      set((state) => {
        const removed = state.wells.find(
          (well) => well.id === id && well.kind !== "native",
        );
        if (!removed) return {};
        const reservoirAssignments = { ...state.reservoirAssignments };
        const reservoirRuntimes = { ...state.reservoirRuntimes };
        delete reservoirAssignments[id];
        delete reservoirRuntimes[id];
        return {
          wells: state.wells.filter((well) => well.id !== id),
          reservoirAssignments,
          reservoirRuntimes,
        };
      }),

    addSource: (source) => {
      const id = nextId(
        "S",
        get().sources.map((item) => item.id),
      );
      const placed: PlacedSource = { ...source, id };
      set((state) => ({ sources: [...state.sources, placed] }));
      return placed;
    },

    updateSource: (id, patch) =>
      set((state) => ({
        sources: state.sources.map((source) =>
          source.id === id ? { ...source, ...patch } : source,
        ),
      })),

    removeSource: (id) =>
      set((state) => ({
        sources: state.sources.filter((source) => source.id !== id),
      })),

    enterBasin: () => {
      if (get().terrain) set({ level: "basin" });
    },
    exitBasin: () => set({ level: "earth" }),

    enterField: () => {
      if (get().reservoir) set({ level: "field" });
    },
    exitField: () => set({ level: "basin" }),
    reset: () => set({ ...EMPTY_STATE }),

    hydrate: (setup) =>
      set({
        terrain: { ...setup.terrain, extent: { ...setup.terrain.extent } },
        // Reopened memos carry only hash-addressed references. Task 8 relinks
        // the overview through the registry rather than embedding raster data.
        overviewData: null,
        reservoir: {
          ...setup.reservoir,
          well_ij: [...setup.reservoir.well_ij],
          covered_fingerprints: [...setup.reservoir.covered_fingerprints],
        },
        // Runtime geology and launch pads are never serialized into a portable
        // result summary; memo hydration relinks them by id and hash.
        reservoirRuntime: null,
        reservoirAssignments: Object.fromEntries(
          Object.entries(setup.reservoir_assignments ?? { W01: setup.reservoir }).map(
            ([wellId, reference]) => [
              wellId,
              {
                ...reference,
                well_ij: [...reference.well_ij],
                covered_fingerprints: [...reference.covered_fingerprints],
              },
            ],
          ),
        ),
        reservoirRuntimes: {},
        roads: setup.roads ? { ...setup.roads } : null,
        roadLayers: null,
        placement: { ...setup.placement },
        // Preserve memo coordinates exactly. A later move/rotate re-derives
        // only the native well from the imported model.
        wells: setup.wells.map((well) => ({
          ...well,
          name: well.name || well.id,
        })),
        sources: setup.sources.map((source) => ({ ...source })),
        level: "basin",
      }),
  }));
