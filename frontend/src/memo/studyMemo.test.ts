import { describe, expect, it } from "vitest";
import { isLegacyMemo, STUDY_MEMO_VERSION } from "./studyMemo";

describe("memo v3", () => {
  it("flags older memos as legacy", () => {
    expect(STUDY_MEMO_VERSION).toBe(3);
    expect(isLegacyMemo({ memo_version: 2 })).toBe(true);
    expect(isLegacyMemo({ memo_version: 3 })).toBe(false);
  });
});
