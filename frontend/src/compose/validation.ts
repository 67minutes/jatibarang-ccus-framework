import type {
  CarbonPriceScenario,
  FiscalCaseLite,
  InlineScreenRequest,
  OperationalGrid,
} from "../api/types";

/**
 * Client-side mirror of the backend `InlineScreenRequest` validators
 * (screening/schemas.py). Catches the same 422 conditions before submission and
 * previews the logical scenario count. Trained-range checks reproduce the
 * promoted checkpoint's envelope so out-of-range sweeps flag amber up front;
 * the backend remains the source of truth and returns authoritative
 * extrapolation flags in the result.
 */

export interface FieldIssue {
  field: string;
  message: string;
}

export interface ValidationReport {
  errors: FieldIssue[];
  warnings: FieldIssue[];
  /** candidates x schedules — the surrogate scenario count. */
  scenarioCount: number;
  scheduleCount: number;
  valid: boolean;
}

/**
 * Promoted-checkpoint trained envelope (from the normalization stats the
 * backend ships). Used only to warn; not authoritative.
 */
export const TRAINED_RANGES = {
  injection_rate_m3_day_max: 9982.28,
  production_bhp_psi_max: 699.64,
  cycles_max: 4,
  anisotropy_ratio_max: 2.99,
};

export function readCarbonPrices(
  draft: Pick<InlineScreenRequest, "carbon_prices">,
): CarbonPriceScenario[] {
  return (draft.carbon_prices as CarbonPriceScenario[]).filter(
    (p) => p && typeof p === "object" && "scenario_id" in p,
  );
}

export function readFiscalCases(
  draft: Pick<InlineScreenRequest, "fiscal_cases">,
): FiscalCaseLite[] {
  return (draft.fiscal_cases as FiscalCaseLite[]).filter(
    (f) => f && typeof f === "object" && "case_id" in f,
  );
}

function gridScheduleCount(grid: OperationalGrid): number {
  return (
    grid.injection_rate_m3_day.length *
    grid.injection_duration_days.length *
    grid.soak_duration_days.length *
    grid.production_duration_days.length *
    grid.production_bhp_psi.length *
    grid.cycles.length
  );
}

function uniqueCount<T>(values: T[]): boolean {
  return new Set(values).size === values.length;
}

