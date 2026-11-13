import { describe, expect, it } from "vitest";

import { parseReservoirCatalog } from "./reservoirCatalog";

describe("parseReservoirCatalog", () => {
  it("normalizes and orders a wrapped per-well catalog", () => {
    expect(
      parseReservoirCatalog(JSON.stringify({
        entries: [
          { well_id: "w02", model_path: " C:/models/b.npz " },
          { well_id: "W01", model_path: "C:/models/a.npz", bank_path: "" },
        ],
      })),
    ).toEqual([
      { well_id: "W01", model_path: "C:/models/a.npz", bank_path: null },
      { well_id: "W02", model_path: "C:/models/b.npz", bank_path: null },
    ]);
  });

  it("rejects gaps, duplicates, malformed JSON, and more than 20 entries", () => {
    expect(() => parseReservoirCatalog("not json")).toThrow(/valid JSON/i);
    expect(() => parseReservoirCatalog(JSON.stringify([
      { well_id: "W01", model_path: "a.npz" },
      { well_id: "W03", model_path: "c.npz" },
    ]))).toThrow(/expected W02/i);
    expect(() => parseReservoirCatalog(JSON.stringify([
      { well_id: "W01", model_path: "a.npz" },
      { well_id: "w01", model_path: "b.npz" },
    ]))).toThrow(/unique/i);
    expect(() => parseReservoirCatalog(JSON.stringify(Array.from(
      { length: 21 },
      (_, index) => ({
        well_id: `W${String(index + 1).padStart(2, "0")}`,
        model_path: `${index}.npz`,
      }),
    )))).toThrow(/1 to 20/i);
  });
});
