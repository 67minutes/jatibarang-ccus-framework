import { describe, expect, it } from "vitest";
import type { ProgressEvent } from "../api/types";
import { SseFrameParser } from "../api/sse";
import { buildTimeline } from "./stageTimeline";
import { readFixture } from "../test/fixture";

const raw = readFixture("src/test/fixtures/stream.sse");

function events(): ProgressEvent[] {
  const parser = new SseFrameParser();
  return parser
    .push(raw)
    .map((f) => JSON.parse(f.data) as ProgressEvent)
    .filter((e) => e.event !== "result");
}

describe("buildTimeline", () => {
  it("folds the real stream into ordered stages starting with resolve/surrogate", () => {
    const rows = buildTimeline(events());
    expect(rows.length).toBeGreaterThan(0);
    expect(rows[0].stage).toBe("resolve");
    expect(rows.map((r) => r.stage)).toContain("surrogate");
  });

  it("marks completed stages done and labels per-price portfolio stages", () => {
    const rows = buildTimeline(events());
    // The stream completed, so at least the early stages are done.
    expect(rows.some((r) => r.status === "done")).toBe(true);
    const portfolio = rows.find((r) => r.stage.startsWith("portfolio:"));
    if (portfolio) expect(portfolio.label).toMatch(/Network \+ economics @/);
  });
});
