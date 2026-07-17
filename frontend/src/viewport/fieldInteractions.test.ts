import { describe, expect, it } from "vitest";
import type { ReservoirImportResponse } from "../api/client";
import type { FieldPlacement, ReservoirRef } from "../state/field.store";
import { pointInField } from "./FieldOutline";
import { reservoirVisualizationFromImport } from "./ReservoirGrid";
import {
  fieldWindowBounds,
  makeProjector,
  xzToCoordinate,
  type TerrainData,
} from "./terrain";

const reservoir = {
  length_x_m: 900,
  length_y_m: 600,
} as ReservoirRef;

const placement: FieldPlacement = {
  name: "F",
  center_lat: -6.5,
  center_lon: 108,
  rotation_deg: 0,
};

describe("pointInField", () => {
  it("accepts the centre and rejects a point 1 km east", () => {
    expect(pointInField(-6.5, 108, placement, reservoir)).toBe(true);
    expect(pointInField(-6.5, 108.009, placement, reservoir)).toBe(false);
  });

  it("respects the placed field rotation", () => {
    const rotated = { ...placement, rotation_deg: 90 };
    expect(pointInField(-6.5, 108.0036, rotated, reservoir)).toBe(false);
    expect(pointInField(-6.4964, 108, rotated, reservoir)).toBe(true);
  });
});

describe("xzToCoordinate", () => {
  it("inverts the terrain projector", () => {
    const data: TerrainData = {
      width: 2,
      height: 2,
      extent: { minLon: 107, minLat: -7, maxLon: 109, maxLat: -6 },
      minElev: 0,
      maxElev: 1,
      elevations: [0, 0, 0, 0],
    };
    const projector = makeProjector(data);
    const coordinate = { latitude: -6.35, longitude: 108.4 };
    const [x, z] = projector.toXZ(coordinate);

    expect(xzToCoordinate(projector, x, z)).toEqual(
      expect.objectContaining({
        latitude: expect.closeTo(coordinate.latitude, 10),
        longitude: expect.closeTo(coordinate.longitude, 10),
      }),
    );
  });
});

describe("fieldWindowBounds", () => {
  it("pads the placed reservoir by three footprint widths in metres", () => {
    const bounds = fieldWindowBounds(
      { latitude: placement.center_lat, longitude: placement.center_lon },
      reservoir,
    );
    const northMetres = (bounds.maxLat - placement.center_lat) * 111_320;
    const eastMetres =
      (bounds.maxLon - placement.center_lon) *
      111_320 *
      Math.cos((placement.center_lat * Math.PI) / 180);

    expect(northMetres).toBeCloseTo(2_700, 6);
    expect(eastMetres).toBeCloseTo(2_700, 6);
    expect((bounds.minLat + bounds.maxLat) / 2).toBeCloseTo(
      placement.center_lat,
      12,
    );
    expect((bounds.minLon + bounds.maxLon) / 2).toBeCloseTo(
      placement.center_lon,
      12,
    );
  });
});

const grid = (value: number) => ({
  shape: [64, 64] as [number, number],
  values: Array.from({ length: 64 * 64 }, () => value),
});

function importedRuntime(): ReservoirImportResponse {
  return {
    model_id: "model-abc",
    sha256: "A".repeat(64),
    source_file: "case_0016.mat",
    geology: {
      permeability_md: grid(125),
      porosity_fraction: grid(0.18),
      structure_m: grid(0.5),
      fracture_proxy: grid(0.1),
      barrier: grid(0),
      facies: grid(2),
      well_mask: grid(0),
      completion_mask: grid(1),
      length_x_m: 900,
      length_y_m: 600,
      thickness_m: 6,
    },
    native_schedule: { injection_duration_days: 45 },
    native_fingerprint: "F".repeat(64),
    native_seed: {
      source_class: "mrst_ground_truth",
      source_id: "case_0016",
      frames: Array.from({ length: 8 }, (_, index) => ({
        pressure_bar: grid(100 + index),
        gas_saturation: grid(index / 100),
        z_co2: grid(index / 200),
      })),
    },
    bank_seeds: {},
    well_ij: [30, 36],
    completion_ij: [[30, 36]],
    launchpads: {
      bank_id: null,
      bank_sha256: null,
      covered_fingerprints: ["F".repeat(64)],
    },
  };
}

describe("reservoirVisualizationFromImport", () => {
  it("preserves imported MRST geometry and uses the final warm-start frame", () => {
    const visualization = reservoirVisualizationFromImport(importedRuntime());

    expect(visualization?.grid).toEqual({
      nx: 64,
      ny: 64,
      nz: 1,
      length_x_m: 900,
      length_y_m: 600,
      thickness_m: 6,
    });
    expect(visualization?.static_fields.permeability_md.values[0]).toBe(125);
    expect(visualization?.baseline_state?.pressure_bar.values[0]).toBe(107);
    expect(visualization?.provenance).toMatchObject({
      coordinate_reference: "local_proxy_grid",
      geometry_source_class: "mrst_derived_geology",
      baseline_frame_index: 7,
      surveyed_orientation: false,
    });
  });

  it("does not synthesize a reservoir when a required imported grid is absent", () => {
    const runtime = importedRuntime();
    delete runtime.geology.completion_mask;
    expect(reservoirVisualizationFromImport(runtime)).toBeNull();
  });
});
