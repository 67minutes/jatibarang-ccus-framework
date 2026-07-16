import { describe, expect, it } from "vitest";
import type { InlineScreenRequest } from "../api/types";
import { TRAINED_RANGES, validateDraft } from "./validation";

function baseDraft(): InlineScreenRequest {
  return {
    mode: "inline",
    geologies: { G: {} },
    seeds: { S0: {} },
    candidates: [
      { candidate_id: "W01", location: { latitude: -6.48, longitude: 108.31 } },
      { candidate_id: "W02", location: { latitude: -6.47, longitude: 108.32 } },
    ],
    sources: [
      {
        id: "SRC",
        name: "s",
        location: { latitude: -6.49, longitude: 108.31 },
        capacity_tonnes_per_year: 1,
        max_mass_flow_kg_s: 1,
        outlet_pressure_bar: 120,
        outlet_temperature_c: 27,
        co2_purity: 0.95,
      },
    ],
    operational_grid: {
      injection_rate_m3_day: [9000],
      injection_duration_days: [45],
      soak_duration_days: [30],
      production_duration_days: [190],
      production_bhp_psi: [675],
      cycles: [3],
    },
    schedules: null,
    annual_co2_budget_tonnes: 320_000,
    carbon_prices: [
      { scenario_id: "a", carbon_price_usd_per_tonne: 4, source_type: "economic_assumption", provenance: [] },
      { scenario_id: "b", carbon_price_usd_per_tonne: 20, source_type: "economic_assumption", provenance: [] },
      { scenario_id: "c", carbon_price_usd_per_tonne: 40, source_type: "economic_assumption", provenance: [] },
      { scenario_id: "d", carbon_price_usd_per_tonne: 50, source_type: "economic_assumption", provenance: [] },
    ],
    fiscal_cases: [{ case_id: "pre_tax", mode: "pre_tax" }],
    economic_assumptions: {},
    selection_fiscal_case_id: "pre_tax",
  };
}

describe("validateDraft", () => {
  it("accepts a well-formed draft and previews the scenario count", () => {
    const r = validateDraft(baseDraft());
    expect(r.valid).toBe(true);
    expect(r.scheduleCount).toBe(1);
    expect(r.scenarioCount).toBe(2); // 2 candidates x 1 schedule
  });

  it("requires exactly one of grid or schedules", () => {
    const d = baseDraft();
    d.schedules = [{}];
    const r = validateDraft(d);
    expect(r.valid).toBe(false);
    expect(r.errors.some((e) => e.field === "operational_grid")).toBe(true);
  });

  it("requires at least four carbon prices", () => {
    const d = baseDraft();
    d.carbon_prices = d.carbon_prices.slice(0, 3);
    expect(validateDraft(d).valid).toBe(false);
  });

  it("rejects a non-pre-tax selection fiscal case", () => {
    const d = baseDraft();
    d.fiscal_cases = [{ case_id: "cr", mode: "cost_recovery" }];
    d.selection_fiscal_case_id = "cr";
    const r = validateDraft(d);
    expect(r.errors.some((e) => e.field === "selection_fiscal_case_id")).toBe(true);
  });

  it("flags out-of-trained-range injection rate as a warning, not an error", () => {
    const d = baseDraft();
    d.operational_grid!.injection_rate_m3_day = [TRAINED_RANGES.injection_rate_m3_day_max + 5000];
    const r = validateDraft(d);
    expect(r.valid).toBe(true);
    expect(r.warnings.some((w) => w.field.includes("injection_rate"))).toBe(true);
  });

  it("rejects duplicate and non-positive grid levels", () => {
    const d = baseDraft();
    d.operational_grid!.cycles = [3, 3];
    expect(validateDraft(d).errors.some((e) => e.field.includes("cycles"))).toBe(true);
    const d2 = baseDraft();
    d2.operational_grid!.soak_duration_days = [-1];
    expect(validateDraft(d2).errors.some((e) => e.field.includes("soak"))).toBe(true);
  });

  it("rejects duplicate candidate ids", () => {
    const d = baseDraft();
    d.candidates = [d.candidates[0], d.candidates[0]];
    expect(validateDraft(d).valid).toBe(false);
  });
});
