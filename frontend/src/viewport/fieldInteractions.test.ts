import { describe, expect, it } from "vitest";
import type { FieldPlacement, ReservoirRef } from "../state/field.store";
import { pointInField } from "./FieldOutline";
import { makeProjector, xzToCoordinate, type TerrainData } from "./terrain";

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
