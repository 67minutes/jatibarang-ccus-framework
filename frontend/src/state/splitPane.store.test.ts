import { beforeEach, describe, expect, it } from "vitest";
import {
  clampSplitPaneSize,
  splitPaneLimits,
  useSplitPaneStore,
} from "./splitPane.store";

describe("splitPane.store", () => {
  beforeEach(() => useSplitPaneStore.getState().resetAll());

  it("starts at the locked desktop defaults", () => {
    expect(useSplitPaneStore.getState().sizes).toEqual({
      left: 248,
      right: 320,
      bottom: 340,
    });
  });

  it("clamps the side panels to their exact limits", () => {
    expect(clampSplitPaneSize("left", 12)).toBe(180);
    expect(clampSplitPaneSize("left", 900)).toBe(420);
    expect(clampSplitPaneSize("right", 12)).toBe(260);
    expect(clampSplitPaneSize("right", 900)).toBe(520);
  });

  it("caps the bottom panel at 70 percent of the center height", () => {
    expect(splitPaneLimits("bottom", 800)).toEqual({ min: 180, max: 560 });
    expect(clampSplitPaneSize("bottom", 700, 800)).toBe(560);
    expect(clampSplitPaneSize("bottom", 100, 800)).toBe(180);
  });

  it("retains and resets each size independently", () => {
    const state = useSplitPaneStore.getState();
    state.setSize("left", 390);
    state.setSize("right", 500);
    state.resetSize("left");
    expect(useSplitPaneStore.getState().sizes).toEqual({
      left: 248,
      right: 500,
      bottom: 340,
    });
  });
});

