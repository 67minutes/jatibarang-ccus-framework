import type { FieldSetupMemo, LedgerEntry } from "./studyMemo";
import { entryToMemo } from "./studyMemo";
import { APP_VERSION, API_CONTRACT_VERSION } from "../version";
import { archiveSpatialResult } from "../api/client";
import type { ScreenResult } from "../api/types";
import { useFieldStore } from "../state/field.store";

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
  const hasSpatialResult =
    Object.keys(entry.result.detailed_reservoirs ?? {}).length > 0 &&
    Object.values(entry.result.detailed_predictions ?? {}).some(
      (prediction) => (prediction.fields?.length ?? 0) > 0,
    );
  const spatial = hasSpatialResult
    ? await archiveSpatialResult(entry.result)
    : undefined;
  const memo = entryToMemo(
    entry,
    APP_VERSION,
    API_CONTRACT_VERSION,
    snapshotFieldSetup(),
    spatial
      ? {
          artifact_id: spatial.artifact_id,
          sha256: spatial.sha256,
          request_fingerprint: spatial.request_fingerprint,
        }
      : undefined,
  );
  const blob = new Blob([JSON.stringify(memo, null, 2)], { type: "application/json" });
  const name = entry.study?.memo_file_name || `${sanitize(entry.label)}.study.json`;
  await saveBlob(blob, name, "application/json");
}

/**
 * Capture only portable field references and engineer-authored placement.
 * Runtime terrain pixels, reservoir arrays, and launch-pad payloads remain in
 * their hash-addressed backend registries and are deliberately not memo data.
 */
export function snapshotFieldSetup(): FieldSetupMemo | undefined {
  const { terrain, reservoir, reservoirAssignments, roads, placement, wells, sources } =
    useFieldStore.getState();
  if (!terrain || !reservoir || !placement) return undefined;

  return {
    terrain: {
      ...terrain,
      extent: { ...terrain.extent },
    },
    reservoir: {
      ...reservoir,
      covered_fingerprints: [...reservoir.covered_fingerprints],
      well_ij: [...reservoir.well_ij],
    },
    reservoir_assignments: Object.fromEntries(
      Object.entries(reservoirAssignments).map(([wellId, reference]) => [
        wellId,
        {
          ...reference,
          covered_fingerprints: [...reference.covered_fingerprints],
          well_ij: [...reference.well_ij],
        },
      ]),
    ),
    roads: roads ? { ...roads } : null,
    placement: { ...placement },
    wells: wells.map((well) => ({ ...well })),
    sources: sources.map((source) => ({ ...source })),
  };
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

export interface MrstResimulationPlan {
  schema_version: "1.0";
  purpose: "offline_mrst_top_k_confirmation";
  runtime_mrst_forbidden: true;
  raw_training_corpus_copied: false;
  selection_basis: "development_shortlist" | "pre_logistics_non_development_ranking";
  development_selection_claimed: boolean;
  request_fingerprint: string;
  entries: Array<{
    rank: number;
    candidate_id: string;
    scenario_id: string;
    carbon_price_scenario_ids: string[];
    development_selected: boolean;
    schedule: Record<string, number>;
    reservoir: {
      model_id: string;
      sha256: string;
      source_file: string;
      bank_id: string | null;
      bank_sha256: string | null;
    } | null;
    location: { latitude: number; longitude: number } | null;
  }>;
}

/** Build a compact handoff for top-K confirmation in the upstream MRST repo. */
export function buildMrstResimulationPlan(
  entry: LedgerEntry,
  fieldSetup: FieldSetupMemo | undefined = snapshotFieldSetup(),
): MrstResimulationPlan {
  const candidates = new Map<
    string,
    { candidate_id: string; location: { latitude: number; longitude: number } }
  >();
  if (entry.request.mode === "inline") {
    for (const raw of entry.request.candidates) {
      const item = raw as {
        candidate_id?: unknown;
        location?: { latitude?: unknown; longitude?: unknown };
      };
      if (
        typeof item.candidate_id === "string" &&
        typeof item.location?.latitude === "number" &&
        typeof item.location.longitude === "number"
      ) {
        candidates.set(item.candidate_id, {
          candidate_id: item.candidate_id,
          location: {
            latitude: item.location.latitude,
            longitude: item.location.longitude,
          },
        });
      }
    }
  }
  const strategies = new Map(
    entry.result.plans.flatMap((plan) =>
      plan.well_strategies.map((strategy) => [strategy.scenario_id, strategy] as const),
    ),
  );
  const assignments = fieldSetup?.reservoir_assignments ?? (
    fieldSetup ? { W01: fieldSetup.reservoir } : {}
  );
  const fallbackPlan = [...entry.result.plans].sort(
    (a, b) => b.carbon_price_usd_per_tonne - a.carbon_price_usd_per_tonne,
  )[0];
  const requestedTopK = entry.request.mode === "inline"
    ? (entry.request.shortlist_top_k ?? 5)
    : 5;
  const fallbackRows = fallbackPlan
    ? [...fallbackPlan.well_strategies]
        .sort((a, b) => b.preliminary_npv_usd - a.preliminary_npv_usd)
        .filter(
          (strategy, index, rows) =>
            rows.findIndex((item) => item.candidate_id === strategy.candidate_id) === index,
        )
        .slice(0, requestedTopK)
        .map((strategy, index) => ({
          rank: index + 1,
          candidate_id: strategy.candidate_id,
          scenario_id: strategy.scenario_id,
          carbon_price_scenario_ids: [fallbackPlan.carbon_price_scenario_id],
          development_selected: false,
        }))
    : [];
  const exportRows = entry.result.shortlist.length > 0
    ? entry.result.shortlist.map((item) => ({
        ...item,
        development_selected: true,
      }))
    : fallbackRows;
  return {
    schema_version: "1.0",
    purpose: "offline_mrst_top_k_confirmation",
    runtime_mrst_forbidden: true,
    raw_training_corpus_copied: false,
    selection_basis: entry.result.shortlist.length > 0
      ? "development_shortlist"
      : "pre_logistics_non_development_ranking",
    development_selection_claimed: entry.result.shortlist.length > 0,
    request_fingerprint: entry.result.request_fingerprint,
    entries: exportRows.map((item) => {
      const strategy = strategies.get(item.scenario_id);
      const reservoir = assignments[item.candidate_id] ?? fieldSetup?.reservoir ?? null;
      const candidate = candidates.get(item.candidate_id);
      return {
        rank: item.rank,
        candidate_id: item.candidate_id,
        scenario_id: item.scenario_id,
        carbon_price_scenario_ids: [...item.carbon_price_scenario_ids],
        development_selected: item.development_selected,
        schedule: strategy ? { ...strategy.schedule } : {},
        reservoir: reservoir
          ? {
              model_id: reservoir.model_id,
              sha256: reservoir.sha256,
              source_file: reservoir.source_file,
              bank_id: reservoir.bank_id,
              bank_sha256: reservoir.bank_sha256,
            }
          : null,
        location: candidate ? { ...candidate.location } : null,
      };
    }),
  };
}

export async function exportMrstResimulationPlan(
  entry: LedgerEntry,
): Promise<void> {
  const plan = buildMrstResimulationPlan(entry);
  const blob = new Blob([JSON.stringify(plan, null, 2)], { type: "application/json" });
  await saveBlob(
    blob,
    `${sanitize(entry.study?.name ?? entry.label)}-mrst-resimulation-plan.json`,
    "application/json",
  );
}

function sanitize(name: string): string {
  return name.replace(/[^a-z0-9._-]+/gi, "_").slice(0, 80) || "study";
}
