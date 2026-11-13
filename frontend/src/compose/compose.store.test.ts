import { beforeEach, describe, expect, it } from "vitest";
import type { InlineScreenRequest } from "../api/types";
import { useComposeStore } from "./compose.store";

function draft(): InlineScreenRequest {
  return {
    mode: "inline",
    geologies: {},
    seeds: {},
    candidates: [],
    sources: [],
    annual_co2_budget_tonnes: 1,
    carbon_prices: [],
    fiscal_cases: [],
    economic_assumptions: {
      oil_price_usd_per_bbl: 73,
      lifting_cost_usd_per_bbl: 18,
      discount_rate: 0.1,
    },
  };
}

describe("compose economic assumptions", () => {
  beforeEach(() => {
    useComposeStore.setState({ draft: null, past: [], future: [] });
  });

  it("updates engineer-controlled assumptions and participates in undo", () => {
    const store = useComposeStore.getState();
    store.loadBase(draft());
    store.setEconomicAssumption("oil_price_usd_per_bbl", 120);
    store.setEconomicAssumption("lifting_cost_usd_per_bbl", 22);
    store.setEconomicAssumption("discount_rate", 0.08);

    expect(useComposeStore.getState().draft?.economic_assumptions).toMatchObject({
      oil_price_usd_per_bbl: 120,
      lifting_cost_usd_per_bbl: 22,
      discount_rate: 0.08,
    });

    useComposeStore.getState().undo();
    expect(useComposeStore.getState().draft?.economic_assumptions.discount_rate).toBe(0.1);
    expect(useComposeStore.getState().canRedo()).toBe(true);
  });
});
