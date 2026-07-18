import { afterEach, describe, expect, it, vi } from "vitest";
import {
  getReservoir,
  getTerrainWindow,
  importReservoir,
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
});
