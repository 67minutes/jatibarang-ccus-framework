import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ScreenRequest, ScreenResult } from "../api/types";
import { useFieldStore, type FieldPlacement, type ReservoirRef, type TerrainRef } from "../state/field.store";
import { useUiStore } from "../state/ui.store";
import type { TerrainData } from "../viewport/terrain";
import { snapshotFieldSetup } from "./export";
import { hydrateMemoFieldSetup } from "./import";
import {
  entryToMemo,
  isLegacyMemo,
  STUDY_MEMO_KIND,
  STUDY_MEMO_VERSION,
  type FieldSetupMemo,
  type LedgerEntry,
  type StudyMemo,
} from "./studyMemo";

const terrain: TerrainRef = {
  terrain_id: "terrain-abc",
  sha256: "A".repeat(64),
  source_path: "C:/dem.tif",
  extent: { minLon: 107, maxLon: 108, minLat: -7, maxLat: -6 },
};

const reservoir: ReservoirRef = {
  model_id: "model-1",
  sha256: "B".repeat(64),
  source_file: "case_0016.mat",
  native_fingerprint: "native-fingerprint",
  covered_fingerprints: ["native-fingerprint"],
  bank_id: null,
  bank_sha256: null,
  well_ij: [30, 36],
  length_x_m: 900,
  length_y_m: 600,
};

const placement: FieldPlacement = {
  name: "Memo field",
  center_lat: -6.53,
  center_lon: 108.39,
  rotation_deg: 35,
};

const setup: FieldSetupMemo = {
  terrain,
  reservoir,
  placement,
  wells: [
    {
      id: "W01",
      name: "Native well",
      kind: "native",
      lat: -6.53,
      lon: 108.39,
    },
    {
      id: "W02",
      name: "North candidate",
      kind: "placed",
      lat: -6.52,
      lon: 108.4,
    },
  ],
  sources: [
    {
      id: "S01",
      name: "Subang source",
      lat: -6.57,
      lon: 107.76,
      annual_capacity_t: 100_000,
      outlet_pressure_bar: 120,
      outlet_temperature_c: 27,
      co2_purity: 0.98,
      max_mass_flow_kg_s: 5,
    },
  ],
};

const overview: TerrainData = {
  width: 2,
  height: 2,
  extent: terrain.extent,
  minElev: 10,
  maxElev: 40,
  elevations: [10, 20, 30, 40],
};

function memo(
  memoVersion: number,
  fieldSetup: FieldSetupMemo | undefined,
): StudyMemo {
  return {
    kind: STUDY_MEMO_KIND,
    memo_version: memoVersion,
    app_version: "test",
    api_contract_version: "test",
    saved_at: "2026-07-18T00:00:00.000Z",
    label: "memo",
    field_setup: fieldSetup,
    request: {} as ScreenRequest,
    fingerprint: "F".repeat(64),
    result: {} as ScreenResult,
  };
}

