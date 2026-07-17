import { beforeEach, describe, expect, it } from "vitest";
import type { ReservoirImportResponse } from "../api/client";
import type { FieldSetupMemo } from "../memo/studyMemo";
import type { TerrainData } from "../viewport/terrain";
import {
  nativeWellPosition,
  useFieldStore,
  type FieldPlacement,
  type ReservoirRef,
  type TerrainRef,
} from "./field.store";

const terrain: TerrainRef = {
  terrain_id: "terrain-abc",
  sha256: "A".repeat(64),
  source_path: "C:/dem.tif",
  extent: { minLon: 107, maxLon: 108, minLat: -7, maxLat: -6 },
};

const reservoir: ReservoirRef = {
  model_id: "m1",
  sha256: "B".repeat(64),
  source_file: "case_0016.mat",
  native_fingerprint: "fp-native",
  covered_fingerprints: ["fp-native"],
  bank_id: null,
  well_ij: [30, 36],
  length_x_m: 900,
  length_y_m: 600,
};

const placement: FieldPlacement = {
  name: "Test Field",
  center_lat: -6.5,
  center_lon: 107.5,
  rotation_deg: 0,
};

const overview: TerrainData = {
  width: 2,
  height: 2,
  extent: terrain.extent,
  minElev: 10,
  maxElev: 40,
  elevations: [10, 20, 30, 40],
};

const reservoirRuntime = {
  model_id: reservoir.model_id,
  sha256: reservoir.sha256,
  source_file: reservoir.source_file,
  geology: { length_x_m: 900, length_y_m: 600 },
  native_schedule: { injection_duration_days: 45 },
  native_fingerprint: reservoir.native_fingerprint,
  native_seed: { schedule_fingerprint: reservoir.native_fingerprint },
  bank_seeds: {},
  well_ij: reservoir.well_ij,
  completion_ij: [reservoir.well_ij],
  launchpads: {
    bank_id: null,
    bank_sha256: null,
    covered_fingerprints: reservoir.covered_fingerprints,
  },
} satisfies ReservoirImportResponse;

describe("field store", () => {
  beforeEach(() => useFieldStore.getState().reset());

  it("setup derives the native well from well_ij", () => {
    useFieldStore
      .getState()
      .setup(terrain, reservoir, placement, overview, reservoirRuntime);
    const state = useFieldStore.getState();
    expect(state.overviewData).toBe(overview);
    expect(state.reservoirRuntime).toBe(reservoirRuntime);
    expect(state.wells).toHaveLength(1);
    expect(state.wells[0]).toMatchObject({
      id: "W01",
      name: "W01",
      kind: "native",
    });
    const expected = nativeWellPosition(placement, reservoir);
    expect(state.wells[0].lat).toBeCloseTo(expected.lat, 8);
    expect(state.wells[0].lon).toBeCloseTo(expected.lon, 8);
    expect(state.wells[0].lon).toBeGreaterThan(placement.center_lon);
  });

  it("moveField re-derives the native well while placed wells stay put", () => {
    useFieldStore.getState().setup(terrain, reservoir, placement);
    const placed = useFieldStore.getState().addWell(-6.52, 107.52);

    useFieldStore.getState().moveField(-6.6, 107.6);

    const after = useFieldStore.getState();
    expect(after.wells[0].lat).not.toBeCloseTo(-6.5, 4);
    expect(after.wells.find((well) => well.id === placed.id)?.lat).toBe(-6.52);
  });

  it("keeps ids stable when wells are renamed", () => {
    useFieldStore.getState().setup(terrain, reservoir, placement);
    const placed = useFieldStore.getState().addWell(-6.52, 107.52);

    useFieldStore.getState().renameWell("W01", "Native producer");
    useFieldStore.getState().renameWell(placed.id, "North candidate");

    expect(useFieldStore.getState().wells).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ id: "W01", name: "Native producer" }),
        expect.objectContaining({ id: "W02", name: "North candidate" }),
      ]),
    );
  });

  it("does not move or remove the native well", () => {
    useFieldStore.getState().setup(terrain, reservoir, placement);
    const native = { ...useFieldStore.getState().wells[0] };

    useFieldStore.getState().moveWell(native.id, 0, 0);
    useFieldStore.getState().removeWell(native.id);

    expect(useFieldStore.getState().wells[0]).toEqual(native);
  });

  it("assigns zero-padded stable source ids", () => {
    const source = useFieldStore.getState().addSource({
      name: "Plant",
      lat: -6.4,
      lon: 107.6,
      annual_capacity_t: 100_000,
      outlet_pressure_bar: 120,
      outlet_temperature_c: 27,
      co2_purity: 0.95,
      max_mass_flow_kg_s: 600,
    });

    expect(source.id).toBe("S01");
    expect(useFieldStore.getState().sources[0]).toEqual(source);
  });

  it("enters and exits the field only when a reservoir is loaded", () => {
    useFieldStore.getState().enterField();
    expect(useFieldStore.getState().level).toBe("basin");

    useFieldStore.getState().setup(terrain, reservoir, placement);
    useFieldStore.getState().enterField();
    expect(useFieldStore.getState().level).toBe("field");
    useFieldStore.getState().exitField();
    expect(useFieldStore.getState().level).toBe("basin");
  });

  it("hydrates memo coordinates without re-deriving the native well", () => {
    const setup: FieldSetupMemo = {
      terrain,
      reservoir,
      placement,
      wells: [
        {
          id: "W01",
          name: "Memo native",
          kind: "native",
          lat: -6.123,
          lon: 107.987,
        },
      ],
      sources: [],
    };

    useFieldStore.getState().setup(terrain, reservoir, placement, overview);
    useFieldStore.getState().hydrate(setup);

    expect(useFieldStore.getState().overviewData).toBeNull();
    expect(useFieldStore.getState().reservoirRuntime).toBeNull();
    expect(useFieldStore.getState().wells[0]).toMatchObject({
      id: "W01",
      name: "Memo native",
      lat: -6.123,
      lon: 107.987,
    });
  });
});