export function validateDraft(draft: InlineScreenRequest | null): ValidationReport {
  const errors: FieldIssue[] = [];
  const warnings: FieldIssue[] = [];

  if (!draft) {
    return { errors: [], warnings: [], scenarioCount: 0, scheduleCount: 0, valid: false };
  }

  // Exactly one of operational_grid / schedules.
  const hasGrid = draft.operational_grid != null;
  const hasSchedules = draft.schedules != null;
  if (hasGrid === hasSchedules) {
    errors.push({
      field: "operational_grid",
      message: "Provide exactly one of an operational grid or an explicit schedule list.",
    });
  }

  const scheduleCount = hasGrid
    ? gridScheduleCount(draft.operational_grid as OperationalGrid)
    : (draft.schedules?.length ?? 0);

  const candidateCount = draft.candidates.length;
  if (candidateCount < 1) errors.push({ field: "candidates", message: "At least one candidate well is required." });
  if (candidateCount > 20) errors.push({ field: "candidates", message: "At most 20 candidate wells are allowed." });

  const candidateIds = draft.candidates
    .map((c) => (c && typeof c === "object" ? (c as { candidate_id?: string }).candidate_id : undefined))
    .filter((id): id is string => typeof id === "string");
  if (!uniqueCount(candidateIds)) errors.push({ field: "candidates", message: "Candidate IDs must be unique." });

  if (!uniqueCount(draft.sources.map((s) => s.id))) {
    errors.push({ field: "sources", message: "Source IDs must be unique." });
  }

  const prices = readCarbonPrices(draft);
  if (prices.length < 4) {
    errors.push({ field: "carbon_prices", message: "At least four carbon-price scenarios are required." });
  }
  if (!uniqueCount(prices.map((p) => p.scenario_id))) {
    errors.push({ field: "carbon_prices", message: "Carbon-price scenario IDs must be unique." });
  }

  const fiscal = readFiscalCases(draft);
  if (!uniqueCount(fiscal.map((f) => f.case_id))) {
    errors.push({ field: "fiscal_cases", message: "Fiscal case IDs must be unique." });
  }
  const selectionId = draft.selection_fiscal_case_id ?? "pre_tax";
  const selectionCase = fiscal.find((f) => f.case_id === selectionId);
  if (!selectionCase) {
    errors.push({
      field: "selection_fiscal_case_id",
      message: `Selection fiscal case "${selectionId}" must be one of the fiscal cases.`,
    });
  } else if (selectionCase.mode !== "pre_tax") {
    errors.push({
      field: "selection_fiscal_case_id",
      message: "Pipeline selection must use a pre-tax fiscal case.",
    });
  }

  if (!(draft.annual_co2_budget_tonnes > 0)) {
    errors.push({ field: "annual_co2_budget_tonnes", message: "Annual CO₂ budget must be positive." });
  }

  const economic = draft.economic_assumptions;
  if ("oil_price_usd_per_bbl" in economic) {
    const oilPrice = Number(economic.oil_price_usd_per_bbl);
    const oilPriceMax = Number(economic.oil_price_max_usd_per_bbl ?? 500);
    if (!Number.isFinite(oilPrice) || oilPrice < 0 || oilPrice > oilPriceMax) {
      errors.push({
        field: "economic_assumptions.oil_price_usd_per_bbl",
        message: `Oil price must be between 0 and ${oilPriceMax} USD/bbl.`,
      });
    }
  }
  if ("lifting_cost_usd_per_bbl" in economic) {
    const liftingCost = Number(economic.lifting_cost_usd_per_bbl);
    if (!Number.isFinite(liftingCost) || liftingCost < 0) {
      errors.push({
        field: "economic_assumptions.lifting_cost_usd_per_bbl",
        message: "Lifting cost must be non-negative.",
      });
    }
  }
  if ("discount_rate" in economic) {
    const discountRate = Number(economic.discount_rate);
    if (!Number.isFinite(discountRate) || discountRate < 0 || discountRate > 1) {
      errors.push({
        field: "economic_assumptions.discount_rate",
        message: "Discount rate must be between 0% and 100%.",
      });
    }
  }

  // Trained-range warnings (amber).
  if (hasGrid) {
    const grid = draft.operational_grid as OperationalGrid;
    if (Math.max(...grid.injection_rate_m3_day) > TRAINED_RANGES.injection_rate_m3_day_max) {
      warnings.push({
        field: "operational_grid.injection_rate_m3_day",
        message: `Injection rate exceeds the trained envelope (${TRAINED_RANGES.injection_rate_m3_day_max} m³/day); results will carry a low-confidence flag.`,
      });
    }
    if (Math.max(...grid.production_bhp_psi) > TRAINED_RANGES.production_bhp_psi_max) {
      warnings.push({
        field: "operational_grid.production_bhp_psi",
        message: `Production BHP exceeds the trained envelope (${TRAINED_RANGES.production_bhp_psi_max} psi); results will carry a low-confidence flag.`,
      });
    }
    if (Math.max(...grid.cycles) > TRAINED_RANGES.cycles_max) {
      warnings.push({
        field: "operational_grid.cycles",
        message: `Cycle count exceeds the trained maximum (${TRAINED_RANGES.cycles_max}); results are extended-horizon.`,
      });
    }
    for (const [name, values] of Object.entries(grid) as [string, number[]][]) {
      if (!uniqueCount(values)) errors.push({ field: `operational_grid.${name}`, message: `${name} levels must be unique.` });
      if (values.some((v) => v <= 0)) errors.push({ field: `operational_grid.${name}`, message: `${name} levels must be positive.` });
    }
  }

  const scenarioCount = candidateCount * scheduleCount;
  if (scenarioCount > 4096) {
    warnings.push({
      field: "scenario_limit",
      message: `Logical scenario count (${scenarioCount}) exceeds 4096 and will be capped by scenario_limit.`,
    });
  }

  return {
    errors,
    warnings,
    scenarioCount,
    scheduleCount,
    valid: errors.length === 0,
  };
}
