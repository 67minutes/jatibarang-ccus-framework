import { describe, expect, it } from "vitest";
import economicBasis from "../../../data/jatibarang/economic_basis.json";
import seedDesign from "../../../data/jatibarang/feature005_seed_design.json";
import {
  DEFAULT_CARBON_PRICES,
  DEFAULT_ECONOMIC_ASSUMPTIONS,
  DEFAULT_FISCAL_CASES,
  DEFAULT_OPERATIONAL_GRID,
  DEFAULT_STUDY_REQUEST_BASE,
  createDefaultStudyRequestBase,
} from "./defaults";

describe("study request defaults", () => {
  it("keeps carbon prices and fiscal scalar inputs aligned with the economic basis", () => {
    expect(
      DEFAULT_CARBON_PRICES.map((scenario) => ({
        scenario_id: scenario.scenario_id,
        carbon_price_usd_per_tonne: scenario.carbon_price_usd_per_tonne,
        source_type: scenario.source_type,
      })),
    ).toEqual(
      economicBasis.carbon_price_scenarios.map((scenario) => ({
        scenario_id: scenario.scenario_id,
        carbon_price_usd_per_tonne: scenario.carbon_price_usd_per_tonne,
        source_type: scenario.source_type,
      })),
    );

    expect(
      (DEFAULT_FISCAL_CASES as Array<Record<string, unknown>>).map(
        ({ provenance: _provenance, recoverable_cost_categories: _categories, ...fiscal }) =>
          fiscal,
      ),
    ).toEqual(economicBasis.fiscal_cases);
  });

  it("maps the economic basis and root bounds to the backend assumptions contract", () => {
    expect(DEFAULT_ECONOMIC_ASSUMPTIONS).toEqual({
      version: economicBasis.version,
      currency_basis: economicBasis.currency_basis,
      discount_rate: economicBasis.discount_rate,
      oil_price_usd_per_bbl: economicBasis.oil_price_usd_per_bbl,
      gas_price_usd_per_mmbtu: economicBasis.gas_price_usd_per_mmbtu,
      gas_heating_value_mmbtu_per_std_m3:
        economicBasis.gas_heating_value_mmbtu_per_std_m3,
      lifting_cost_usd_per_bbl: economicBasis.lifting_cost_usd_per_bbl,
      workover_cost_usd_per_cycle: economicBasis.workover_cost_usd_per_cycle,
      mrv_cost_usd_per_tonne: economicBasis.mrv_cost_usd_per_tonne,
      certification_haircut: economicBasis.certification_haircut,
      storage_divergence_threshold_fraction_of_injected:
        economicBasis.storage_divergence_threshold_fraction_of_injected,
      usd_reconciliation_tolerance: economicBasis.usd_reconciliation_tolerance,
      mass_reconciliation_tolerance_tonnes:
        economicBasis.mass_reconciliation_tolerance_tonnes,
      irr_min: economicBasis.root_bounds.irr_min,
      irr_max: economicBasis.root_bounds.irr_max,
      carbon_price_max_usd_per_tonne:
        economicBasis.root_bounds.carbon_price_max_usd_per_tonne,
      oil_price_max_usd_per_bbl: economicBasis.root_bounds.oil_price_max_usd_per_bbl,
      root_iterations: economicBasis.root_bounds.iterations,
    });
  });

  it("uses the exact Feature 005 grid and fixed injection duration", () => {
    expect(DEFAULT_OPERATIONAL_GRID).toEqual({
      ...seedDesign.grid,
      injection_duration_days: [seedDesign.fixed_injection_duration_days],
    });
    expect(
      Object.values(DEFAULT_OPERATIONAL_GRID).reduce(
        (count, levels) => count * levels.length,
        1,
      ),
    ).toBe(seedDesign.full_schedule_count);
  });

  it("returns a deep editable copy of the request base", () => {
    const copy = createDefaultStudyRequestBase();
    expect(copy).toEqual(DEFAULT_STUDY_REQUEST_BASE);
    expect(copy).not.toBe(DEFAULT_STUDY_REQUEST_BASE);
    expect(copy.operational_grid).not.toBe(DEFAULT_OPERATIONAL_GRID);
    expect(copy.carbon_prices).not.toBe(DEFAULT_CARBON_PRICES);
  });
});
