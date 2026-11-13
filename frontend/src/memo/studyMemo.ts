import type {
  InlineScreenRequest,
  ScreenRequest,
  ScreenResult,
} from "../api/types";
import type {
  FieldPlacement,
  PlacedSource,
  PlacedWell,
  ReservoirRef,
  RoadsRef,
  TerrainRef,
} from "../state/field.store";
import type { StudyMetadata } from "../state/study.store";

/**
 * A study memo is the workbench's unit of durable state (design §7.5).
 *
 * It is simultaneously the persistence mechanism (no browser storage — the file
 * IS the state), the collaboration unit (a colleague imports it), the
 * reproducibility contract (re-compose -> run -> same fingerprint or the inputs
 * changed), and the Feature 007 hand-off artifact. Field memos retain a
 * decision-request summary and artifact hashes, while geology/launch-pad
 * payloads stay in the backend import registry rather than bloating the file.
 */

export const STUDY_MEMO_KIND = "jatibarang.ccus.study-memo";
export const STUDY_MEMO_VERSION = 4;
const FIELD_SETUP_MEMO_VERSION = 3;

/** Content-addressed companion containing detailed cell arrays for playback. */
export interface SpatialResultRef {
  artifact_id: string;
  sha256: string;
  request_fingerprint: string;
}

/**
 * Portable, lightweight field setup. Imported raster/model payloads remain
 * hash-addressed backend artifacts; the memo stores their references and the
 * engineer's map edits, not the binary payloads.
 */
export interface FieldSetupMemo {
  terrain: TerrainRef;
  reservoir: ReservoirRef;
  reservoir_assignments?: Record<string, ReservoirRef>;
  roads?: RoadsRef | null;
  placement: FieldPlacement;
  wells: PlacedWell[];
  sources: PlacedSource[];
}

interface StudyMemoBase {
  kind: typeof STUDY_MEMO_KIND;
  memo_version: number;
  app_version: string;
  api_contract_version: string;
  saved_at: string;
  label: string;
  study?: StudyMetadata;
  field_setup?: FieldSetupMemo;
  spatial_result?: SpatialResultRef;
  fingerprint: string;
  result: ScreenResult;
}

/**
 * Decision-facing request metadata retained in a portable field memo. The two
 * required API catalogs are absent, so this type cannot be submitted as an
 * InlineScreenRequest. The referenced reservoir hashes remain in field_setup.
 */
export type ArtifactReferencedRequestSummary = Omit<
  InlineScreenRequest,
  "geologies" | "seeds"
> & {
  geologies?: never;
  seeds?: never;
};

export type StudyMemo = StudyMemoBase &
  (
    | {
        request_payload_mode?: "embedded";
        result_payload_mode?: "full";
        request: ScreenRequest;
      }
    | {
        request_payload_mode: "artifact_referenced";
        /** Older v3 files may contain a full result; new exports are summaries. */
        result_payload_mode?: "full" | "summary";
        request: ArtifactReferencedRequestSummary;
      }
  );

/** A run held in the session ledger (in-memory; exportable as a StudyMemo). */
interface LedgerEntryBase {
  /** Stable id for UI keys; the fingerprint is the scientific identity. */
  entryId: string;
  fingerprint: string;
  label: string;
  savedAt: string;
  result: ScreenResult;
  /** True when loaded from a saved memo rather than a live run. */
  imported: boolean;
  study?: StudyMetadata;
}

export type LedgerEntry = LedgerEntryBase &
  (
    | {
        requestPayloadMode?: "embedded";
        resultPayloadMode?: "full";
        request: ScreenRequest;
      }
    | {
        /** Result summaries are inspectable but cannot be recomposed. */
        requestPayloadMode: "artifact_referenced";
        resultPayloadMode?: "full" | "summary";
        request: ArtifactReferencedRequestSummary;
      }
  );

export function shortFingerprint(fingerprint: string): string {
  return fingerprint ? fingerprint.slice(0, 8).toLowerCase() : "--------";
}

export function isStudyMemo(value: unknown): value is StudyMemo {
  if (!value || typeof value !== "object") return false;
  const memo = value as Record<string, unknown>;
  if (!(
    memo.kind === STUDY_MEMO_KIND &&
    typeof memo.fingerprint === "string" &&
    memo.request !== null &&
    typeof memo.request === "object" &&
    memo.result !== null &&
    typeof memo.result === "object"
  )) {
    return false;
  }
  if (
    (memo.request_payload_mode !== undefined &&
      memo.request_payload_mode !== "embedded" &&
      memo.request_payload_mode !== "artifact_referenced") ||
    (memo.result_payload_mode !== undefined &&
      memo.result_payload_mode !== "full" &&
      memo.result_payload_mode !== "summary")
  ) {
    return false;
  }
  if (memo.spatial_result !== undefined) {
    if (!memo.spatial_result || typeof memo.spatial_result !== "object") {
      return false;
    }
    const spatial = memo.spatial_result as Record<string, unknown>;
    if (
      typeof spatial.artifact_id !== "string" ||
      typeof spatial.sha256 !== "string" ||
      typeof spatial.request_fingerprint !== "string"
    ) {
      return false;
    }
  }

  if (memo.request_payload_mode === "artifact_referenced") {
    const request = memo.request as Record<string, unknown>;
    const omittedOrEmptyCatalog = (catalog: unknown) =>
      catalog === undefined ||
      (catalog !== null &&
        typeof catalog === "object" &&
        Object.keys(catalog).length === 0);
    return (
      (memo.result_payload_mode === undefined ||
        memo.result_payload_mode === "summary") &&
      memo.field_setup !== null &&
      typeof memo.field_setup === "object" &&
      request.mode === "inline" &&
      omittedOrEmptyCatalog(request.geologies) &&
      omittedOrEmptyCatalog(request.seeds)
    );
  }

  return memo.result_payload_mode !== "summary";
}

