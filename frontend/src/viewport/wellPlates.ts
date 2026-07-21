import type {
  Coordinate,
  PredictionResult,
  ReservoirVisualization,
} from "../api/types";
import type { ReservoirImportResponse } from "../api/client";
import type { FieldPlacement, PlacedWell } from "../state/field.store";
import type { Selection } from "../state/selection.store";
import { reservoirVisualizationFromImport } from "./ReservoirGrid";
import { framesFromPrediction } from "./plume";

/** One renderable geology plate anchored at a well. */
export interface WellPlateDescriptor {
  wellId: string;
  coordinate: Coordinate;
  /** Retained detailed scenario backing this plate, when one exists. */
  scenarioId: string | null;
  reservoir: ReservoirVisualization;
  /** Only present when detailed fields were retained for the scenario. */
  prediction: PredictionResult | null;
}

export interface WellPlateInputs {
  wells: PlacedWell[];
  runtimes: Record<string, ReservoirImportResponse>;
  detailedReservoirs: Record<string, ReservoirVisualization>;
  detailedPredictions: Record<string, PredictionResult>;
  /** Scenario the user explicitly picked (shortlist click); applies to selectedWellId only. */
  preferredScenarioId?: string | null;
  selectedWellId?: string | null;
}

export function scenarioIdForWell(
  detailedKeys: string[],
  wellId: string,
  preferredScenarioId?: string | null,
): string | null {
  if (
    preferredScenarioId &&
    (preferredScenarioId === wellId ||
      preferredScenarioId.startsWith(`${wellId}--`)) &&
    detailedKeys.includes(preferredScenarioId)
  ) {
    return preferredScenarioId;
  }
  return (
    detailedKeys.find((id) => id === wellId || id.startsWith(`${wellId}--`)) ??
    null
  );
}

// Imported payloads are large and stable for a session; convert each at most once.
const visualizationCache = new WeakMap<
  ReservoirImportResponse,
  ReservoirVisualization | null
>();

export function cachedVisualizationFromImport(
  imported: ReservoirImportResponse | null,
): ReservoirVisualization | null {
  if (!imported) return null;
  if (!visualizationCache.has(imported)) {
    visualizationCache.set(imported, reservoirVisualizationFromImport(imported));
  }
  return visualizationCache.get(imported) ?? null;
}

export function collectWellPlates(
  inputs: WellPlateInputs,
  toVisualization: (
    imported: ReservoirImportResponse | null,
  ) => ReservoirVisualization | null = cachedVisualizationFromImport,
): WellPlateDescriptor[] {
  const detailedKeys = Object.keys(inputs.detailedReservoirs);
  const plates: WellPlateDescriptor[] = [];
  for (const well of inputs.wells) {
    const preferred =
      well.id === inputs.selectedWellId ? inputs.preferredScenarioId : null;
    const scenarioId = scenarioIdForWell(detailedKeys, well.id, preferred);
    const detailed = scenarioId
      ? inputs.detailedReservoirs[scenarioId]
      : undefined;
    const reservoir = detailed ?? toVisualization(inputs.runtimes[well.id] ?? null);
    if (!reservoir) continue;
    plates.push({
      wellId: well.id,
      coordinate: { latitude: well.lat, longitude: well.lon },
      scenarioId: detailed && scenarioId ? scenarioId : null,
      reservoir,
      prediction:
        detailed && scenarioId
          ? (inputs.detailedPredictions[scenarioId] ?? null)
          : null,
    });
  }
  return plates;
}

/** Field-view focus: the selected well when there is one, else the placement. */
export function fieldFocusCoordinate(
  selection: Selection,
  wells: PlacedWell[],
  placement: FieldPlacement | null,
): Coordinate | null {
  if (selection.kind === "well" && selection.id) {
    const well = wells.find((item) => item.id === selection.id);
    if (well) return { latitude: well.lat, longitude: well.lon };
  }
  return placement
    ? { latitude: placement.center_lat, longitude: placement.center_lon }
    : null;
}

/** Global timeline length: the longest retained playback among visible plates. */
export function maxFrameCount(
  predictions: Array<PredictionResult | null | undefined>,
): number {
  return predictions.reduce(
    (count, prediction) =>
      Math.max(count, prediction ? framesFromPrediction(prediction).length : 0),
    0,
  );
}
