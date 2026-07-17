import { describe, expect, it } from "vitest";
import type { PredictionResult, ReservoirBaselineState, SpatialFrame } from "../api/types";
import { availablePredictionFields } from "./fieldAvailability";

const grid = { shape: [64, 64] as [number, number], values: [0] };
const frame = {
  step_index: 0,
  origin: "surrogate",
  pressure_bar: grid,
  gas_saturation: grid,
  z_co2: grid,
  oil_saturation: grid,
} satisfies SpatialFrame;
const prediction = { fields: [frame] } as PredictionResult;
const baseline = {
  pressure_bar: grid,
  gas_saturation: grid,
  z_co2: grid,
  oil_saturation: null,
} satisfies ReservoirBaselineState;

describe("dynamic field availability", () => {
  it("requires the declared warm-start baseline for delta pressure and oil depletion", () => {
    const withoutBaseline = availablePredictionFields(prediction);
    expect(withoutBaseline).toEqual(new Set(["z_co2", "gas_saturation"]));

    const withPressureBaseline = availablePredictionFields(prediction, baseline);
    expect(withPressureBaseline).toEqual(new Set(["z_co2", "gas_saturation", "pressure_bar"]));
    expect(withPressureBaseline.has("oil_saturation")).toBe(false);
  });
});
