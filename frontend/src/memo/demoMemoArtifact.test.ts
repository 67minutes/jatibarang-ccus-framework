import { readFileSync, statSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import type { ScreenResult } from "../api/types";
import { isStudyMemo } from "./studyMemo";

const memoPath = resolve(
  process.cwd(),
  "../data/jatibarang/jatibarang.study.json",
);
const wellsPath = resolve(process.cwd(), "../data/jatibarang/demo_wells.csv");

describe("checked-in Jatibarang study memo", () => {
  it("is a bounded, internally consistent, read-only result summary", () => {
    expect(statSync(memoPath).size).toBeLessThan(5_000_000);

    const parsed: unknown = JSON.parse(readFileSync(memoPath, "utf8"));
    expect(isStudyMemo(parsed)).toBe(true);
    if (!isStudyMemo(parsed)) throw new Error("Invalid study memo fixture.");

    expect(parsed.request_payload_mode).toBe("artifact_referenced");
    expect(parsed.result_payload_mode).toBe("summary");
    const setup = parsed.field_setup;
    expect(setup).toBeDefined();
    if (!setup) throw new Error("Study memo has no field setup.");
    expect(setup.terrain.sha256).toBe(
      "AA9CC7AD4BD0CB390A80CB8B2CE06061745CFCFE2B010D39F808CF74C506826E",
    );
    expect(setup.placement).toMatchObject({
      center_lat: -6.53,
      center_lon: 108.39,
      rotation_deg: 35,
    });
    expect(setup.wells).toHaveLength(20);
    expect(setup.sources).toEqual([
      expect.objectContaining({
        lat: -6.571,
        lon: 107.759,
        annual_capacity_t: 500_000,
        outlet_pressure_bar: 120,
        outlet_temperature_c: 27,
        co2_purity: 0.95,
        max_mass_flow_kg_s: 600,
      }),
    ]);

    const csvRows = readFileSync(wellsPath, "utf8")
      .trim()
      .split(/\r?\n/)
      .slice(1)
      .map((row) => {
        const [id, lat, lon] = row.split(",");
        return { id, lat: Number(lat), lon: Number(lon) };
      });
    expect(csvRows).toHaveLength(20);
    for (const csvWell of csvRows.slice(1)) {
      expect(setup.wells.find((well) => well.id === csvWell.id)).toMatchObject(
        csvWell,
      );
    }
    expect(parsed.request.mode).toBe("inline");
    if (parsed.request.mode !== "inline") throw new Error("Expected inline summary.");
    expect(parsed.request).not.toHaveProperty("geologies");
    expect(parsed.request).not.toHaveProperty("seeds");
    expect(parsed.fingerprint).toBe(parsed.result.request_fingerprint);
    expect(parsed.result.detailed_reservoirs).toEqual({});

    const result = parsed.result as ScreenResult;
    for (const prediction of Object.values(result.detailed_predictions)) {
      expect(prediction.fields).toBeNull();
    }
    for (const plan of result.plans) {
      for (const strategy of plan.well_strategies) {
        expect(strategy.prediction.fields).toBeNull();
      }
    }
  });
});
