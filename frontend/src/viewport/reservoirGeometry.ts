/**
 * Pure geometry and colour encoders for the simulator-style reservoir view.
 * Geometry is expressed in physical metres. The React/three layer applies one
 * horizontal scene scale and an explicitly labelled vertical exaggeration.
 */

export const RESERVOIR_NX = 64;
export const RESERVOIR_NY = 64;
export const TRIANGLES_PER_CELL = 12;
export const VERTICES_PER_CELL = TRIANGLES_PER_CELL * 3;

export type StaticReservoirField = "permeability_md" | "porosity_fraction" | "facies";
export type DynamicReservoirField =
  | "z_co2"
  | "gas_saturation"
  | "pressure_bar"
  | "oil_saturation";

export interface PhysicalGrid {
  nx: number;
  ny: number;
  nz: number;
  length_x_m: number;
  length_y_m: number;
  thickness_m: number;
}

export interface MeshArrays {
  positions: Float32Array;
  colors: Float32Array;
  cellCount: number;
  trianglesPerCell: number;
}

export interface LineArrays {
  positions: Float32Array;
}

type RGB = [number, number, number];
type Stop = [number, RGB];

const VIRIDIS: Stop[] = [
  [0, [0.267, 0.005, 0.329]],
  [0.25, [0.23, 0.322, 0.546]],
  [0.5, [0.128, 0.567, 0.551]],
  [0.75, [0.369, 0.789, 0.383]],
  [1, [0.993, 0.906, 0.144]],
];

const POROSITY: Stop[] = [
  [0, [0.08, 0.13, 0.17]],
  [0.35, [0.15, 0.35, 0.43]],
  [0.7, [0.44, 0.68, 0.62]],
  [1, [0.91, 0.84, 0.55]],
];

const PRESSURE: Stop[] = [
  [0, [0.16, 0.07, 0.08]],
  [0.3, [0.54, 0.12, 0.1]],
  [0.65, [0.93, 0.36, 0.12]],
  [1, [1, 0.82, 0.32]],
];

const SATURATION: Stop[] = [
  [0, [0.87, 0.94, 0.93]],
  [0.3, [0.5, 0.78, 0.75]],
  [0.65, [0.15, 0.55, 0.53]],
  [1, [0.04, 0.25, 0.25]],
];

const OIL_DEPLETION: Stop[] = [
  [0, [0.92, 0.9, 0.83]],
  [0.4, [0.68, 0.55, 0.28]],
  [0.75, [0.47, 0.25, 0.16]],
  [1, [0.24, 0.09, 0.11]],
];

const FACIES: Record<number, RGB> = {
  1: [0.28, 0.3, 0.32],
  2: [0.56, 0.46, 0.3],
  3: [0.27, 0.52, 0.48],
};

export function finiteRange(values: ArrayLike<number>, transform: (value: number) => number = (v) => v): [number, number] {
  let lo = Number.POSITIVE_INFINITY;
  let hi = Number.NEGATIVE_INFINITY;
  for (let index = 0; index < values.length; index++) {
    const value = transform(values[index]);
    if (!Number.isFinite(value)) continue;
    lo = Math.min(lo, value);
    hi = Math.max(hi, value);
  }
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return [0, 1];
  if (Math.abs(hi - lo) < 1e-12) return [lo, lo + 1];
  return [lo, hi];
}

export function sampleStops(normalized: number, stops: Stop[]): RGB {
  const value = Math.max(0, Math.min(1, normalized));
  for (let index = 1; index < stops.length; index++) {
    if (value > stops[index][0]) continue;
    const [loT, lo] = stops[index - 1];
    const [hiT, hi] = stops[index];
    const mix = (value - loT) / Math.max(1e-12, hiT - loT);
    return [
      lo[0] + (hi[0] - lo[0]) * mix,
      lo[1] + (hi[1] - lo[1]) * mix,
      lo[2] + (hi[2] - lo[2]) * mix,
    ];
  }
  return stops[stops.length - 1][1];
}

/** Average adjacent cell-centred structure values onto the (nx+1)x(ny+1) nodes. */
export function cellCentersToNodes(values: ArrayLike<number>, nx = RESERVOIR_NX, ny = RESERVOIR_NY): Float32Array {
  if (values.length !== nx * ny) {
    throw new Error(`structure grid must contain ${nx * ny} cells`);
  }
  const nodes = new Float32Array((nx + 1) * (ny + 1));
  for (let j = 0; j <= ny; j++) {
    for (let i = 0; i <= nx; i++) {
      let total = 0;
      let count = 0;
      for (let dj = -1; dj <= 0; dj++) {
        for (let di = -1; di <= 0; di++) {
          const ci = i + di;
          const cj = j + dj;
          if (ci < 0 || ci >= nx || cj < 0 || cj >= ny) continue;
          total += values[cj * nx + ci];
          count++;
        }
      }
      nodes[j * (nx + 1) + i] = total / Math.max(1, count);
    }
  }
  return nodes;
}

export function staticColors(
  values: ArrayLike<number>,
  field: StaticReservoirField,
  range?: [number, number],
): Float32Array {
  const transform = field === "permeability_md" ? (value: number) => Math.log10(Math.max(value, 1e-6)) : (value: number) => value;
  const [minimum, maximum] = range ?? finiteRange(values, transform);
  const colors = new Float32Array(values.length * 3);
  for (let index = 0; index < values.length; index++) {
    const raw = values[index];
    const rgb = field === "facies"
      ? FACIES[Math.round(raw)] ?? [0.5, 0.5, 0.5]
      : sampleStops((transform(raw) - minimum) / Math.max(1e-12, maximum - minimum), field === "permeability_md" ? VIRIDIS : POROSITY);
    colors.set(rgb, index * 3);
  }
  return colors;
}

