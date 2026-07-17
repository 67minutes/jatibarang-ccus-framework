import type { LedgerEntry } from "./studyMemo";
import { entryToMemo } from "./studyMemo";
import { APP_VERSION, API_CONTRACT_VERSION } from "../version";
import type { ScreenResult } from "../api/types";

/**
 * Study-memo and CSV export. Uses the File System Access API when available,
 * falling back to a download. No browser storage — the file is the durable
 * state (design §7.5).
 */

interface FsWindow {
  showSaveFilePicker?: (options: unknown) => Promise<{
    createWritable: () => Promise<{ write: (data: Blob) => Promise<void>; close: () => Promise<void> }>;
  }>;
}

async function saveBlob(blob: Blob, suggestedName: string, mime: string): Promise<void> {
  const fsWindow = window as unknown as FsWindow;
  if (fsWindow.showSaveFilePicker) {
    try {
      const handle = await fsWindow.showSaveFilePicker({
        suggestedName,
        types: [{ description: suggestedName, accept: { [mime]: [suggestedName.slice(suggestedName.lastIndexOf("."))] } }],
      });
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
      return;
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      // Fall through to download on any picker failure.
    }
  }
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = suggestedName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export async function exportStudyMemo(entry: LedgerEntry): Promise<void> {
  const memo = entryToMemo(entry, APP_VERSION, API_CONTRACT_VERSION);
  const blob = new Blob([JSON.stringify(memo, null, 2)], { type: "application/json" });
  const name = entry.study?.memo_file_name || `${sanitize(entry.label)}.study.json`;
  await saveBlob(blob, name, "application/json");
}

export function rankingToCsv(result: ScreenResult): string {
  const header = ["rank", "candidate_id", "scenario_id", "carbon_prices", "designated_npv_usd", "reasons"];
  const rows = result.shortlist.map((item) =>
    [
      item.rank,
      item.candidate_id,
      item.scenario_id,
      item.carbon_price_scenario_ids.join("|"),
      item.designated_npv_usd ?? "",
      item.reasons.join("; ").replace(/"/g, "'"),
    ]
      .map((v) => (typeof v === "string" && v.includes(",") ? `"${v}"` : String(v)))
      .join(","),
  );
  return [header.join(","), ...rows].join("\n");
}

export async function exportRankingCsv(result: ScreenResult, label: string): Promise<void> {
  const blob = new Blob([rankingToCsv(result)], { type: "text/csv" });
  await saveBlob(blob, `${sanitize(label)}-ranking.csv`, "text/csv");
}

function sanitize(name: string): string {
  return name.replace(/[^a-z0-9._-]+/gi, "_").slice(0, 80) || "study";
}
