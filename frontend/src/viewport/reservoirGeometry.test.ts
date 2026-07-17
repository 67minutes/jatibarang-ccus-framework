import { describe, expect, it } from "vitest";
import {
  RESERVOIR_NX,
  RESERVOIR_NY,
  VERTICES_PER_CELL,
  buildReservoirMesh,
  cellCentersToNodes,
  dynamicValues,
  staticColors,
  type PhysicalGrid,
} from "./reservoirGeometry";

const grid: PhysicalGrid = {
  nx: RESERVOIR_NX,
  ny: RESERVOIR_NY,
  nz: 1,
  length_x_m: 900,
  length_y_m: 600,
  thickness_m: 6,
};

describe("reservoir physical geometry", () => {
  it("preserves the 900 by 600 by 6 metre single-layer volume", () => {
    const structure = new Float32Array(RESERVOIR_NX * RESERVOIR_NY);
    const colours = staticColors(new Float32Array(structure.length).fill(100), "permeability_md");
    const mesh = buildReservoirMesh(grid, structure, colours);
    expect(mesh.positions).toHaveLength(structure.length * VERTICES_PER_CELL * 3);
    const x: number[] = [];
    const y: number[] = [];
    const z: number[] = [];
    for (let index = 0; index < mesh.positions.length; index += 3) {
      x.push(mesh.positions[index]);
      y.push(mesh.positions[index + 1]);
      z.push(mesh.positions[index + 2]);
    }
    const bounds = (values: number[]) =>
      values.reduce(
        ([minimum, maximum], value) => [Math.min(minimum, value), Math.max(maximum, value)],
        [Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY],
      );
    const [minX, maxX] = bounds(x);
    const [minY, maxY] = bounds(y);
    const [minZ, maxZ] = bounds(z);
    expect(minX).toBe(-450);
    expect(maxX).toBe(450);
    expect(minZ).toBe(-300);
    expect(maxZ).toBe(300);
    expect(maxY - minY).toBe(6);
  });

  it("averages cell-centred structure onto shared corner nodes", () => {
    const cells = new Float32Array(4);
    cells.set([0, 2, 4, 6]);
    const nodes = cellCentersToNodes(cells, 2, 2);
    expect(nodes).toHaveLength(9);
    expect(nodes[4]).toBeCloseTo(3);
    expect(nodes[0]).toBe(0);
    expect(nodes[8]).toBe(6);
  });

  it("uses log permeability colours and keeps equal values identical", () => {
    const colours = staticColors(Float32Array.from([10, 100, 100, 1000]), "permeability_md");
    expect(Array.from(colours.slice(3, 6))).toEqual(Array.from(colours.slice(6, 9)));
    expect(Array.from(colours.slice(0, 3))).not.toEqual(Array.from(colours.slice(9, 12)));
  });

  it("derives pressure change and oil depletion from a baseline", () => {
    expect(Array.from(dynamicValues("pressure_bar", [102, 99], [100, 100]))).toEqual([2, -1]);
    const depletion = dynamicValues("oil_saturation", [0.5, 0.7], [0.8, 0.8]);
    expect(depletion[0]).toBeCloseTo(0.3);
    expect(depletion[1]).toBeCloseTo(0.1);
  });
});
