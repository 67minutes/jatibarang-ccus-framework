import {
  getReservoir,
  getRoadLayers,
  getSpatialResult,
  getTerrainWindow,
} from "../api/client";
import { useFieldStore } from "../state/field.store";
import { useUiStore } from "../state/ui.store";
import { isLegacyMemo, isStudyMemo, type StudyMemo } from "./studyMemo";

/**
 * Load a study memo from a file the user picks. Prefers the File System Access
 * API, falling back to a hidden file input.
 */

interface FsWindow {
  showOpenFilePicker?: (options: unknown) => Promise<Array<{ getFile: () => Promise<File> }>>;
}

export async function pickStudyMemo(): Promise<StudyMemo | null> {
  const file = await pickFile();
  if (!file) return null;
  const text = await file.text();
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new Error("Selected file is not valid JSON.");
  }
  if (!isStudyMemo(parsed)) {
    throw new Error("Selected file is not a compatible study memo.");
  }
  await hydrateMemoFieldSetup(parsed);
  return parsed;
}

/**
 * Replace any live field with the memo's lightweight setup. Overview pixels
 * and reservoir runtime data are restored from their hash-addressed registries
 * when the referenced machine-local artifacts are still available.
 */
export async function hydrateMemoFieldSetup(memo: StudyMemo): Promise<void> {
  const field = useFieldStore.getState();
  const ui = useUiStore.getState();

  // A memo open is a replacement operation. Never leave objects from the
  // previously open study behind when the incoming memo has no field setup.
  field.reset();

  if (isLegacyMemo(memo)) {
    ui.pushBanner({
      id: "memo-legacy",
      severity: "info",
      message:
        "This memo predates field setups; opened read-only without a field scene.",
    });
    return;
  }

  ui.dismissBanner("memo-legacy");
  ui.dismissBanner("roads-relink");
  ui.dismissBanner("memo-spatial-relink");
  if (!memo.field_setup) return;

  field.hydrate(memo.field_setup);
  try {
    const overview = await getTerrainWindow(
      memo.field_setup.terrain.terrain_id,
      memo.field_setup.terrain.extent,
      512,
    );
    // A second open/reset may have completed while the overview was loading.
    // Only attach it if this memo's terrain is still the active field.
    const activeTerrain = useFieldStore.getState().terrain;
    if (
      activeTerrain?.terrain_id === memo.field_setup.terrain.terrain_id &&
      activeTerrain.sha256 === memo.field_setup.terrain.sha256
    ) {
      useFieldStore.setState({ overviewData: overview });
    }
  } catch {
    // The references and engineer-authored map edits are still useful when the
    // registry is offline. Opening the memo must not depend on raster loading.
  }

  try {
    const assignments =
      memo.field_setup.reservoir_assignments ?? {
        W01: memo.field_setup.reservoir,
      };
    const runtimes: Record<string, Awaited<ReturnType<typeof getReservoir>>> = {};
    for (const [wellId, reference] of Object.entries(assignments).sort(
      ([left], [right]) => left.localeCompare(right),
    )) {
      const runtime = await getReservoir(reference.model_id, reference.bank_id);
      const verified =
        runtime.sha256 === reference.sha256 &&
        (!reference.bank_sha256 ||
          runtime.launchpads.bank_sha256 === reference.bank_sha256);
      if (!verified) {
        throw new Error(`reservoir relink hash mismatch for ${wellId}`);
      }
      runtimes[wellId] = runtime;
    }
    const active = useFieldStore.getState().reservoir;
    const stillOpen = active?.model_id === memo.field_setup.reservoir.model_id;
    const primaryRuntime = Object.values(runtimes).find(
      (runtime) => runtime.model_id === memo.field_setup?.reservoir.model_id,
    );
    if (stillOpen && primaryRuntime) {
      useFieldStore.setState({
        reservoirRuntime: primaryRuntime,
        reservoirRuntimes: runtimes,
      });
      ui.dismissBanner("memo-reservoir-relink");
    }
  } catch {
    // The artifact may have been removed from data/imports. Keep the memo open;
    // the workbench banner explains how to restore screening capability.
  }

  if (memo.spatial_result) {
    try {
      const archive = await getSpatialResult(memo.spatial_result.artifact_id);
      const stillOpen =
        useFieldStore.getState().reservoir?.model_id ===
        memo.field_setup.reservoir.model_id;
      const verified =
        archive.sha256 === memo.spatial_result.sha256 &&
        archive.payload.request_fingerprint === memo.fingerprint &&
        memo.spatial_result.request_fingerprint === memo.fingerprint;
      if (!verified) {
        throw new Error("spatial-result archive hash or fingerprint mismatch");
      }
      if (stillOpen) {
        memo.result = {
          ...memo.result,
          detailed_predictions: archive.payload.detailed_predictions,
          detailed_reservoirs: archive.payload.detailed_reservoirs,
        };
      }
    } catch {
      ui.pushBanner({
        id: "memo-spatial-relink",
        severity: "info",
        message:
          "Detailed reservoir frames for this study could not be re-linked. Aggregate results remain available; re-run screening to restore plume playback.",
      });
    }
  } else if (
    Object.values(memo.result.detailed_predictions ?? {}).some(
      (prediction) => prediction.fields == null,
    )
  ) {
    ui.pushBanner({
      id: "memo-spatial-relink",
      severity: "info",
      message:
        "This older study memo has no spatial-result archive. Aggregate results remain available; re-run screening and save again to preserve plume playback.",
    });
  }

  if (memo.field_setup.roads) {
    try {
      const layers = await getRoadLayers(
        memo.field_setup.roads.road_network_id,
      );
      const active = useFieldStore.getState().roads;
      if (
        active?.road_network_id ===
        memo.field_setup.roads.road_network_id
      ) {
        useFieldStore.setState({ roadLayers: layers });
      }
    } catch {
      ui.pushBanner({
        id: "roads-relink",
        severity: "info",
        message:
          "The road network for this study could not be found; trucking falls back to the great-circle estimate until it is re-imported.",
      });
    }
  }
}

async function pickFile(): Promise<File | null> {
  const fsWindow = window as unknown as FsWindow;
  if (fsWindow.showOpenFilePicker) {
    try {
      const [handle] = await fsWindow.showOpenFilePicker({
        types: [{ description: "Study memo", accept: { "application/json": [".json"] } }],
        multiple: false,
      });
      return await handle.getFile();
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return null;
      // Fall through to input fallback.
    }
  }
  return new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "application/json,.json";
    input.onchange = () => resolve(input.files?.[0] ?? null);
    input.oncancel = () => resolve(null);
    input.click();
  });
}
