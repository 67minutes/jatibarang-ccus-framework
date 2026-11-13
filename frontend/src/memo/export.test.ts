import { describe, expect, it } from "vitest";

import type { FieldSetupMemo, LedgerEntry } from "./studyMemo";
import { buildMrstResimulationPlan } from "./export";

describe("MRST re-simulation export", () => {
  it("binds each shortlist schedule to its per-well reservoir hash", () => {
    const entry = {
      label: "field",
      request: {
        mode: "inline",
        candidates: [
          { candidate_id: "W02", location: { latitude: -6.5, longitude: 108.4 } },
        ],
      },
      result: {
        request_fingerprint: "A".repeat(64),
        shortlist: [{
          rank: 1,
          candidate_id: "W02",
          scenario_id: "W02--ABC",
          carbon_price_scenario_ids: ["p40"],
        }],
        plans: [{
          well_strategies: [{
            scenario_id: "W02--ABC",
            schedule: {
              injection_rate_m3_day: 9000,
              injection_duration_days: 45,
              soak_duration_days: 30,
              production_duration_days: 190,
              production_bhp_psi: 675,
              cycles: 4,
            },
          }],
        }],
      },
    } as unknown as LedgerEntry;
    const field = {
      reservoir: { model_id: "primary" },
      reservoir_assignments: {
        W02: {
          model_id: "model-w02",
          sha256: "B".repeat(64),
          source_file: "W02--case_0021.reservoir.npz",
          bank_id: "bank-w02",
          bank_sha256: "C".repeat(64),
        },
      },
    } as unknown as FieldSetupMemo;

    const plan = buildMrstResimulationPlan(entry, field);

    expect(plan.runtime_mrst_forbidden).toBe(true);
    expect(plan.raw_training_corpus_copied).toBe(false);
    expect(plan.selection_basis).toBe("development_shortlist");
    expect(plan.development_selection_claimed).toBe(true);
    expect(plan.entries[0]).toMatchObject({
      candidate_id: "W02",
      scenario_id: "W02--ABC",
      location: { latitude: -6.5, longitude: 108.4 },
      reservoir: {
        model_id: "model-w02",
        source_file: "W02--case_0021.reservoir.npz",
        bank_id: "bank-w02",
      },
      schedule: { cycles: 4, injection_rate_m3_day: 9000 },
      development_selected: true,
    });
  });

  it("exports top-K verification candidates without claiming development", () => {
    const entry = {
      label: "field",
      request: {
        mode: "inline",
        shortlist_top_k: 2,
        candidates: [
          { candidate_id: "W01", location: { latitude: -6.5, longitude: 108.4 } },
          { candidate_id: "W02", location: { latitude: -6.6, longitude: 108.5 } },
        ],
      },
      result: {
        request_fingerprint: "D".repeat(64),
        shortlist: [],
        plans: [{
          carbon_price_scenario_id: "p500",
          carbon_price_usd_per_tonne: 500,
          well_strategies: [
            {
              candidate_id: "W01",
              scenario_id: "W01--A",
              preliminary_npv_usd: 20,
              schedule: { cycles: 4 },
            },
            {
              candidate_id: "W02",
              scenario_id: "W02--B",
              preliminary_npv_usd: 30,
              schedule: { cycles: 3 },
            },
          ],
        }],
      },
    } as unknown as LedgerEntry;
    const field = {
      reservoir: { model_id: "primary" },
      reservoir_assignments: {
        W01: { model_id: "model-w01", sha256: "1".repeat(64) },
        W02: { model_id: "model-w02", sha256: "2".repeat(64) },
      },
    } as unknown as FieldSetupMemo;

    const plan = buildMrstResimulationPlan(entry, field);

    expect(plan.selection_basis).toBe("pre_logistics_non_development_ranking");
    expect(plan.development_selection_claimed).toBe(false);
    expect(plan.entries.map((item) => item.candidate_id)).toEqual(["W02", "W01"]);
    expect(plan.entries.every((item) => item.development_selected === false)).toBe(true);
    expect(plan.entries[0].reservoir?.model_id).toBe("model-w02");
  });
});
