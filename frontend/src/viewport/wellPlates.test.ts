import { describe, expect, it } from "vitest";
import type { PredictionResult, ReservoirVisualization } from "../api/types";
import type { ReservoirImportResponse } from "../api/client";
import type { PlacedWell } from "../state/field.store";
import {
  collectWellPlates,
  fieldFocusCoordinate,
  maxFrameCount,
  scenarioIdForWell,
} from "./wellPlates";

const runtime = (modelId: string) =>
  ({ model_id: modelId }) as unknown as ReservoirImportResponse;
const viz = (id: string) => ({ id }) as unknown as ReservoirVisualization;
const stubConverter = (imported: ReservoirImportResponse | null) =>
  imported
    ? viz(`viz-${(imported as unknown as { model_id: string }).model_id}`)
    : null;
const well = (id: string, lat: number, lon: number): PlacedWell => ({
  id,
  name: id,
  kind: "placed",
  lat,
  lon,
});
const prediction = (frameCount: number) =>
  ({
    fields: Array.from({ length: frameCount }, (_, step_index) => ({
      step_index,
      z_co2: { values: [] },
      gas_saturation: { values: [] },
      pressure_bar: { values: [] },
    })),
  }) as unknown as PredictionResult;

describe("scenarioIdForWell", () => {
  it("prefers the explicitly selected scenario when it belongs to the well", () => {
    const keys = ["W07--AAA", "W07--BBB", "W01--CCC"];
    expect(scenarioIdForWell(keys, "W07", "W07--BBB")).toBe("W07--BBB");
  });

  it("ignores a preferred scenario belonging to a different well", () => {
    const keys = ["W07--AAA", "W01--CCC"];
    expect(scenarioIdForWell(keys, "W07", "W01--CCC")).toBe("W07--AAA");
  });

  it("falls back to the first prefix or exact match, else null", () => {
    expect(scenarioIdForWell(["W07--AAA"], "W07")).toBe("W07--AAA");
    expect(scenarioIdForWell(["W07"], "W07")).toBe("W07");
    expect(scenarioIdForWell(["W01--CCC"], "W07")).toBeNull();
    // W17 must not match W1's prefix or vice versa.
    expect(scenarioIdForWell(["W17--DDD"], "W1")).toBeNull();
  });
});

describe("collectWellPlates", () => {
  const detailedReservoirs = { "W01--CCC": viz("detailed-W01") };
  const detailedPredictions = { "W01--CCC": prediction(3) };

  it("uses retained detailed fields when present, imported geology otherwise", () => {
    const plates = collectWellPlates(
      {
        wells: [well("W01", -6.5, 108.3), well("W02", -6.6, 108.4)],
        runtimes: { W01: runtime("m1"), W02: runtime("m2") },
        detailedReservoirs,
        detailedPredictions,
      },
      stubConverter,
    );
    expect(plates).toHaveLength(2);
    expect(plates[0]).toMatchObject({
      wellId: "W01",
      scenarioId: "W01--CCC",
      reservoir: viz("detailed-W01"),
      coordinate: { latitude: -6.5, longitude: 108.3 },
    });
    expect(plates[0].prediction).not.toBeNull();
    expect(plates[1]).toMatchObject({
      wellId: "W02",
      scenarioId: null,
      reservoir: viz("viz-m2"),
      prediction: null,
    });
  });

  it("omits wells with neither a runtime nor retained detail", () => {
    const plates = collectWellPlates(
      {
        wells: [well("W03", -6.7, 108.5)],
        runtimes: {},
        detailedReservoirs: {},
        detailedPredictions: {},
      },
      stubConverter,
    );
    expect(plates).toHaveLength(0);
  });

  it("keeps prediction null when the detailed reservoir has no retained prediction", () => {
    const plates = collectWellPlates(
      {
        wells: [well("W01", -6.5, 108.3)],
        runtimes: {},
        detailedReservoirs,
        detailedPredictions: {},
      },
      stubConverter,
    );
    expect(plates[0].reservoir).toEqual(viz("detailed-W01"));
    expect(plates[0].prediction).toBeNull();
  });

  it("routes the preferred scenario only to the selected well", () => {
    const twoScenarios = {
      "W01--CCC": viz("detailed-W01-C"),
      "W01--DDD": viz("detailed-W01-D"),
    };
    const plates = collectWellPlates(
      {
        wells: [well("W01", -6.5, 108.3)],
        runtimes: {},
        detailedReservoirs: twoScenarios,
        detailedPredictions: {},
        selectedWellId: "W01",
        preferredScenarioId: "W01--DDD",
      },
      stubConverter,
    );
    expect(plates[0].scenarioId).toBe("W01--DDD");
  });
});

describe("fieldFocusCoordinate", () => {
  const wells = [well("W01", -6.5, 108.3), well("W20", -6.9, 108.6)];
  const placement = {
    name: "Jatibarang",
    center_lat: -6.55,
    center_lon: 108.35,
    rotation_deg: 0,
  };

  it("returns the selected well's coordinate", () => {
    expect(
      fieldFocusCoordinate({ kind: "well", id: "W20" }, wells, placement),
    ).toEqual({ latitude: -6.9, longitude: 108.6 });
  });

  it("falls back to the placement when nothing (or a non-well) is selected", () => {
    expect(
      fieldFocusCoordinate({ kind: "none", id: null }, wells, placement),
    ).toEqual({ latitude: -6.55, longitude: 108.35 });
    expect(
      fieldFocusCoordinate({ kind: "source", id: "S1" }, wells, placement),
    ).toEqual({ latitude: -6.55, longitude: 108.35 });
    expect(
      fieldFocusCoordinate({ kind: "well", id: "W99" }, wells, placement),
    ).toEqual({ latitude: -6.55, longitude: 108.35 });
  });

  it("returns null without a placement or matching well", () => {
    expect(fieldFocusCoordinate({ kind: "none", id: null }, wells, null)).toBeNull();
  });
});

describe("maxFrameCount", () => {
  it("returns the maximum frame count across retained predictions", () => {
    expect(maxFrameCount([prediction(3), null, prediction(7), undefined])).toBe(7);
  });

  it("returns 0 for empty or field-less predictions", () => {
    expect(maxFrameCount([])).toBe(0);
    expect(
      maxFrameCount([{ fields: null } as unknown as PredictionResult]),
    ).toBe(0);
  });
});
