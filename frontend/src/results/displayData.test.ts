import { describe, expect, it } from "vitest";
import type { ScreenResult } from "../api/types";
import { displayPredictions, preliminaryRanking } from "./displayData";
import { planForPrice } from "./priceScrubber";
import { screenResultFixture } from "../test/screenResult.fixture";

describe("displayData fallbacks (no viable network)", () => {
  it("uses an aligned detailed prediction when retained", () => {
    expect(Object.keys(screenResultFixture.detailed_predictions)).toHaveLength(1);
    expect(Object.keys(screenResultFixture.detailed_reservoirs)).toEqual(
      Object.keys(screenResultFixture.detailed_predictions),
    );
    const preds = displayPredictions(screenResultFixture, null);
    expect(preds).toHaveLength(1);
    expect(screenResultFixture.detailed_reservoirs[preds[0].scenarioId].geology_id).toBe("model-01");
    for (const p of preds) {
      expect(p.prediction.production.cumulative_oil_m3.length).toBeGreaterThan(0);
      expect(p.candidateId).toBeTruthy();
    }
  });

  it("falls back to compact per-well predictions when detail was not retained", () => {
    const compactOnly = {
      ...screenResultFixture,
      detailed_predictions: {},
      detailed_reservoirs: {},
    } satisfies ScreenResult;
    expect(displayPredictions(compactOnly, null).length).toBeGreaterThan(0);
  });

  it("produces a pre-logistics ranking sorted by preliminary NPV", () => {
    const plan = planForPrice(screenResultFixture, null);
    const rows = preliminaryRanking(plan);
    expect(rows.length).toBeGreaterThan(0);
    for (let i = 1; i < rows.length; i++) {
      expect(rows[i - 1].preliminaryNpv).toBeGreaterThanOrEqual(rows[i].preliminaryNpv);
    }
  });
});
