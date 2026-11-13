import { describe, expect, it } from "vitest";
import type { ReservoirImportResponse } from "../api/client";
import type { FieldSetupMemo } from "../memo/studyMemo";
import { comboFingerprint, scheduleCombos, type ScheduleCombo } from "./coverage";
import { createDefaultStudyRequestBase, DEFAULT_OPERATIONAL_GRID } from "./defaults";
import {
  buildStudyRequest,
  sourceValidationIssue,
  studySchedulePlan,
} from "./studyRequest";

const firstCombo = scheduleCombos(DEFAULT_OPERATIONAL_GRID)[0];
const firstFingerprint = comboFingerprint(firstCombo, 45);

function schedule(combo: ScheduleCombo, injectionDurationDays = 45) {
  return {
    ...combo,
    injection_reference_pressure_bar: 1.01325,
    injection_reference_temperature_c: 15,
    injection_duration_days: injectionDurationDays,
  };
}

function runtime(
  nativeCombo: ScheduleCombo = firstCombo,
  bank: Array<{ combo: ScheduleCombo; injectionDurationDays?: number }> = [],
): ReservoirImportResponse {
  const nativeSchedule = schedule(nativeCombo);
  const nativeFingerprint = comboFingerprint(nativeCombo, 45);
  const bankSeeds = Object.fromEntries(
    bank.map(({ combo, injectionDurationDays = 45 }) => {
      const fingerprint = comboFingerprint(combo, injectionDurationDays);
      return [fingerprint, { schedule_fingerprint: fingerprint, source_id: fingerprint }];
    }),
  );
  return {
    model_id: "model-abc",
    sha256: "A".repeat(64),
    source_file: "case_0016.mat",
    geology: { length_x_m: 900, length_y_m: 600, thickness_m: 6 },
    native_schedule: nativeSchedule,
    native_fingerprint: nativeFingerprint,
    native_seed: {
      schedule_fingerprint: nativeFingerprint,
      source_id: "native",
    },
    bank_seeds: bankSeeds,
    well_ij: [30, 36],
    completion_ij: [[30, 36]],
    launchpads: {
      bank_id: bank.length ? "bank-abc" : null,
      bank_sha256: bank.length ? "B".repeat(64) : null,
      covered_fingerprints: [nativeFingerprint, ...Object.keys(bankSeeds)].sort(),
    },
  };
}

function field(imported: ReservoirImportResponse): FieldSetupMemo {
  return {
    terrain: {
      terrain_id: "terrain-abc",
      sha256: "T".repeat(64),
      source_path: "C:/terrain.tif",
      extent: { minLon: 107, minLat: -7, maxLon: 108, maxLat: -6 },
    },
    reservoir: {
      model_id: imported.model_id,
      sha256: imported.sha256,
      source_file: imported.source_file,
      native_fingerprint: imported.native_fingerprint,
      covered_fingerprints: imported.launchpads.covered_fingerprints,
      bank_id: imported.launchpads.bank_id,
      bank_sha256: imported.launchpads.bank_sha256,
      well_ij: imported.well_ij,
      length_x_m: 900,
      length_y_m: 600,
    },
    placement: {
      name: "Imported field",
      center_lat: -6.5,
      center_lon: 107.7,
      rotation_deg: 18,
    },
    wells: [
      { id: "W01", name: "Native", kind: "native", lat: -6.5, lon: 107.7 },
      { id: "W02", name: "North", kind: "placed", lat: -6.49, lon: 107.71 },
    ],
    sources: [
      {
        id: "S01",
        name: "Plant",
        lat: -6.55,
        lon: 107.65,
        annual_capacity_t: 500_000,
        outlet_pressure_bar: 120,
        outlet_temperature_c: 27,
        co2_purity: 0.95,
        max_mass_flow_kg_s: 600,
      },
    ],
  };
}

