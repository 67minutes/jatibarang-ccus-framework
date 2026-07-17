import { describe, expect, it } from "vitest";
import type { ScreenResult } from "../api/types";
import { displayPredictions, preliminaryRanking } from "./displayData";
import { planForPrice } from "./priceScrubber";
import { readFixture } from "../test/fixture";

const canned = JSON.parse(readFixture("public/assets/canned-demo.json")) as ScreenResult;

describe("displayData fallbacks (no viable network)", () => {
  it("uses the aligned case-0016 detailed prediction when retained", () => {
    expect(Object.keys(canned.detailed_predictions)).toHaveLength(1);
    expect(Object.keys(canned.detailed_reservoirs)).toEqual(
      Object.keys(canned.detailed_predictions),
    );
    const preds = displayPredictions(canned, null);
    expect(preds).toHaveLength(1);
    expect(canned.detailed_reservoirs[preds[0].scenarioId].geology_id).toBe("case_0016");
    for (const p of preds) {
      expect(p.prediction.production.cumulative_oil_m3.length).toBeGreaterThan(0);
      expect(p.candidateId).toBeTruthy();
    }
  });

  it("falls back to compact per-well predictions when detail was not retained", () => {
    const compactOnly = {
      ...canned,
      detailed_predictions: {},
      detailed_reservoirs: {},
    } satisfies ScreenResult;
    expect(displayPredictions(compactOnly, null).length).toBeGreaterThan(0);
  });

  it("produces a pre-logistics ranking sorted by preliminary NPV", () => {
    const plan = planForPrice(canned, null);
    const rows = preliminaryRanking(plan);
    expect(rows.length).toBeGreaterThan(0);
    for (let i = 1; i < rows.length; i++) {
      expect(rows[i - 1].preliminaryNpv).toBeGreaterThanOrEqual(rows[i].preliminaryNpv);
    }
  });
});
