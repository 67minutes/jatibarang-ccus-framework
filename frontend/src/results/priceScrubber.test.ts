import { describe, expect, it } from "vitest";
import type { CarbonPricePlan, EconomicScenarioResult } from "../api/types";
import {
  carbonPriceAxis,
  economicForPlan,
  kpiSummary,
  planForPrice,
  selectionAtPrice,
} from "./priceScrubber";
import { screenResultFixture } from "../test/screenResult.fixture";

describe("priceScrubber over a deterministic result fixture", () => {
  it("builds an ascending carbon-price axis matching the plans", () => {
    const axis = carbonPriceAxis(screenResultFixture);
    expect(axis.length).toBe(screenResultFixture.plans.length);
    const prices = axis.map((p) => p.price);
    expect([...prices].sort((a, b) => a - b)).toEqual(prices);
  });

  it("resolves a plan for a given scenario id and falls back to the first", () => {
    const axis = carbonPriceAxis(screenResultFixture);
    const target = axis[axis.length - 1].scenarioId;
    expect(planForPrice(screenResultFixture, target)?.carbon_price_scenario_id).toBe(target);
    expect(planForPrice(screenResultFixture, "nope")).toBe(screenResultFixture.plans[0]);
  });

  it("reads the selection set per price from the cross-price comparison", () => {
    for (const point of carbonPriceAxis(screenResultFixture)) {
      const set = selectionAtPrice(screenResultFixture, point.scenarioId);
      expect(set).toBeInstanceOf(Set);
    }
  });

  it("returns null economics gracefully when no network is viable", () => {
    const plan = planForPrice(screenResultFixture, null)!;
    expect(economicForPlan(plan, "pre_tax")).toBeNull();
    const kpi = kpiSummary(null);
    expect(kpi.npv).toBeNull();
    expect(kpi.irr).toBeNull();
  });
});

describe("priceScrubber economics selection (synthetic)", () => {
  const econ: EconomicScenarioResult = {
    portfolio_id: "p",
    carbon_price_scenario_id: "cp_high",
    fiscal_case_id: "pre_tax",
    fiscal_mode: "pre_tax",
    annual_cashflows: [],
    storage: {
      injected_co2_tonnes: 1000,
      primary_net_stored_co2_tonnes: 900,
      divergence_fraction_of_injected: 0.01,
      mass_balance_passed: true,
      low_confidence: false,
      reasons: [],
    },
    breakdown: {} as EconomicScenarioResult["breakdown"],
    pre_tax_npv_usd: 5,
    npv_usd: 12_000,
    npv_low_usd: 8_000,
    npv_high_usd: 16_000,
    irr: { value: 0.18, status: "computed", method: "brent" },
    discounted_payback: { value: 4, status: "computed", method: "interp" },
    break_even_carbon_price: { value: 22, status: "computed", method: "brent" },
    break_even_oil_price: { value: null, status: "no_root", method: "brent" },
    low_confidence: false,
    confidence_reasons: [],
  };
  const plan = {
    carbon_price_scenario_id: "cp_high",
    economics: { results: [econ] },
  } as unknown as CarbonPricePlan;

  it("selects the matching price+fiscal result and summarizes KPIs", () => {
    const picked = economicForPlan(plan, "pre_tax");
    expect(picked).toBe(econ);
    const kpi = kpiSummary(picked);
    expect(kpi.npv).toBe(12_000);
    expect(kpi.irr).toBe(0.18);
    expect(kpi.breakEvenCarbon).toBe(22);
    expect(kpi.breakEvenOil).toBeNull(); // no_root -> null
    expect(kpi.netStored).toBe(900);
  });
});
