import { describe, expect, it } from "vitest";
import type { InlineScreenRequest, ScreenResult } from "../api/types";
import type { LedgerEntry } from "../memo/studyMemo";
import { compareEntries, diffRequests, rankTrajectories } from "./compare";

function inlineReq(carbonPrice: number): InlineScreenRequest {
  return {
    mode: "inline",
    geologies: {},
    seeds: {},
    candidates: [],
    sources: [],
    annual_co2_budget_tonnes: 320_000,
    carbon_prices: [
      { scenario_id: "a", carbon_price_usd_per_tonne: carbonPrice, source_type: "economic_assumption", provenance: [] },
    ],
    fiscal_cases: [{ case_id: "pre_tax", mode: "pre_tax" }],
    economic_assumptions: {},
    cost_case: "base",
  };
}

function resultWith(shortlist: ScreenResult["shortlist"]): ScreenResult {
  return {
    run_id: "r",
    request_fingerprint: "f",
    status: "completed",
    logical_scenario_count: 1,
    unique_inference_count: 1,
    inference_cache_hits: 0,
    plans: [],
    cross_price_comparison: { selection_by_carbon_price: {}, transitions: [], pivot_observed: false },
    shortlist,
    detailed_predictions: {},
    timings: { total_seconds: 1, stages_seconds: {}, milp_solve_seconds: 0 },
    warnings: [],
    provenance_catalog: {},
  };
}

function entry(id: string, req: InlineScreenRequest, result: ScreenResult): LedgerEntry {
  return { entryId: id, fingerprint: id, label: id, savedAt: "", request: req, result, imported: false };
}

describe("compare", () => {
  it("reports only the changed request fields", () => {
    const deltas = diffRequests(inlineReq(15), inlineReq(8));
    const fields = deltas.map((d) => d.field);
    expect(fields).toContain("carbon_prices");
    // Cost case, budget, etc. are identical -> not reported.
    expect(fields).not.toContain("cost_case");
  });

  it("computes rank trajectories and NPV deltas by candidate", () => {
    const a = resultWith([
      { rank: 1, candidate_id: "W01", scenario_id: "s", carbon_price_scenario_ids: ["a"], designated_npv_usd: 100, reasons: [] },
      { rank: 2, candidate_id: "W02", scenario_id: "s", carbon_price_scenario_ids: ["a"], designated_npv_usd: 50, reasons: [] },
    ]);
    const b = resultWith([
      { rank: 1, candidate_id: "W02", scenario_id: "s", carbon_price_scenario_ids: ["a"], designated_npv_usd: 60, reasons: [] },
    ]);
    const traj = rankTrajectories(a, b);
    const w01 = traj.find((t) => t.candidateId === "W01")!;
    const w02 = traj.find((t) => t.candidateId === "W02")!;
    expect(w01.rankA).toBe(1);
    expect(w01.rankB).toBeNull(); // dropped off in B
    expect(w02.rankA).toBe(2);
    expect(w02.rankB).toBe(1);
    expect(w02.npvA).toBe(50);
    expect(w02.npvB).toBe(60);
  });

  it("flags identical fingerprints", () => {
    const req = inlineReq(15);
    const res = resultWith([]);
    const cmp = compareEntries(entry("x", req, res), entry("x", req, res));
    expect(cmp.sameFingerprint).toBe(true);
  });
});
