import { describe, expect, it } from "vitest";
import {
  displayWireKey,
  presetDisplayName,
  quantityDisplayName,
  scientificDisplayText,
} from "./presentation";

describe("presentation vocabulary", () => {
  it("keeps internal preset and warm-history vocabulary out of UI copy", () => {
    const rendered = [
      presetDisplayName("jatibarang_demo_v1"),
      presetDisplayName("jatibarang_full_v1"),
      quantityDisplayName("seed_pressure_psi"),
      scientificDisplayText("warm-start history is a derived seed"),
      scientificDisplayText(
        "seeds.seed_pressure_psi failed in jatibarang_case_study_v1",
      ),
      displayWireKey("seed_by_schedule_fingerprint"),
    ].join(" ");

    expect(rendered).not.toMatch(/jatibarang|\bseeds?\b|seed_/i);
    expect(rendered).toMatch(/launch-pad|warm-start/i);
  });
});