/** Version-2 and older memos remain readable but have no field-scene state. */
export function isLegacyMemo(memo: Pick<StudyMemo, "memo_version">): boolean {
  return memo.memo_version < FIELD_SETUP_MEMO_VERSION;
}

export function memoToEntry(memo: StudyMemo, imported: boolean): LedgerEntry {
  const common: LedgerEntryBase = {
    entryId: crypto.randomUUID(),
    fingerprint: memo.fingerprint,
    label: memo.label || shortFingerprint(memo.fingerprint),
    savedAt: memo.saved_at,
    result: memo.result,
    imported,
    study: memo.study,
  };
  if (memo.request_payload_mode === "artifact_referenced") {
    return {
      ...common,
      request: artifactRequestSummary(memo.request),
      requestPayloadMode: "artifact_referenced",
      resultPayloadMode: memo.result_payload_mode ?? "full",
    };
  }
  return {
    ...common,
    request: memo.request,
    requestPayloadMode: "embedded",
    resultPayloadMode: "full",
  };
}

export function entryToMemo(
  entry: LedgerEntry,
  appVersion: string,
  apiContractVersion: string,
  fieldSetup?: FieldSetupMemo,
  spatialResult?: SpatialResultRef,
): StudyMemo {
  if (entry.requestPayloadMode === "artifact_referenced") {
    const request = structuredClone(entry.request);
    if (!fieldSetup || request.mode !== "inline") {
      throw new Error("An artifact-referenced memo requires a field setup.");
    }
    return {
      kind: STUDY_MEMO_KIND,
      memo_version: STUDY_MEMO_VERSION,
      app_version: appVersion,
      api_contract_version: apiContractVersion,
      saved_at: new Date().toISOString(),
      label: entry.label,
      study: entry.study,
      field_setup: fieldSetup,
      spatial_result: spatialResult,
      request_payload_mode: "artifact_referenced",
      result_payload_mode: "summary",
      request: artifactRequestSummary(request),
      fingerprint: entry.fingerprint,
      result: summarizeFieldResult(entry.result),
    };
  }

  const request = structuredClone(entry.request);
  if (fieldSetup && request.mode === "inline") {
    return {
      kind: STUDY_MEMO_KIND,
      memo_version: STUDY_MEMO_VERSION,
      app_version: appVersion,
      api_contract_version: apiContractVersion,
      saved_at: new Date().toISOString(),
      label: entry.label,
      study: entry.study,
      field_setup: fieldSetup,
      spatial_result: spatialResult,
      request_payload_mode: "artifact_referenced",
      result_payload_mode: "summary",
      request: artifactRequestSummary(request),
      fingerprint: entry.fingerprint,
      result: summarizeFieldResult(entry.result),
    };
  }

  return {
    kind: STUDY_MEMO_KIND,
    memo_version: STUDY_MEMO_VERSION,
    app_version: appVersion,
    api_contract_version: apiContractVersion,
    saved_at: new Date().toISOString(),
    label: entry.label,
    study: entry.study,
    field_setup: fieldSetup,
    spatial_result: spatialResult,
    request_payload_mode: "embedded",
    result_payload_mode: "full",
    request,
    fingerprint: entry.fingerprint,
    result: entry.result,
  };
}

/** Strip legacy empty catalogs and return a non-submittable request summary. */
function artifactRequestSummary(
  request: InlineScreenRequest | ArtifactReferencedRequestSummary,
): ArtifactReferencedRequestSummary {
  const {
    geologies: _geologies,
    seeds: _seeds,
    ...summary
  } = request as InlineScreenRequest;
  return summary;
}

/**
 * Keep decision-facing outputs portable while leaving cell-by-cell arrays in
 * the hash-addressed reservoir import. Aggregate timelines, production,
 * inventory, plume summaries, economics, warnings, and fingerprints remain in
 * the memo. A new import-backed study is required to regenerate spatial fields.
 */
function summarizeFieldResult(result: ScreenResult): ScreenResult {
  const detailedPredictions = Object.fromEntries(
    Object.entries(result.detailed_predictions ?? {}).map(
      ([scenarioId, prediction]) => [
        scenarioId,
        { ...prediction, fields: null },
      ],
    ),
  );
  const plans = (result.plans ?? []).map((plan) => ({
    ...plan,
    well_strategies: plan.well_strategies.map((strategy) => ({
      ...strategy,
      prediction: { ...strategy.prediction, fields: null },
    })),
  }));
  return {
    ...result,
    plans,
    detailed_predictions: detailedPredictions,
    detailed_reservoirs: {},
  };
}
