import { describe, expect, it } from "vitest";
import type { ScreenResult } from "../api/types";
import { displayPredictions, preliminaryRanking } from "./displayData";
import { planForPrice } from "./priceScrubber";
import { readFixture } from "../test/fixture";

const canned = JSON.parse(readFixture("public/assets/canned-demo.json")) as ScreenResult;

describe("displayData fallbacks (no viable network)", () => {
  it("falls back to per-well strategy predictions when no detailed set exists", () => {
    expect(Object.keys(canned.detailed_predictions)).toHaveLength(0);
    const preds = displayPredictions(canned, null);
    expect(preds.length).toBeGreaterThan(0);
    for (const p of preds) {
      expect(p.prediction.production.cumulative_oil_m3.length).toBeGreaterThan(0);
      expect(p.candidateId).toBeTruthy();
    }
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
