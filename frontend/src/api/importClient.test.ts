import { afterEach, describe, expect, it, vi } from "vitest";
import {
  archiveSpatialResult,
  getRoadLayers,
  getReservoir,
  getSpatialResult,
  getTerrainWindow,
  importReservoir,
  importReservoirCatalog,
  importRoads,
  importTerrain,
  listTerrains,
} from "./client";

describe("import client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("posts the terrain path and returns the registered record", async () => {
    const body = {
      terrain_id: "terrain-x",
      sha256: "A",
      extent: { minLon: 107, minLat: -7, maxLon: 108, maxLat: -6 },
      cell_size_m: 30,
      overview: {
        width: 1,
        height: 1,
        extent: { minLon: 107, minLat: -7, maxLon: 108, maxLat: -6 },
        minElev: 42,
        maxElev: 42,
        elevations: [42],
      },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(body))),
    );

    const result = await importTerrain("C:/dem.tif");

    expect(result.terrain_id).toBe("terrain-x");
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/terrain/import");
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      path: "C:/dem.tif",
    });
  });

  it("lists registered terrains", async () => {
    const body = [
      {
        terrain_id: "terrain-x",
        sha256: "A",
        source_path: "data/imports/x/dem.tif",
        extent: { minLon: 107, minLat: -7, maxLon: 108, maxLat: -6 },
        cell_size_m: 30,
      },
    ];
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(body))),
    );

    await expect(listTerrains()).resolves.toEqual(body);
    expect(vi.mocked(fetch)).toHaveBeenCalledWith("/terrain", {
      headers: { Accept: "application/json" },
    });
  });

  it("requests a bounded terrain window using backend query names", async () => {
    const body = {
      width: 2,
      height: 2,
      extent: { minLon: 107, minLat: -7, maxLon: 108, maxLat: -6 },
      minElev: 1,
      maxElev: 4,
      elevations: [1, 2, 3, 4],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(body))),
    );

    await getTerrainWindow(
      "terrain/x",
      { minLon: 107.1, minLat: -6.9, maxLon: 107.9, maxLat: -6.1 },
      512,
    );

    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toBe(
      "/terrain/terrain%2Fx/window?min_lon=107.1&min_lat=-6.9&max_lon=107.9&max_lat=-6.1&max_px=512",
    );
  });

  it("posts model and bank paths and keeps launch-pad payloads typed", async () => {
    const nativeSeed = { schedule_fingerprint: "F".repeat(64), frames: [] };
    const bankSeed = { schedule_fingerprint: "E".repeat(64), frames: [] };
    const body = {
      model_id: "m",
      sha256: "B",
      source_file: "model.mat",
      geology: {},
      native_schedule: {},
      native_fingerprint: nativeSeed.schedule_fingerprint,
      native_seed: nativeSeed,
      bank_seeds: { [bankSeed.schedule_fingerprint]: bankSeed },
      well_ij: [31, 32],
      completion_ij: [[31, 32]],
      launchpads: {
        bank_id: "bank-x",
        bank_sha256: "C",
        covered_fingerprints: [
          nativeSeed.schedule_fingerprint,
          bankSeed.schedule_fingerprint,
        ],
      },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(body))),
    );

    const result = await importReservoir(
      "C:/model.mat",
      "C:/model.launchpads.npz",
    );

    expect(result.native_seed).toEqual(nativeSeed);
    expect(result.bank_seeds[bankSeed.schedule_fingerprint]).toEqual(bankSeed);
    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      model_path: "C:/model.mat",
      bank_path: "C:/model.launchpads.npz",
    });
  });

  it("fetches a reservoir relink by model and bank id", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ model_id: "m1" }))),
    );

    const result = await getReservoir("m1", "b1");

    expect(result.model_id).toBe("m1");
    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/reservoir/m1?bank_id=b1");
  });

  it("imports a well-keyed reservoir catalog", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ reservoirs: {}, count: 2 })),
      ),
    );
    const entries = [
      { well_id: "W01", model_path: "C:/derived/W01.npz" },
      {
        well_id: "W02",
        model_path: "C:/derived/W02.npz",
        bank_path: "C:/derived/W02.launchpads.npz",
      },
    ];

    await expect(importReservoirCatalog(entries)).resolves.toMatchObject({
      count: 2,
    });
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/reservoir/import-batch");
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({ entries });
  });

  it("archives and restores detailed spatial screening fields", async () => {
    const result = {
      request_fingerprint: "A".repeat(64),
      detailed_predictions: { scenario: { scenario_id: "scenario" } },
      detailed_reservoirs: { scenario: { scenario_id: "scenario" } },
    } as never;
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({
              artifact_id: "archive-1",
              sha256: "B".repeat(64),
              request_fingerprint: "A".repeat(64),
              scenario_count: 1,
              compressed_bytes: 100,
            }),
          ),
        )
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({
              artifact_id: "archive-1",
              sha256: "B".repeat(64),
              payload: result,
            }),
          ),
        ),
    );

    await archiveSpatialResult(result);
    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect(JSON.parse((init as RequestInit).body as string)).toEqual(result);

    await expect(getSpatialResult("archive/1")).resolves.toMatchObject({
      artifact_id: "archive-1",
    });
    expect(vi.mocked(fetch).mock.calls[1][0]).toBe(
      "/screening/spatial/archive%2F1",
    );
  });

  it("imports a road network for a registered terrain", async () => {
    const body = {
      road_network_id: "roads-a",
      sha256: "D".repeat(64),
      node_count: 12,
      edge_count: 11,
      bbox: [107, -7, 108, -6],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(body))),
    );

    await expect(
      importRoads("C:/java.osm.pbf", "terrain-x"),
    ).resolves.toEqual(body);
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/roads/import");
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      path: "C:/java.osm.pbf",
      terrain_id: "terrain-x",
    });
  });

  it("fetches display layers for a road network", async () => {
    const body = { roads: [], coastline: [], places: [] };
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(body))),
    );

    await expect(getRoadLayers("roads-a")).resolves.toEqual(body);
    expect(vi.mocked(fetch)).toHaveBeenCalledWith("/roads/roads-a/layers", {
      headers: { Accept: "application/json" },
    });
  });
});
