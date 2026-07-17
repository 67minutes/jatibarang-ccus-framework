import { describe, expect, it } from "vitest";

import { nativeWellPosition, useFieldStore } from "../state/field.store";
import {
  applyWellsCsvRows,
  parseWellsCsv,
  type WellsCsvRow,
} from "./wellsCsv";

describe("parseWellsCsv", () => {
  it("parses id,lat,lon with a header", () => {
    const rows = parseWellsCsv(
      "id,lat,lon\nW02,-6.47,108.31\nW03,-6.48,108.33\n",
    );

    expect(rows).toEqual([
      { id: "W02", lat: -6.47, lon: 108.31 },
      { id: "W03", lat: -6.48, lon: 108.33 },
    ]);
  });

  it("skips blank rows", () => {
    expect(parseWellsCsv("id,lat,lon\n\nW02,-6.47,108.31\n  \n")).toEqual([
      { id: "W02", lat: -6.47, lon: 108.31 },
    ]);
  });

  it("reports malformed coordinates with the offending line", () => {
    expect(() =>
      parseWellsCsv("id,lat,lon\nW02,not-a-number,108.31\n"),
    ).toThrow(/line 2/i);
  });

  it("rejects an invalid header", () => {
    expect(() => parseWellsCsv("name,lat,lon\nW02,-6.47,108.31\n")).toThrow(
      /header/i,
    );
  });

  it("rejects empty ids and unexpected columns", () => {
    expect(() => parseWellsCsv("id,lat,lon\n,-6.47,108.31\n")).toThrow(
      /line 2/i,
    );
    expect(() =>
      parseWellsCsv("id,lat,lon\nW02,-6.47,108.31,extra\n"),
    ).toThrow(/line 2/i);
  });

  it("rejects duplicate ids case-insensitively", () => {
    expect(() =>
      parseWellsCsv(
        "id,lat,lon\nW02,-6.47,108.31\nw02,-6.48,108.33\n",
      ),
    ).toThrow(/line 3/i);
  });

  it("keeps the derived native W01 and adds only the remaining rows", () => {
    useFieldStore.getState().reset();
    const terrain = {
      terrain_id: "terrain-a",
      sha256: "A".repeat(64),
      source_path: "data/imports/a/dem.tif",
      extent: { minLon: 107, minLat: -7, maxLon: 108, maxLat: -6 },
    };
    const reservoir = {
      model_id: "model-a",
      sha256: "B".repeat(64),
      source_file: "model.mat",
      native_fingerprint: "C".repeat(64),
      covered_fingerprints: ["C".repeat(64)],
      bank_id: null,
      bank_sha256: null,
      well_ij: [31, 32] as [number, number],
      length_x_m: 900,
      length_y_m: 600,
    };
    const placement = {
      name: "Field A",
      center_lat: -6.5,
      center_lon: 108,
      rotation_deg: 0,
    };
    useFieldStore.getState().setup(terrain, reservoir, placement);
    const expectedNative = nativeWellPosition(placement, reservoir);
    const rows: WellsCsvRow[] = [
      { id: "W01", lat: 0, lon: 0 },
      { id: "North", lat: -6.49, lon: 108.01 },
      { id: "South", lat: -6.51, lon: 107.99 },
    ];

    const added = applyWellsCsvRows(rows, useFieldStore.getState());
    const wells = useFieldStore.getState().wells;

    expect(added).toBe(2);
    expect(wells).toHaveLength(3);
    expect(wells[0]).toMatchObject({
      id: "W01",
      lat: expectedNative.lat,
      lon: expectedNative.lon,
    });
    expect(wells[1]).toMatchObject({
      id: "W02",
      name: "North",
      lat: -6.49,
      lon: 108.01,
    });
    expect(wells[2]).toMatchObject({ id: "W03", name: "South" });
  });
});
