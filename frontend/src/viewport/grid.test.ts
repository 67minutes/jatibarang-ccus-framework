import { describe, expect, it } from "vitest";
import type { PlumeFrame } from "./grid";
import { binColor, FRACTION_BINS, GRID_N, gridToInstances } from "./grid";
import { readFixture } from "../test/fixture";

const realFrame = JSON.parse(readFixture("src/test/fixtures/plume_frame.json")) as PlumeFrame;

describe("grid encoding", () => {
  it("bins values into discrete colors, not a gradient", () => {
    // Two values in the same bin get the identical color.
    expect(binColor(0.06)).toEqual(binColor(0.14));
    // Values in different bins differ.
    expect(binColor(0.06)).not.toEqual(binColor(0.4));
    // Every bin is one of the defined swatches.
    for (const v of [0, 0.1, 0.2, 0.4, 0.9]) {
      expect(FRACTION_BINS.map((b) => b.rgb)).toContainEqual(binColor(v));
    }
  });

  it("produces one instance per cell with non-negative heights", () => {
    const inst = gridToInstances(realFrame, { heightField: "z_co2", colorField: "gas_saturation" });
    expect(inst.count).toBe(GRID_N * GRID_N);
    expect(inst.positions).toHaveLength(inst.count * 3);
    expect(inst.colors).toHaveLength(inst.count * 3);
    for (let k = 0; k < inst.count; k++) {
      expect(inst.heights[k]).toBeGreaterThan(0);
      // Cell center y is half the height (box sits on the plane).
      expect(inst.positions[k * 3 + 1]).toBeCloseTo(inst.heights[k] / 2, 5);
    }
  });

  it("reflects the real plume: some cells are elevated above background", () => {
    const inst = gridToInstances(realFrame, { heightField: "z_co2", colorField: "z_co2", maxHeight: 3 });
    const maxH = Math.max(...inst.heights);
    const minH = Math.min(...inst.heights);
    // The captured frame has a real plume, so heights span a range.
    expect(maxH).toBeGreaterThan(minH + 0.5);
  });

  it("lays cells out symmetrically about the origin", () => {
    const inst = gridToInstances(realFrame, { heightField: "z_co2", colorField: "z_co2", footprint: 6 });
    const xs = [];
    for (let k = 0; k < inst.count; k++) xs.push(inst.positions[k * 3]);
    expect(Math.min(...xs)).toBeCloseTo(-Math.max(...xs), 5);
  });
});