describe("memo v3", () => {
  beforeEach(() => {
    useFieldStore.getState().reset();
    useUiStore.setState({ banners: [] });
    vi.unstubAllGlobals();
  });

  it("flags older memos as legacy", () => {
    expect(STUDY_MEMO_VERSION).toBe(3);
    expect(isLegacyMemo({ memo_version: 2 })).toBe(true);
    expect(isLegacyMemo({ memo_version: 3 })).toBe(false);
  });

  it("exports a deep lightweight field snapshot without runtime payloads", () => {
    const liveTerrain: TerrainRef = {
      ...terrain,
      extent: { ...terrain.extent },
    };
    const liveReservoir: ReservoirRef = {
      ...reservoir,
      covered_fingerprints: [...reservoir.covered_fingerprints],
      well_ij: [...reservoir.well_ij],
    };
    useFieldStore
      .getState()
      .setup(liveTerrain, liveReservoir, placement, overview, {
        geology: { permeability_md: [1, 2, 3] },
      } as never);
    useFieldStore.getState().addWell(-6.51, 108.41);
    const { id: _sourceId, ...source } = setup.sources[0];
    useFieldStore.getState().addSource(source);

    const snapshot = snapshotFieldSetup();
    expect(snapshot).toBeDefined();
    expect(snapshot).not.toHaveProperty("overviewData");
    expect(snapshot).not.toHaveProperty("reservoirRuntime");
    expect(snapshot).toEqual({
      terrain,
      reservoir,
      placement,
      wells: useFieldStore.getState().wells,
      sources: useFieldStore.getState().sources,
    });

    liveTerrain.extent.minLon = 0;
    liveReservoir.well_ij[0] = 0;
    useFieldStore.getState().wells[0].name = "mutated";
    expect(snapshot!.terrain.extent.minLon).toBe(107);
    expect(snapshot!.reservoir.well_ij).toEqual([30, 36]);
    expect(snapshot!.wells[0].name).toBe("W01");

    const entry = {
      label: "memo",
      request: {} as ScreenRequest,
      result: {} as ScreenResult,
      fingerprint: "F".repeat(64),
    } as LedgerEntry;
    expect(entryToMemo(entry, "app", "api", snapshot).field_setup).toBe(
      snapshot,
    );
  });

  it("references field artifacts instead of embedding geology and launch pads", () => {
    const request = {
      mode: "inline",
      geologies: { "model-1": { permeability_md: Array(4096).fill(100) } },
      seeds: { launchpad: { pressure: Array(4096).fill(1) } },
      candidates: [],
      sources: [],
      operational_grid: null,
      schedules: [],
      annual_co2_budget_tonnes: 1,
      carbon_prices: [],
      fiscal_cases: [],
      economic_assumptions: {},
    } satisfies ScreenRequest;
    const entry = {
      entryId: "entry-1",
      label: "memo",
      request,
      result: {} as ScreenResult,
      fingerprint: "F".repeat(64),
      savedAt: "2026-07-18T00:00:00.000Z",
      imported: false,
    } satisfies LedgerEntry;

    const saved = entryToMemo(entry, "app", "api", setup);

    expect(saved.request_payload_mode).toBe("artifact_referenced");
    expect(saved.request).toMatchObject({ geologies: {}, seeds: {} });
    expect(request.geologies).toHaveProperty("model-1");
    expect(JSON.stringify(saved).length).toBeLessThan(10_000);
  });

  it("hydrates field references, refetches terrain, and leaves runtime null", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(overview))),
    );

    await hydrateMemoFieldSetup(memo(3, setup));

    const field = useFieldStore.getState();
    expect(field.terrain).toEqual(terrain);
    expect(field.reservoir).toEqual(reservoir);
    expect(field.placement).toEqual(placement);
    expect(field.wells).toEqual(setup.wells);
    expect(field.sources).toEqual(setup.sources);
    expect(field.overviewData).toEqual(overview);
    expect(field.reservoirRuntime).toBeNull();
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe(
      "/terrain/terrain-abc/window?min_lon=107&min_lat=-7&max_lon=108&max_lat=-6&max_px=512",
    );
  });

  it("clears stale field state and shows the exact legacy notice", async () => {
    useFieldStore
      .getState()
      .setup(terrain, reservoir, placement, overview, {} as never);

    await hydrateMemoFieldSetup(memo(2, undefined));

    expect(useFieldStore.getState().terrain).toBeNull();
    expect(useFieldStore.getState().reservoirRuntime).toBeNull();
    expect(useUiStore.getState().banners).toContainEqual({
      id: "memo-legacy",
      severity: "info",
      message:
        "This memo predates field setups; opened read-only without a field scene.",
    });
  });

  it("clears stale field state and legacy banners for v3 without a setup", async () => {
    useFieldStore
      .getState()
      .setup(terrain, reservoir, placement, overview, {} as never);
    useUiStore.getState().pushBanner({
      id: "memo-legacy",
      severity: "info",
      message: "stale",
    });

    await hydrateMemoFieldSetup(memo(3, undefined));

    expect(useFieldStore.getState().terrain).toBeNull();
    expect(useFieldStore.getState().reservoirRuntime).toBeNull();
    expect(useUiStore.getState().banners).toEqual([]);
  });

  it("keeps hydrated references when terrain overview refetch fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("offline", { status: 503 })));

    await expect(hydrateMemoFieldSetup(memo(3, setup))).resolves.toBeUndefined();
    expect(useFieldStore.getState().terrain).toEqual(terrain);
    expect(useFieldStore.getState().overviewData).toBeNull();
    expect(useFieldStore.getState().reservoirRuntime).toBeNull();
  });
});
