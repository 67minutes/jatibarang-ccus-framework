import type {
  CellField,
  PredictionResult,
  ReservoirBaselineState,
} from "../api/types";

/**
 * Return only response fields that can be rendered with their declared
 * scientific encoding. Pressure and oil require the matching warm-start
 * baseline because the UI displays delta pressure and oil depletion.
 */
export function availablePredictionFields(
  prediction: PredictionResult | undefined,
  baseline?: ReservoirBaselineState | null,
): Set<CellField> {
  const fields = new Set<CellField>();
  for (const frame of prediction?.fields ?? []) {
    if (frame.z_co2) fields.add("z_co2");
    if (frame.gas_saturation) fields.add("gas_saturation");
    if (frame.pressure_bar && baseline?.pressure_bar) fields.add("pressure_bar");
    if (frame.oil_saturation && baseline?.oil_saturation) fields.add("oil_saturation");
  }
  return fields;
}
