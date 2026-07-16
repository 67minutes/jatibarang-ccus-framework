import type {
  CarbonPricePlan,
  EconomicScenarioResult,
  ScreenResult,
} from "../api/types";

/**
 * Pure client-side pivot over an immutable ScreenResult (design §7.4). Moving
 * the carbon-price scrubber selects a plan and re-derives the KPIs, the
 * per-price selection set, and the scene coloring — with zero API calls.
 * These functions are unit-tested against a recorded result fixture.
 */

export interface PricePoint {
  scenarioId: string;
  price: number;
}

/** Carbon-price axis, ascending by price. */
export function carbonPriceAxis(result: ScreenResult): PricePoint[] {
  return result.plans
    .map((p) => ({ scenarioId: p.carbon_price_scenario_id, price: p.carbon_price_usd_per_tonne }))
    .sort((a, b) => a.price - b.price);
}

export function planForPrice(
  result: ScreenResult,
  scenarioId: string | null,
): CarbonPricePlan | null {
  if (result.plans.length === 0) return null;
  if (scenarioId) {
    const match = result.plans.find((p) => p.carbon_price_scenario_id === scenarioId);
    if (match) return match;
  }
  return result.plans[0];
}

/** Wells selected at a given carbon price, from the cross-price comparison. */
export function selectionAtPrice(result: ScreenResult, scenarioId: string): Set<string> {
  const wells = result.cross_price_comparison.selection_by_carbon_price[scenarioId];
  if (wells) return new Set(wells);
  const plan = result.plans.find((p) => p.carbon_price_scenario_id === scenarioId);
  return new Set(plan?.selected_wells ?? []);
}

/**
 * The portfolio economics for a plan under the selection fiscal case. Prefers
 * the result matching the plan's carbon price and the given fiscal case, then
 * falls back to the first available result.
 */
export function economicForPlan(
  plan: CarbonPricePlan,
  fiscalCaseId: string,
): EconomicScenarioResult | null {
  const results = plan.economics?.results ?? [];
  if (results.length === 0) return null;
  return (
    results.find(
      (r) =>
        r.carbon_price_scenario_id === plan.carbon_price_scenario_id &&
        r.fiscal_case_id === fiscalCaseId,
    ) ??
    results.find((r) => r.fiscal_case_id === fiscalCaseId) ??
    results[0]
  );
}

export interface KpiSummary {
  npv: number | null;
  npvLow: number | null;
  npvHigh: number | null;
  irr: number | null;
  breakEvenCarbon: number | null;
  breakEvenOil: number | null;
  netStored: number | null;
  lowConfidence: boolean;
  confidenceReasons: string[];
}

export function kpiSummary(econ: EconomicScenarioResult | null): KpiSummary {
  if (!econ) {
    return {
      npv: null,
      npvLow: null,
      npvHigh: null,
      irr: null,
      breakEvenCarbon: null,
      breakEvenOil: null,
      netStored: null,
      lowConfidence: false,
      confidenceReasons: [],
    };
  }
  return {
    npv: econ.npv_usd,
    npvLow: econ.npv_low_usd,
    npvHigh: econ.npv_high_usd,
    irr: econ.irr.status === "computed" ? econ.irr.value : null,
    breakEvenCarbon:
      econ.break_even_carbon_price.status === "computed"
        ? econ.break_even_carbon_price.value
        : null,
    breakEvenOil:
      econ.break_even_oil_price.status === "computed" ? econ.break_even_oil_price.value : null,
    netStored: econ.storage.primary_net_stored_co2_tonnes,
    lowConfidence: econ.low_confidence,
    confidenceReasons: econ.confidence_reasons,
  };
}
