import { beforeEach, describe, expect, it } from "vitest";
import type { ReservoirImportResponse } from "../api/client";
import type { InlineScreenRequest } from "../api/types";
import { createDefaultStudyRequestBase } from "../compose/defaults";
import { buildStudyRequest } from "../compose/studyRequest";
import type { FieldSetupMemo } from "../memo/studyMemo";
import { useFieldStore } from "../state/field.store";
import { prepareScreeningRequest } from "./useWorkbench";

const NATIVE_FINGERPRINT =
  "E76B43C3F324821A90DCE393ACEEAB5FDF5C4AAF158639E2A37DCBDAC170E451";

function runtime(): ReservoirImportResponse {
  return {
    model_id: "case-0016",
    sha256: "A".repeat(64),
    source_file: "case_0016.mat",
    geology: { length_x_m: 900, length_y_m: 600, thickness_m: 6 },
    native_schedule: {
      injection_rate_m3_day: 8687.177439504216,
      injection_reference_pressure_bar: 1.01325,
      injection_reference_temperature_c: 15,
      injection_duration_days: 46.89706574654418,
      soak_duration_days: 28.126672556861426,
      production_duration_days: 199.0340798188366,
      production_bhp_psi: 669.0069852265157,
      cycles: 4,
    },
    native_fingerprint: NATIVE_FINGERPRINT,
    native_seed: {
      schedule_fingerprint: NATIVE_FINGERPRINT,
      source_id: "case-0016",
    },
    bank_seeds: {},
    well_ij: [30, 36],
    completion_ij: [[30, 36]],
    launchpads: {
      bank_id: null,
      bank_sha256: null,
      covered_fingerprints: [NATIVE_FINGERPRINT],
    },
  };
}

function field(imported: ReservoirImportResponse): FieldSetupMemo {
  return {
    terrain: {
      terrain_id: "terrain-one",
      sha256: "B".repeat(64),
      source_path: "terrain.tif",
      extent: { minLon: 107, maxLon: 108, minLat: -7, maxLat: -6 },
    },
    reservoir: {
      model_id: imported.model_id,
      sha256: imported.sha256,
      source_file: imported.source_file,
      native_fingerprint: imported.native_fingerprint,
      covered_fingerprints: [...imported.launchpads.covered_fingerprints],
      bank_id: null,
      well_ij: [...imported.well_ij],
      length_x_m: 900,
      length_y_m: 600,
    },
    placement: {
      name: "Field one",
      center_lat: -6.5,
      center_lon: 107.7,
      rotation_deg: 20,
    },
    wells: [
      { id: "W01", name: "Native", kind: "native", lat: -6.5, lon: 107.7 },
    ],
    sources: [],
  };
}

function installField(): {
  imported: ReservoirImportResponse;
  setup: FieldSetupMemo;
  draft: InlineScreenRequest;
} {
  const imported = runtime();
  const setup = field(imported);
  useFieldStore.getState().setup(
    setup.terrain,
    setup.reservoir,
    setup.placement,
    null,
    imported,
  );
  const draft = buildStudyRequest({
    field: setup,
    imported,
    base: createDefaultStudyRequestBase(),
    scheduleMode: "grid",
  });
  return { imported, setup, draft };
}

describe("prepareScreeningRequest", () => {
  beforeEach(() => useFieldStore.getState().reset());

  it("rebuilds candidates and sources from the latest field state", () => {
    const { draft } = installField();
    useFieldStore.getState().addWell(-6.49, 107.71);
    useFieldStore.getState().addSource({
      name: "Capture plant",
      lat: -6.55,
      lon: 107.65,
      annual_capacity_t: 500_000,
      outlet_pressure_bar: 120,
      outlet_temperature_c: 27,
      co2_purity: 0.98,
      max_mass_flow_kg_s: 600,
    });

    const prepared = prepareScreeningRequest(draft);
    expect(prepared.issue).toBeNull();
    expect(prepared.request?.candidates).toHaveLength(2);
    expect(prepared.request?.sources).toHaveLength(1);
    expect(prepared.request?.operational_grid).toBeNull();
    expect(prepared.request?.schedules).toHaveLength(1);
  });

  it("blocks a field with no CO2 source", () => {
    const { draft } = installField();
    expect(prepareScreeningRequest(draft)).toMatchObject({
      request: null,
      issue: { bannerId: "source-required" },
    });
  });

  it("blocks source values outside the backend pressure and purity bounds", () => {
    const { draft } = installField();
    useFieldStore.getState().addSource({
      name: "Invalid plant",
      lat: -6.55,
      lon: 107.65,
      annual_capacity_t: 500_000,
      outlet_pressure_bar: 79,
      outlet_temperature_c: 27,
      co2_purity: 0.94,
      max_mass_flow_kg_s: 600,
    });
    expect(prepareScreeningRequest(draft)).toMatchObject({
      request: null,
      issue: { bannerId: "source-invalid" },
    });
  });

  it("requires runtime relinking after a memo-style field hydration", () => {
    const { setup, draft } = installField();
    useFieldStore.getState().hydrate(setup);
    expect(prepareScreeningRequest(draft)).toMatchObject({
      request: null,
      issue: { bannerId: "reservoir-relink-required" },
    });
  });
});
