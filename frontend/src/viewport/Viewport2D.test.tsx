import { beforeEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useFieldStore } from "../state/field.store";
import { useLedgerStore } from "../state/ledger.store";
import { useSelectionStore } from "../state/selection.store";
import { useWorkspaceStore } from "../state/workspace.store";
import { Viewport2D } from "./Viewport2D";

describe("Viewport2D field setup", () => {
  beforeEach(() => {
    useFieldStore.getState().reset();
    useLedgerStore.setState({
      entries: [],
      activeEntryId: null,
      compareIds: [null, null],
    });
    useSelectionStore.getState().clear();
    useWorkspaceStore.setState({ viewport: "2d" });
  });

  it("shows the pre-run field and enters its high-resolution 3D view", async () => {
    const user = userEvent.setup();
    useFieldStore.getState().setup(
      {
        terrain_id: "terrain-one",
        sha256: "A".repeat(64),
        source_path: "terrain.tif",
        extent: { minLon: 108, maxLon: 109, minLat: -7, maxLat: -6 },
      },
      {
        model_id: "model-one",
        sha256: "B".repeat(64),
        source_file: "case.mat",
        native_fingerprint: "native",
        covered_fingerprints: ["native"],
        bank_id: null,
        bank_sha256: null,
        well_ij: [30, 36],
        length_x_m: 900,
        length_y_m: 600,
      },
      {
        name: "Field one",
        center_lat: -6.53,
        center_lon: 108.39,
        rotation_deg: 35,
      },
    );
    useFieldStore.getState().addSource({
      name: "Capture plant",
      lat: -6.57,
      lon: 107.76,
      annual_capacity_t: 500_000,
      outlet_pressure_bar: 120,
      outlet_temperature_c: 27,
      co2_purity: 0.95,
      max_mass_flow_kg_s: 600,
    });

    render(<Viewport2D />);

    expect(screen.getByRole("img", { name: "Study map" })).toBeInTheDocument();
    expect(screen.getByText("W01")).toBeInTheDocument();
    expect(screen.getByText("S01")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Enter field view" }));

    expect(useFieldStore.getState().level).toBe("field");
    expect(useWorkspaceStore.getState().viewport).toBe("3d");
  });
});
