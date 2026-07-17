import { describe, expect, it } from "vitest";
import { terrainColor } from "./terrain";

describe("terrain color treatment", () => {
  it("keeps geologic relief chromatic and elevation-responsive", () => {
    const low = terrainColor(0.05, "geologic");
    const high = terrainColor(0.9, "geologic");
    expect(low).not.toEqual(high);
    expect(low[1]).toBeGreaterThan(low[0]);
    expect(high[0]).toBeGreaterThan(low[0]);
  });

  it("offers a restrained monochrome preference", () => {
    const [r, g, b] = terrainColor(0.5, "monochrome");
    expect(Math.max(r, g, b) - Math.min(r, g, b)).toBeLessThan(0.08);
  });

  it("clamps values outside the normalized elevation range", () => {
    expect(terrainColor(-1, "geologic")).toEqual(terrainColor(0, "geologic"));
    expect(terrainColor(2, "geologic")).toEqual(terrainColor(1, "geologic"));
  });
});

