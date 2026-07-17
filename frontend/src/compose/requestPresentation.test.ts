import { describe, expect, it } from "vitest";
import { requestForDisplay } from "./requestPresentation";

describe("requestForDisplay", () => {
  it("aliases internal launch-pad keys and hides product-specific basis ids", () => {
    const rendered = JSON.stringify(
      requestForDisplay({
        seeds: { native: { pressure: [1] } },
        candidates: [
          {
            seed_by_schedule_fingerprint: {
              ABC: "native-seed",
            },
          },
        ],
        routing_basis_id: "jatibarang_case_study_v1",
      }),
    );

    expect(rendered).not.toMatch(/jatibarang|\bseeds?\b|seed_/i);
    expect(rendered).toContain("launch_pads");
    expect(rendered).toContain("configured basis");
  });
});
