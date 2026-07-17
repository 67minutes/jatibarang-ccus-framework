import type { ScreenRequest, ScreenResult } from "../api/types";
import type {
  FieldPlacement,
  PlacedSource,
  PlacedWell,
  ReservoirRef,
  TerrainRef,
} from "../state/field.store";
import type { StudyMetadata } from "../state/study.store";

/**
 * A study memo is the workbench's unit of durable state (design §7.5).
 *
 * It is simultaneously the persistence mechanism (no browser storage — the file
 * IS the state), the collaboration unit (a colleague imports it), the
 * reproducibility contract (re-compose -> run -> same fingerprint or the inputs
 * changed), and the Feature 007 hand-off artifact. Field memos retain the
 * decision request and artifact hashes, while relinkable geology/launch-pad
 * payloads stay in the backend import registry rather than bloating the file.
 */

export const STUDY_MEMO_KIND = "jatibarang.ccus.study-memo";
export const STUDY_MEMO_VERSION = 3;

/**
 * Portable, lightweight field setup. Imported raster/model payloads remain
 * hash-addressed backend artifacts; the memo stores their references and the
 * engineer's map edits, not the binary payloads.
 */
export interface FieldSetupMemo {
  terrain: TerrainRef;
  reservoir: ReservoirRef;
  placement: FieldPlacement;
  wells: PlacedWell[];
  sources: PlacedSource[];
}

export interface StudyMemo {
  kind: typeof STUDY_MEMO_KIND;
  memo_version: number;
  app_version: string;
  api_contract_version: string;
  saved_at: string;
  label: string;
  study?: StudyMetadata;
  field_setup?: FieldSetupMemo;
  /** Older/non-field memos may embed payloads; field memos reference artifacts. */
  request_payload_mode?: "embedded" | "artifact_referenced";
  request: ScreenRequest;
  fingerprint: string;
  result: ScreenResult;
}

/** A run held in the session ledger (in-memory; exportable as a StudyMemo). */
export interface LedgerEntry {
  /** Stable id for UI keys; the fingerprint is the scientific identity. */
  entryId: string;
  fingerprint: string;
  label: string;
  savedAt: string;
  request: ScreenRequest;
  result: ScreenResult;
  /** True when loaded from a canned/imported memo rather than a live run. */
  imported: boolean;
  study?: StudyMetadata;
}

export function shortFingerprint(fingerprint: string): string {
  return fingerprint ? fingerprint.slice(0, 8).toLowerCase() : "--------";
}

export function isStudyMemo(value: unknown): value is StudyMemo {
  if (!value || typeof value !== "object") return false;
  const memo = value as Record<string, unknown>;
  return (
    memo.kind === STUDY_MEMO_KIND &&
    typeof memo.fingerprint === "string" &&
    typeof memo.request === "object" &&
    typeof memo.result === "object"
  );
}

/** Version-2 and older memos remain readable but have no field-scene state. */
export function isLegacyMemo(memo: Pick<StudyMemo, "memo_version">): boolean {
  return memo.memo_version < STUDY_MEMO_VERSION;
}

export function memoToEntry(memo: StudyMemo, imported: boolean): LedgerEntry {
  return {
    entryId: crypto.randomUUID(),
    fingerprint: memo.fingerprint,
    label: memo.label || shortFingerprint(memo.fingerprint),
    savedAt: memo.saved_at,
    request: memo.request,
    result: memo.result,
    imported,
    study: memo.study,
  };
}

export function entryToMemo(
  entry: LedgerEntry,
  appVersion: string,
  apiContractVersion: string,
  fieldSetup?: FieldSetupMemo,
): StudyMemo {
  const request = structuredClone(entry.request);
  const artifactReferenced = Boolean(
    fieldSetup && request.mode === "inline",
  );
  if (artifactReferenced && request.mode === "inline") {
    // Candidates, sources, decisions, and schedule selection remain readable.
    // The model/bank hashes in field_setup are the portable link contract.
    request.geologies = {};
    request.seeds = {};
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
    request_payload_mode: artifactReferenced
      ? "artifact_referenced"
      : "embedded",
    request,
    fingerprint: entry.fingerprint,
    result: entry.result,
  };
}
