/**
 * Pure encoding of a 64×64 reservoir field into instanced-prism attributes for
 * the SECARB-style extruded grid (design §5.1). Height encodes one per-cell
 * field, color encodes another in DISCRETE bins (never a continuous gradient).
 * Kept free of three.js so it is unit-testable.
 */

export const GRID_N = 64;

export interface PlumeFrame {
  step_index: number;
  z_co2?: number[];
  gas_saturation?: number[];
  pressure_bar?: number[];
  oil_saturation?: number[];
}

export type PlumeField = "z_co2" | "gas_saturation" | "pressure_bar" | "oil_saturation";

/** Discrete color bins (dark→green→yellow→orange→red), SECARB-style. */
export interface Bin {
  max: number; // upper bound of the normalized value for this bin
  rgb: [number, number, number];
}

export const FRACTION_BINS: Bin[] = [
  { max: 0.05, rgb: [0.35, 0.38, 0.42] }, // ~background
  { max: 0.15, rgb: [0.18, 0.56, 0.3] }, // green
  { max: 0.3, rgb: [0.58, 0.72, 0.23] }, // yellow-green
  { max: 0.45, rgb: [0.85, 0.54, 0.17] }, // orange
  { max: Infinity, rgb: [0.76, 0.23, 0.18] }, // red
];

/** Normalization maxima per field (fields are physical, not pre-normalized). */
export const FIELD_MAX: Record<PlumeField, number> = {
  z_co2: 0.5,
  gas_saturation: 0.5,
  pressure_bar: 120,
  oil_saturation: 1,
};

export interface GridInstances {
  count: number;
  /** Cell centers in the local plane: [x, height/2, z] per instance. */
  positions: Float32Array;
  /** Per-instance extruded height (y scale). */
  heights: Float32Array;
  /** Per-instance rgb color. */
  colors: Float32Array;
  cellSize: number;
}

export interface GridEncodeOptions {
  heightField: PlumeField;
  colorField: PlumeField;
  /** Footprint of the whole grid in scene units. */
  footprint?: number;
  /** Maximum extruded height in scene units. */
  maxHeight?: number;
}

function fieldValues(frame: PlumeFrame, field: PlumeField): number[] | undefined {
  return frame[field];
}

export function binColor(normalized: number, bins: Bin[] = FRACTION_BINS): [number, number, number] {
  for (const bin of bins) {
    if (normalized <= bin.max) return bin.rgb;
  }
  return bins[bins.length - 1].rgb;
}

/**
 * Encode a frame into instance attributes. Cells are laid out on the XZ plane
 * centered on the origin; height grows in +Y.
 */
export function gridToInstances(
  frame: PlumeFrame,
  opts: GridEncodeOptions,
): GridInstances {
  const footprint = opts.footprint ?? 6;
  const maxHeight = opts.maxHeight ?? 3;
  const heightVals = fieldValues(frame, opts.heightField);
  const colorVals = fieldValues(frame, opts.colorField) ?? heightVals;
  const count = GRID_N * GRID_N;
  const positions = new Float32Array(count * 3);
  const heights = new Float32Array(count);
  const colors = new Float32Array(count * 3);
  const cellSize = footprint / GRID_N;
  const hMax = FIELD_MAX[opts.heightField];
  const cMax = FIELD_MAX[opts.colorField];

  for (let j = 0; j < GRID_N; j++) {
    for (let i = 0; i < GRID_N; i++) {
      const k = j * GRID_N + i;
      const hv = heightVals ? heightVals[k] : 0;
      const cv = colorVals ? colorVals[k] : 0;
      const hNorm = Math.max(0, Math.min(1, hv / hMax));
      const cNorm = Math.max(0, Math.min(1, cv / cMax));
      const height = Math.max(0.01, hNorm * maxHeight);
      const x = (i - GRID_N / 2 + 0.5) * cellSize;
      const z = (j - GRID_N / 2 + 0.5) * cellSize;
      positions[k * 3] = x;
      positions[k * 3 + 1] = height / 2;
      positions[k * 3 + 2] = z;
      heights[k] = height;
      const [r, g, b] = binColor(cNorm);
      colors[k * 3] = r;
      colors[k * 3 + 1] = g;
      colors[k * 3 + 2] = b;
    }
  }
  return { count, positions, heights, colors, cellSize };
}
