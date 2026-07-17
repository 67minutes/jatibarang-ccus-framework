import { getTerrainWindow } from "../api/client";
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
    throw new Error("Selected file is not a Jatibarang study memo.");
  }
  await hydrateMemoFieldSetup(parsed);
  return parsed;
}

/**
 * Replace any live field with the memo's lightweight setup. Overview pixels
 * are re-linked from the terrain registry; reservoir runtime data remains
 * intentionally unavailable until the user re-imports the model and bank.
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
