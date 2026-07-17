import type {
  CarbonPricePlan,
  PredictionResult,
  ScreenResult,
} from "../api/types";

const prediction = {
  scenario_id: "W01--FP01",
  production: {
    delta_oil_m3: [1, 2],
    delta_gas_m3: [0.5, 0.75],
    cumulative_oil_m3: [1, 3],
    cumulative_gas_m3: [0.5, 1.25],
  },
} as unknown as PredictionResult;

const lowPlan = {
  carbon_price_scenario_id: "cp_low",
  carbon_price_usd_per_tonne: 10,
  selected_wells: [],
  economics: null,
  well_strategies: [
    {
      candidate_id: "W01",
      scenario_id: prediction.scenario_id,
      preliminary_npv_usd: 12_000,
      pre_logistics_value_usd: 13_000,
      prediction,
    },
    {
      candidate_id: "W02",
      scenario_id: "W02--FP01",
      preliminary_npv_usd: 8_000,
      pre_logistics_value_usd: 9_000,
      prediction: { ...prediction, scenario_id: "W02--FP01" },
    },
  ],
} as unknown as CarbonPricePlan;

const highPlan = {
  ...lowPlan,
  carbon_price_scenario_id: "cp_high",
  carbon_price_usd_per_tonne: 40,
  selected_wells: ["W01"],
} as CarbonPricePlan;

/** Compact, deterministic result used only by pure frontend adapter tests. */
export const screenResultFixture = {
  plans: [lowPlan, highPlan],
  cross_price_comparison: {
    selection_by_carbon_price: { cp_low: [], cp_high: ["W01"] },
    transitions: [],
    pivot_observed: true,
  },
  detailed_predictions: { [prediction.scenario_id]: prediction },
  detailed_reservoirs: {
    [prediction.scenario_id]: {
      scenario_id: prediction.scenario_id,
      geology_id: "model-01",
    },
  },
} as unknown as ScreenResult;