export function dynamicValues(
  field: DynamicReservoirField,
  current: ArrayLike<number>,
  baseline?: ArrayLike<number>,
): Float32Array {
  if (baseline && baseline.length !== current.length) throw new Error("baseline field shape differs from current field");
  const output = new Float32Array(current.length);
  for (let index = 0; index < current.length; index++) {
    if (field === "pressure_bar") output[index] = baseline ? current[index] - baseline[index] : current[index];
    else if (field === "oil_saturation") output[index] = baseline ? baseline[index] - current[index] : 0;
    else output[index] = current[index];
  }
  return output;
}

export function dynamicColors(values: ArrayLike<number>, field: DynamicReservoirField, range?: [number, number]): Float32Array {
  const [minimum, maximum] = range ?? finiteRange(values);
  const colors = new Float32Array(values.length * 3);
  const stops = field === "pressure_bar" ? PRESSURE : field === "oil_saturation" ? OIL_DEPLETION : SATURATION;
  for (let index = 0; index < values.length; index++) {
    colors.set(sampleStops((values[index] - minimum) / Math.max(1e-12, maximum - minimum), stops), index * 3);
  }
  return colors;
}

const CELL_TRIANGLES: ReadonlyArray<readonly [number, number, number]> = [
  [0, 2, 1], [1, 2, 3], // top
  [4, 5, 6], [5, 7, 6], // base
  [0, 1, 4], [1, 5, 4],
  [2, 6, 3], [3, 6, 7],
  [0, 4, 2], [2, 4, 6],
  [1, 3, 5], [3, 7, 5],
];

/** Build non-indexed hexahedra so a face index maps deterministically to a cell. */
export function buildReservoirMesh(
  grid: PhysicalGrid,
  structureCells: ArrayLike<number>,
  cellColors: ArrayLike<number>,
  includeCell?: (index: number) => boolean,
  topOnly = false,
): MeshArrays {
  const { nx, ny, length_x_m: lengthX, length_y_m: lengthY, thickness_m: thickness } = grid;
  if (grid.nz !== 1) throw new Error("current reservoir contract supports exactly one vertical layer");
  if (structureCells.length !== nx * ny) throw new Error("structure field does not match grid dimensions");
  if (cellColors.length !== nx * ny * 3) throw new Error("colour field does not match grid dimensions");
  const nodes = cellCentersToNodes(structureCells, nx, ny);
  const selected: number[] = [];
  for (let index = 0; index < nx * ny; index++) if (!includeCell || includeCell(index)) selected.push(index);
  const triangleCount = topOnly ? 2 : TRIANGLES_PER_CELL;
  const positions = new Float32Array(selected.length * triangleCount * 9);
  const colors = new Float32Array(positions.length);
  let cursor = 0;
  for (const index of selected) {
    const i = index % nx;
    const j = Math.floor(index / nx);
    const x0 = (i / nx - 0.5) * lengthX;
    const x1 = ((i + 1) / nx - 0.5) * lengthX;
    const z0 = (j / ny - 0.5) * lengthY;
    const z1 = ((j + 1) / ny - 0.5) * lengthY;
    const n00 = nodes[j * (nx + 1) + i];
    const n10 = nodes[j * (nx + 1) + i + 1];
    const n01 = nodes[(j + 1) * (nx + 1) + i];
    const n11 = nodes[(j + 1) * (nx + 1) + i + 1];
    const corners: ReadonlyArray<readonly [number, number, number]> = [
      [x0, n00, z0], [x1, n10, z0], [x0, n01, z1], [x1, n11, z1],
      [x0, n00 - thickness, z0], [x1, n10 - thickness, z0],
      [x0, n01 - thickness, z1], [x1, n11 - thickness, z1],
    ];
    for (const triangle of CELL_TRIANGLES.slice(0, triangleCount)) {
      for (const cornerIndex of triangle) {
        positions.set(corners[cornerIndex], cursor);
        colors[cursor] = cellColors[index * 3];
        colors[cursor + 1] = cellColors[index * 3 + 1];
        colors[cursor + 2] = cellColors[index * 3 + 2];
        cursor += 3;
      }
    }
  }
  return { positions, colors, cellCount: selected.length, trianglesPerCell: triangleCount };
}

export function buildReservoirGridLines(grid: PhysicalGrid, structureCells: ArrayLike<number>): LineArrays {
  const { nx, ny, length_x_m: lengthX, length_y_m: lengthY, thickness_m: thickness } = grid;
  const nodes = cellCentersToNodes(structureCells, nx, ny);
  const lines: number[] = [];
  const point = (i: number, j: number, offset = 0): [number, number, number] => [
    (i / nx - 0.5) * lengthX,
    nodes[j * (nx + 1) + i] - offset,
    (j / ny - 0.5) * lengthY,
  ];
  for (let j = 0; j <= ny; j++) {
    for (let i = 0; i < nx; i++) lines.push(...point(i, j), ...point(i + 1, j));
  }
  for (let i = 0; i <= nx; i++) {
    for (let j = 0; j < ny; j++) lines.push(...point(i, j), ...point(i, j + 1));
  }
  for (const [i, j] of [[0, 0], [nx, 0], [0, ny], [nx, ny]]) {
    lines.push(...point(i, j), ...point(i, j, thickness));
  }
  return { positions: Float32Array.from(lines) };
}

export function cellFromFaceIndex(faceIndex: number | undefined, trianglesPerCell = TRIANGLES_PER_CELL): number | null {
  return faceIndex == null || faceIndex < 0 ? null : Math.floor(faceIndex / trianglesPerCell);
}
