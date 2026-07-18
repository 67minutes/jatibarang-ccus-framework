import { describe, expect, it } from "vitest";
import { latLonToVec3 } from "./EarthGlobe";

describe("earth globe coordinates", () => {
  it("places the north pole on positive Y", () => {
    const point = latLonToVec3(90, 0, 10);
    expect(point[0]).toBeCloseTo(0);
    expect(point[1]).toBeCloseTo(10);
    expect(point[2]).toBeCloseTo(0);
  });

  it("keeps equatorial points on the requested radius", () => {
    const prime = latLonToVec3(0, 0, 10);
    const east = latLonToVec3(0, 90, 10);
    expect(prime[1]).toBeCloseTo(0);
    expect(Math.hypot(...prime)).toBeCloseTo(10);
    expect(prime[0] * east[0] + prime[1] * east[1] + prime[2] * east[2])
      .toBeCloseTo(0);
  });
});