describe("buildStudyRequest", () => {
  it("rejects source coordinates outside the API contract", () => {
    const imported = runtime();
    const setup = field(imported);
    setup.sources[0].lat = 90.01;

    expect(sourceValidationIssue(setup.sources)).toMatch(/invalid location/i);
  });

  it("builds a full editable inline draft from the placed field", () => {
    const imported = runtime();
    const request = buildStudyRequest({
      field: field(imported),
      imported,
      base: createDefaultStudyRequestBase(),
      scheduleMode: "grid",
    });

    expect(request).toMatchObject({
      mode: "inline",
      terrain_id: "terrain-abc",
      operational_grid: DEFAULT_OPERATIONAL_GRID,
      schedules: null,
    });
    expect(Object.keys(request.geologies)).toEqual(["model-abc"]);
    expect(Object.keys(request.seeds)).toHaveLength(1);
    expect(request.candidates).toHaveLength(2);
    expect(request.candidates[0]).toMatchObject({
      candidate_id: "W01",
      geology_id: "model-abc",
      location: { latitude: -6.5, longitude: 107.7 },
      seed_by_schedule_fingerprint: {
        [firstFingerprint]: `launchpad:model-abc:${firstFingerprint}`,
      },
      produced_co2: {
        mole_fraction: 0.65,
        provenance: { source_class: "engineering_assumption" },
      },
    });
    expect(request.sources[0]).toEqual({
      id: "S01",
      name: "Plant",
      location: { latitude: -6.55, longitude: 107.65 },
      capacity_tonnes_per_year: 500_000,
      max_mass_flow_kg_s: 600,
      outlet_pressure_bar: 120,
      outlet_temperature_c: 27,
      co2_purity: 0.95,
    });
  });

  it("submits only the grid schedules with matching launch pads", () => {
    const combos = scheduleCombos(DEFAULT_OPERATIONAL_GRID);
    const imported = runtime(firstCombo, [{ combo: combos[1] }]);
    const request = buildStudyRequest({
      field: field(imported),
      imported,
      base: createDefaultStudyRequestBase(),
    });

    expect(request.operational_grid).toBeNull();
    expect(request.schedules).toEqual([schedule(combos[0]), schedule(combos[1])]);
  });

  it("maps distinct per-well geologies and submits only common bank coverage", () => {
    const combos = scheduleCombos(DEFAULT_OPERATIONAL_GRID);
    const primary = runtime(firstCombo, [{ combo: combos[1] }]);
    const secondary = {
      ...runtime(combos[2], [{ combo: combos[1] }]),
      model_id: "model-def",
      sha256: "D".repeat(64),
      source_file: "case_0021.reservoir.npz",
      geology: { length_x_m: 880, length_y_m: 620, thickness_m: 7 },
    } satisfies ReservoirImportResponse;

    const request = buildStudyRequest({
      field: field(primary),
      imported: primary,
      importedByWell: { W01: primary, W02: secondary },
      base: createDefaultStudyRequestBase(),
      scheduleMode: "covered",
    });

    expect(Object.keys(request.geologies).sort()).toEqual(["model-abc", "model-def"]);
    const candidates = request.candidates as Array<{
      candidate_id: string;
      geology_id: string;
    }>;
    expect(candidates.map((item) => [item.candidate_id, item.geology_id])).toEqual([
      ["W01", "model-abc"],
      ["W02", "model-def"],
    ]);
    expect(request.operational_grid).toBeNull();
    expect(request.schedules).toEqual([schedule(combos[1])]);
    expect(Object.keys(request.seeds)).toContain(
      `launchpad:model-def:${comboFingerprint(combos[1], 45)}`,
    );
  });

  it("reports zero grid coverage and runs the real off-grid native schedule", () => {
    const native = {
      injection_rate_m3_day: 8687.177439504216,
      soak_duration_days: 28.126672556861426,
      production_duration_days: 199.0340798188366,
      production_bhp_psi: 669.0069852265157,
      cycles: 4,
    };
    const imported = runtime(native);
    const plan = studySchedulePlan(DEFAULT_OPERATIONAL_GRID, imported);
    const request = buildStudyRequest({
      field: field(imported),
      imported,
      base: createDefaultStudyRequestBase(),
    });

    expect(plan.coverage).toMatchObject({ covered: 0, total: 162 });
    expect(plan.native).toMatchObject({ available: true, onGrid: false });
    expect(plan.usesNativeFallback).toBe(true);
    expect(request.operational_grid).toBeNull();
    expect(request.schedules).toEqual([schedule(native)]);
  });

  it("rebuilds an artifact-referenced memo from its covered explicit schedules", () => {
    const combos = scheduleCombos(DEFAULT_OPERATIONAL_GRID);
    const imported = runtime(firstCombo, [{ combo: combos[1] }]);
    const base = createDefaultStudyRequestBase();
    base.operational_grid = null;
    base.schedules = [schedule(combos[0]), schedule(combos[1]), schedule(combos[2])];

    const request = buildStudyRequest({
      field: field(imported),
      imported,
      base,
      scheduleMode: "covered",
    });

    expect(request.operational_grid).toBeNull();
    expect(request.schedules).toEqual([schedule(combos[0]), schedule(combos[1])]);
  });

  it("carries the optional road-network reference into the request", () => {
    const imported = runtime();
    const withRoads = field(imported);
    withRoads.roads = {
      road_network_id: "roads-a",
      sha256: "R".repeat(64),
      source_path: "C:/java.osm.pbf",
    };

    const routed = buildStudyRequest({
      field: withRoads,
      imported,
      base: createDefaultStudyRequestBase(),
      scheduleMode: "grid",
    });
    const estimated = buildStudyRequest({
      field: { ...withRoads, roads: null },
      imported,
      base: createDefaultStudyRequestBase(),
      scheduleMode: "grid",
    });

    expect(routed.road_network_id).toBe("roads-a");
    expect(estimated.road_network_id).toBeNull();
  });
});
