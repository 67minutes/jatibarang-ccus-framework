import { beforeEach, describe, expect, it, vi } from "vitest";
import type { RoadLayers } from "../api/client";
import type { ScreenRequest, ScreenResult } from "../api/types";
import { useFieldStore, type FieldPlacement, type ReservoirRef, type TerrainRef } from "../state/field.store";
import { useUiStore } from "../state/ui.store";
import type { TerrainData } from "../viewport/terrain";
import { snapshotFieldSetup } from "./export";
import { hydrateMemoFieldSetup } from "./import";
import {
  entryToMemo,
  isStudyMemo,
  isLegacyMemo,
  memoToEntry,
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

const roads = {
  road_network_id: "roads-a",
  sha256: "R".repeat(64),
  source_path: "C:/java.osm.pbf",
};

const roadLayers: RoadLayers = {
  roads: [{ class: "major", points: [[-6.5, 107.5], [-6.4, 107.6]] }],
  coastline: [],
  places: [{ name: "Testville", lat: -6.45, lon: 107.55, kind: "town" }],
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

const reservoirRuntime = {
  model_id: reservoir.model_id,
  sha256: reservoir.sha256,
  source_file: reservoir.source_file,
  geology: {},
  native_schedule: {},
  native_fingerprint: reservoir.native_fingerprint,
  native_seed: {},
  bank_seeds: {},
  well_ij: reservoir.well_ij,
  completion_ij: [reservoir.well_ij],
  launchpads: {
    bank_id: reservoir.bank_id,
    bank_sha256: reservoir.bank_sha256,
    covered_fingerprints: reservoir.covered_fingerprints,
  },
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

describe("study memos", () => {
  beforeEach(() => {
    useFieldStore.getState().reset();
    useUiStore.setState({ banners: [] });
    vi.unstubAllGlobals();
  });

  it("flags older memos as legacy", () => {
    expect(STUDY_MEMO_VERSION).toBe(4);
    expect(isLegacyMemo({ memo_version: 2 })).toBe(true);
    expect(isLegacyMemo({ memo_version: 3 })).toBe(false);
  });

  it("recognizes omitted catalogs and accepts legacy empty catalogs", () => {
    const request: Record<string, unknown> = { mode: "inline" };
    const candidate: Record<string, unknown> = {
      ...memo(3, setup),
      request_payload_mode: "artifact_referenced",
      result_payload_mode: "summary",
      request,
    };

    expect(isStudyMemo(candidate)).toBe(true);
    candidate.result_payload_mode = undefined;
    expect(isStudyMemo(candidate)).toBe(true);
    candidate.result_payload_mode = "summary";
    request.geologies = {};
    request.seeds = {};
    expect(isStudyMemo(candidate)).toBe(true);
    request.geologies = { unexpected: {} };
    expect(isStudyMemo(candidate)).toBe(false);
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
      reservoir_assignments: { W01: reservoir },
      roads: null,
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
    const result = {
      request_fingerprint: "F".repeat(64),
      plans: [
        {
          well_strategies: [
            {
              prediction: {
                fields: [{ step_index: 0, pressure_bar: [[100]] }],
              },
            },
          ],
        },
      ],
      detailed_predictions: {
        "W01--native": {
          scenario_id: "W01--native",
          fields: [
            {
              step_index: 0,
              pressure_bar: [[100]],
              gas_saturation: [[0.1]],
              z_co2: [[0.8]],
              oil_saturation: null,
              origin: "surrogate",
            },
          ],
        },
      },
      detailed_reservoirs: {
        "W01--native": { scenario_id: "W01--native" },
      },
    } as unknown as ScreenResult;
    const entry = {
      entryId: "entry-1",
      label: "memo",
      request,
      result,
      fingerprint: "F".repeat(64),
      savedAt: "2026-07-18T00:00:00.000Z",
      imported: false,
    } satisfies LedgerEntry;

    const saved = entryToMemo(entry, "app", "api", setup);

    expect(saved.request_payload_mode).toBe("artifact_referenced");
    expect(saved.result_payload_mode).toBe("summary");
    expect(saved.request).not.toHaveProperty("geologies");
    expect(saved.request).not.toHaveProperty("seeds");
    expect(saved.result.detailed_predictions["W01--native"].fields).toBeNull();
    expect(saved.result.detailed_reservoirs).toEqual({});
    expect(saved.result.plans[0].well_strategies[0].prediction.fields).toBeNull();
    expect(request.geologies).toHaveProperty("model-1");
    expect(result.detailed_predictions["W01--native"].fields).toHaveLength(1);
    expect(result.plans[0].well_strategies[0].prediction.fields).toHaveLength(1);
    expect(JSON.stringify(saved).length).toBeLessThan(10_000);

    const restored = memoToEntry(saved, true);
    expect(restored.requestPayloadMode).toBe("artifact_referenced");
    expect(restored.resultPayloadMode).toBe("summary");

    const embedded = entryToMemo(entry, "app", "api");
    expect(embedded.request_payload_mode).toBe("embedded");
    expect(embedded.result_payload_mode).toBe("full");
    expect(embedded.result.detailed_predictions["W01--native"].fields).toHaveLength(1);
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

  it("relinks matching reservoir runtime payloads after hydration", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) =>
        new Response(
          JSON.stringify(
            String(input).startsWith("/reservoir/")
              ? reservoirRuntime
              : overview,
          ),
        ),
      ),
    );

    await hydrateMemoFieldSetup(memo(3, setup));

    expect(useFieldStore.getState().reservoirRuntime).toEqual(
      reservoirRuntime,
    );
  });

  it("relinks hash-addressed detailed fields before the memo enters the ledger", async () => {
    const opened = memo(4, setup);
    opened.result = {
      detailed_predictions: {
        "W01--native": { scenario_id: "W01--native", fields: null },
      },
      detailed_reservoirs: {},
    } as unknown as ScreenResult;
    opened.spatial_result = {
      artifact_id: "archive-1",
      sha256: "D".repeat(64),
      request_fingerprint: opened.fingerprint,
    };
    const detailedPredictions = {
      "W01--native": {
        scenario_id: "W01--native",
        fields: [{ step_index: 0 }],
      },
    } as unknown as ScreenResult["detailed_predictions"];
    const detailedReservoirs = {
      "W01--native": { scenario_id: "W01--native" },
    } as unknown as ScreenResult["detailed_reservoirs"];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.startsWith("/reservoir/")) {
          return new Response(JSON.stringify(reservoirRuntime));
        }
        if (url.startsWith("/screening/spatial/")) {
          return new Response(
            JSON.stringify({
              artifact_id: "archive-1",
              sha256: "D".repeat(64),
              payload: {
                request_fingerprint: opened.fingerprint,
                detailed_predictions: detailedPredictions,
                detailed_reservoirs: detailedReservoirs,
              },
            }),
          );
        }
        return new Response(JSON.stringify(overview));
      }),
    );

    await hydrateMemoFieldSetup(opened);

    expect(opened.result.detailed_predictions).toEqual(detailedPredictions);
    expect(opened.result.detailed_reservoirs).toEqual(detailedReservoirs);
    expect(useUiStore.getState().banners).not.toContainEqual(
      expect.objectContaining({ id: "memo-spatial-relink" }),
    );
  });

  it("rejects a reservoir relink whose content hash does not match", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) =>
        new Response(
          JSON.stringify(
            String(input).startsWith("/reservoir/")
              ? { ...reservoirRuntime, sha256: "C".repeat(64) }
              : overview,
          ),
        ),
      ),
    );

    await hydrateMemoFieldSetup(memo(3, setup));

    expect(useFieldStore.getState().reservoirRuntime).toBeNull();
  });

  it("keeps the memo open when reservoir relinking fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        if (String(input).startsWith("/reservoir/")) {
          return new Response("missing", { status: 404 });
        }
        return new Response(JSON.stringify(overview));
      }),
    );

    await expect(hydrateMemoFieldSetup(memo(3, setup))).resolves.toBeUndefined();
    expect(useFieldStore.getState().terrain).toEqual(terrain);
    expect(useFieldStore.getState().reservoirRuntime).toBeNull();
  });

  it("relinks saved road layers without embedding them in the memo", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.startsWith("/reservoir/")) {
          return new Response(JSON.stringify(reservoirRuntime));
        }
        if (url.startsWith("/roads/")) {
          return new Response(JSON.stringify(roadLayers));
        }
        return new Response(JSON.stringify(overview));
      }),
    );

    await hydrateMemoFieldSetup(memo(3, { ...setup, roads }));

    expect(useFieldStore.getState().roads).toEqual(roads);
    expect(useFieldStore.getState().roadLayers).toEqual(roadLayers);
    expect(useUiStore.getState().banners).not.toContainEqual(
      expect.objectContaining({ id: "roads-relink" }),
    );
  });

  it("keeps a study open and explains a missing saved road network", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.startsWith("/reservoir/")) {
          return new Response(JSON.stringify(reservoirRuntime));
        }
        if (url.startsWith("/roads/")) {
          return new Response("missing", { status: 404 });
        }
        return new Response(JSON.stringify(overview));
      }),
    );

    await hydrateMemoFieldSetup(memo(3, { ...setup, roads }));

    expect(useFieldStore.getState().terrain).toEqual(terrain);
    expect(useFieldStore.getState().roadLayers).toBeNull();
    expect(useUiStore.getState().banners).toContainEqual({
      id: "roads-relink",
      severity: "info",
      message:
        "The road network for this study could not be found; trucking falls back to the great-circle estimate until it is re-imported.",
    });
  });
});
