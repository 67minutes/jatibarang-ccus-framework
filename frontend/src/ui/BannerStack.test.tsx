import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { useUiStore } from "../state/ui.store";
import { BannerStack } from "./BannerStack";

describe("BannerStack", () => {
  beforeEach(() => useUiStore.setState({ banners: [] }));

  it("keeps internal request vocabulary out of mixed backend errors", () => {
    useUiStore.getState().pushBanner({
      id: "mixed-error",
      severity: "danger",
      message:
        "seeds.seed_pressure_psi failed in jatibarang_case_study_v1",
    });

    render(<BannerStack />);

    const message = screen.getByRole("status").textContent ?? "";
    expect(message).not.toMatch(/jatibarang|\bseeds?\b|seed_/i);
    expect(message).toMatch(/launch pads|warm-start/i);
  });
});
