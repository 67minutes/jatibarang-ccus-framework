import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReservoirImportResponse } from "../api/client";
import { NewStudyDialog, reservoirRefFromImport } from "./NewStudyDialog";

const importedReservoir = {
  model_id: "model-a",
  sha256: "A".repeat(64),
  source_file: "model.mat",
  geology: { length_x_m: 900, length_y_m: 600 },
  native_schedule: { injection_duration_days: 45 },
  native_fingerprint: "B".repeat(64),
  native_seed: { schedule_fingerprint: "B".repeat(64) },
  bank_seeds: {},
  well_ij: [31, 32],
  completion_ij: [[31, 32]],
  launchpads: {
    bank_id: null,
    bank_sha256: null,
    covered_fingerprints: ["B".repeat(64)],
  },
} satisfies ReservoirImportResponse;

describe("NewStudyDialog", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("maps the imported physical model into a lightweight reservoir reference", () => {
    const reference = reservoirRefFromImport(importedReservoir);

    expect(reference).toMatchObject({
      model_id: "model-a",
      source_file: "model.mat",
      well_ij: [31, 32],
      length_x_m: 900,
      length_y_m: 600,
      bank_id: null,
    });
    expect(reference.covered_fingerprints).not.toBe(
      importedReservoir.launchpads.covered_fingerprints,
    );
  });

  it("rejects an imported model without physical footprint dimensions", () => {
    expect(() =>
      reservoirRefFromImport({
        ...importedReservoir,
        geology: { length_x_m: 900 },
      }),
    ).toThrow(/length_y_m/);
  });

  it("starts from registered terrain instead of a demo template", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify([
            {
              terrain_id: "terrain-a",
              sha256: "C".repeat(64),
              source_path: "data/imports/c/west-java.tif",
              extent: {
                minLon: 107,
                minLat: -7,
                maxLon: 109,
                maxLat: -6,
              },
              cell_size_m: 30,
            },
          ]),
        ),
      ),
    );

    render(<NewStudyDialog onDone={() => undefined} />);

    await waitFor(() =>
      expect(screen.getByRole("option", { name: /west-java\.tif/i })).toBeVisible(),
    );
    expect(screen.queryByText(/demo base/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText("Center latitude")).toHaveValue(-6.5);
    expect(screen.getByLabelText("Center longitude")).toHaveValue(108);
    expect(screen.getByText(/native schedule/i)).toBeVisible();
  });
});
