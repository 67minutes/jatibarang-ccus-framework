import type { PredictionResult } from "../api/types";
import type { PlumeFrame } from "./grid";

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
