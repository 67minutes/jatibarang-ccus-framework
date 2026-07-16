import type { PredictionResult } from "../api/types";
import type { PlumeFrame } from "./grid";

/**
 * Reservoir-field frames for the extruded grid. Real detailed predictions carry
 * per-cell spatial fields; the demo (which correctly selects no wells, so has no
 * detailed predictions) falls back to a bundled real single-well plume preview.
 */

export interface PlumeAnimation {
  scenario_id: string;
  width: number;
  height: number;
  stepIndices: number[];
  frames: PlumeFrame[];
}

let demoCache: Promise<PlumeAnimation | null> | null = null;

export function loadDemoPlume(): Promise<PlumeAnimation | null> {
  if (!demoCache) {
    demoCache = fetch("/assets/demo-plume.json")
      .then((r) => (r.ok ? (r.json() as Promise<PlumeAnimation>) : null))
      .catch(() => null);
  }
  return demoCache;
}

/** Convert a detailed prediction's spatial fields into plume frames. */
export function framesFromPrediction(prediction: PredictionResult): PlumeFrame[] {
  if (!prediction.fields) return [];
  return prediction.fields.map((f) => ({
    step_index: f.step_index,
    z_co2: f.z_co2.values,
    gas_saturation: f.gas_saturation.values,
    pressure_bar: f.pressure_bar.values,
    oil_saturation: f.oil_saturation?.values,
  }));
}

/** Clamp a timeline step to the available frame range. */
export function frameAtStep(frames: PlumeFrame[], step: number): PlumeFrame | null {
  if (frames.length === 0) return null;
  const idx = Math.max(0, Math.min(frames.length - 1, step));
  return frames[idx];
}
