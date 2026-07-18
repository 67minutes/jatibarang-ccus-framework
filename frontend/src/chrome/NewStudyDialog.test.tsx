import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReservoirImportResponse } from "../api/client";
import { comboFingerprint, scheduleCombos } from "../compose/coverage";
import { DEFAULT_OPERATIONAL_GRID } from "../compose/defaults";
import {
  launchPadCoveragePreview,
  NewStudyDialog,
  reservoirRefFromImport,
} from "./NewStudyDialog";

const NATIVE_FINGERPRINT =
  "E76B43C3F324821A90DCE393ACEEAB5FDF5C4AAF158639E2A37DCBDAC170E451";

const importedReservoir = {
  model_id: "model-a",
  sha256: "A".repeat(64),
  source_file: "model.mat",
  geology: { length_x_m: 900, length_y_m: 600 },
  native_schedule: {
    injection_rate_m3_day: 8687.177439504216,
    injection_reference_pressure_bar: 120,
    injection_reference_temperature_c: 40,
    injection_duration_days: 46.89706574654418,
    soak_duration_days: 28.126672556861426,
    production_duration_days: 199.0340798188366,
    production_bhp_psi: 669.0069852265157,
    cycles: 4,
  },
  native_fingerprint: NATIVE_FINGERPRINT,
  native_seed: { schedule_fingerprint: NATIVE_FINGERPRINT },
  bank_seeds: {},
  well_ij: [31, 32],
  completion_ij: [[31, 32]],
  launchpads: {
    bank_id: null,
    bank_sha256: null,
    covered_fingerprints: [NATIVE_FINGERPRINT],
  },
} satisfies ReservoirImportResponse;

const registeredTerrain = {
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
};

function stubImportApi(reservoir?: ReservoirImportResponse) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/reservoir/import") && reservoir) {
        return new Response(JSON.stringify(reservoir));
      }
      return new Response(JSON.stringify([registeredTerrain]));
    }),
  );
}

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

  it("reports an off-grid native launch pad separately from grid coverage", () => {
    const preview = launchPadCoveragePreview(importedReservoir);

    expect(preview.error).toBeNull();
    expect(preview.plan?.coverage).toMatchObject({ covered: 0, total: 162 });
    expect(preview.plan?.native).toMatchObject({ available: true, onGrid: false });
    expect(preview.plan?.usesNativeFallback).toBe(true);
  });

  it("calculates exact grid coverage from the imported bank payloads", () => {
    const [first, second] = scheduleCombos(DEFAULT_OPERATIONAL_GRID);
    const firstFingerprint = comboFingerprint(first, 45);
    const secondFingerprint = comboFingerprint(second, 45);
    const preview = launchPadCoveragePreview({
      ...importedReservoir,
      bank_seeds: {
        [firstFingerprint]: { schedule_fingerprint: firstFingerprint },
        [secondFingerprint]: { schedule_fingerprint: secondFingerprint },
      },
      launchpads: {
        bank_id: "bank-a",
        bank_sha256: "D".repeat(64),
        covered_fingerprints: [
          NATIVE_FINGERPRINT,
          firstFingerprint,
          secondFingerprint,
        ],
      },
    });

    expect(preview.error).toBeNull();
    expect(preview.plan?.coverage).toMatchObject({ covered: 2, total: 162 });
    expect(preview.plan?.native).toMatchObject({ available: true, onGrid: false });
  });

  it("keeps the preview safe when an older response lacks native schedule fields", () => {
    const preview = launchPadCoveragePreview({
      ...importedReservoir,
      native_schedule: { injection_duration_days: 45 },
    });

    expect(preview.plan).toBeNull();
    expect(preview.error).toMatch(/imported native schedule is missing/i);
  });

  it("starts from registered terrain instead of a demo template", async () => {
    stubImportApi();

    render(<NewStudyDialog onDone={() => undefined} />);

    await waitFor(() =>
      expect(screen.getByRole("option", { name: /west-java\.tif/i })).toBeVisible(),
    );
    expect(screen.queryByText(/demo base/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText("Center latitude")).toHaveValue(-6.5);
    expect(screen.getByLabelText("Center longitude")).toHaveValue(108);
    expect(screen.getByText(/native schedule/i)).toBeVisible();
  });

  it("shows zero grid coverage without counting the real off-grid native run", async () => {
    stubImportApi(importedReservoir);
    render(<NewStudyDialog onDone={() => undefined} />);

    await waitFor(() =>
      expect(screen.getByRole("option", { name: /west-java\.tif/i })).toBeVisible(),
    );
    fireEvent.change(screen.getByLabelText("Reservoir model path"), {
      target: { value: "C:\\models\\case_0016.mat" },
    });
    fireEvent.click(screen.getByRole("button", { name: /inspect model/i }));

    expect(await screen.findByText(/0 of 162/i)).toBeVisible();
    expect(
      screen.getByText(/native schedule is real and runnable, but outside/i),
    ).toBeVisible();
  });

  it("imports an optional road network and reports its cached size", async () => {
    const fetchMock = vi.fn(async (
      input: RequestInfo | URL,
      _init?: RequestInit,
    ) => {
      const url = String(input);
      if (url === "/roads/import") {
        return new Response(
          JSON.stringify({
            road_network_id: "roads-a",
            sha256: "R".repeat(64),
            node_count: 12,
            edge_count: 11,
            bbox: [107, -7, 109, -6],
          }),
        );
      }
      if (url === "/roads/roads-a/layers") {
        return new Response(
          JSON.stringify({ roads: [], coastline: [], places: [] }),
        );
      }
      return new Response(JSON.stringify([registeredTerrain]));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<NewStudyDialog onDone={() => undefined} />);

    await waitFor(() =>
      expect(screen.getByRole("option", { name: /west-java\.tif/i })).toBeVisible(),
    );
    fireEvent.change(screen.getByLabelText("Road network (.osm.pbf)"), {
      target: { value: "C:\\maps\\java.osm.pbf" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Import network" }));

    expect(await screen.findByText("12 nodes · 11 edges")).toBeVisible();
    const [, init] = fetchMock.mock.calls.find(([url]) => url === "/roads/import")!;
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      path: "C:\\maps\\java.osm.pbf",
      terrain_id: "terrain-a",
    });
  });
});
