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
 * Load a study memo from a file the user picks with the browser's classic
 * file chooser (see pickFile for why not the File System Access API).
 */

export async function pickStudyMemo(): Promise<StudyMemo | null> {
  const file = await pickFile();
  if (!file) {
    console.info("[open-study] picker cancelled");
    return null;
  }
  return openStudyMemoFile(file);
}

/**
 * Load a study memo served next to the app (frontend/public/studies/), so a
 * demo machine can open a study from a link without the OS file dialog:
 * http://127.0.0.1:5173/?study=geopetra-demo
 */
export async function fetchStudyMemo(name: string): Promise<StudyMemo> {
  const safe = name.replace(/[^A-Za-z0-9._-]/g, "");
  const fileName = safe.endsWith(".json") ? safe : `${safe}.study.json`;
  console.info(`[open-study] fetching studies/${fileName}`);
  const response = await fetch(`/studies/${fileName}`);
  // The dev server and the FastAPI static mount answer unknown paths with the
  // app's index.html, so an HTML response also means "no such study".
  if (!response.ok || (response.headers.get("content-type") ?? "").includes("text/html")) {
    throw new Error(
      `Study "${fileName}" was not found in frontend/public/studies (HTTP ${response.status}).`,
    );
  }
  const blob = await response.blob();
  return openStudyMemoFile(new File([blob], fileName));
}

/** Validate a memo file and re-link its field setup. */
export async function openStudyMemoFile(file: File): Promise<StudyMemo> {
  console.info(`[open-study] picked ${file.name} (${file.size} bytes)`);
  // Reading a large memo and re-linking terrain, reservoirs and the spatial
  // archive takes several seconds; say so at once, or the open looks like it
  // did nothing.
  const ui = useUiStore.getState();
  ui.dismissBanner("open-failed");
  ui.pushBanner({
    id: "memo-opening",
    severity: "info",
    message: `Opening ${file.name}… re-linking terrain, reservoirs and results.`,
  });
  try {
    let text: string;
    try {
      text = await file.text();
    } catch (err) {
      throw new Error(
        `Could not read ${file.name}${err instanceof Error ? ` (${err.message})` : ""}. ` +
          "Copy the file to a local folder such as Documents and open it from there.",
      );
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      throw new Error("Selected file is not valid JSON.");
    }
    if (!isStudyMemo(parsed)) {
      throw new Error("Selected file is not a compatible study memo.");
    }
    console.info("[open-study] memo valid; re-linking field setup");
    await hydrateMemoFieldSetup(parsed);
    console.info("[open-study] field setup re-linked");
    return parsed;
  } catch (err) {
    console.error("[open-study] failed", err);
    throw err;
  } finally {
    useUiStore.getState().dismissBanner("memo-opening");
  }
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
    const entries = Object.entries(assignments).sort(([left], [right]) =>
      left.localeCompare(right),
    );
    // Fetch in parallel (a 20-well study is 20 round trips), then verify in
    // well order so the first mismatch reported is deterministic.
    const fetched = await Promise.all(
      entries.map(([, reference]) =>
        getReservoir(reference.model_id, reference.bank_id),
      ),
    );
    entries.forEach(([wellId, reference], index) => {
      const runtime = fetched[index];
      const verified =
        runtime.sha256 === reference.sha256 &&
        (!reference.bank_sha256 ||
          runtime.launchpads.bank_sha256 === reference.bank_sha256);
      if (!verified) {
        throw new Error(`reservoir relink hash mismatch for ${wellId}`);
      }
      runtimes[wellId] = runtime;
    });
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
  // Use the classic file input, not showOpenFilePicker. On some Windows
  // machines the File System Access picker silently rejects a file clicked in
  // the dialog (it reports AbortError, indistinguishable from Cancel), while
  // the classic chooser opens the same file. Opening only needs to read the
  // file once, so the file handle the newer API provides is not needed.
  return new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".json,application/json";
    input.style.display = "none";
    const finish = (file: File | null) => {
      input.remove();
      resolve(file);
    };
    input.addEventListener("change", () => finish(input.files?.[0] ?? null), { once: true });
    input.addEventListener("cancel", () => finish(null), { once: true });
    document.body.appendChild(input);
    input.click();
  });
}
