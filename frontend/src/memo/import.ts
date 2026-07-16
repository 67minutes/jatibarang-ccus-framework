import { isStudyMemo, type StudyMemo } from "./studyMemo";

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
  return parsed;
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
