import { useEffect, useRef } from "react";
import { ApiError, deleteRun, postScreen } from "../api/client";
import { streamScreen } from "../api/sse";
import type { InlineScreenRequest, ScreenRequest, ScreenResult } from "../api/types";
import { useActionsStore } from "../state/actions.store";
import { useComposeStore } from "../compose/compose.store";
import { useLedgerStore } from "../state/ledger.store";
import { useRunStore } from "../state/run.store";
import { useSelectionStore } from "../state/selection.store";
import { useUiStore } from "../state/ui.store";
import { useWorkspaceStore } from "../state/workspace.store";
import { validateDraft } from "../compose/validation";
import { exportRankingCsv, exportStudyMemo } from "../memo/export";
import { pickStudyMemo } from "../memo/import";
import { carbonPriceAxis } from "../results/priceScrubber";
import { useStudyStore } from "../state/study.store";
import { exportViewportSnapshot } from "../viewport/snapshot";
import { isLegacyMemo, shortFingerprint } from "../memo/studyMemo";
import type { FieldSetupMemo } from "../memo/studyMemo";
import { useFieldStore } from "../state/field.store";
import { createDefaultStudyRequestBase } from "../compose/defaults";
import {
  buildStudyRequest,
  NoCoveredSchedulesError,
  sourceValidationIssue,
} from "../compose/studyRequest";

/** Watchdog: mark the run stalled if no event arrives within this window. */
const STALL_TIMEOUT_MS = 20_000;

interface ScreeningIssue {
  bannerId: string;
  message: string;
}

export interface ScreeningPreparation {
  request: InlineScreenRequest | null;
  issue: ScreeningIssue | null;
}

const PREPARATION_BANNERS = [
  "compose-invalid",
  "coverage-empty",
  "reservoir-relink-required",
  "source-required",
  "source-invalid",
] as const;

function currentFieldSetup(): FieldSetupMemo | null {
  const state = useFieldStore.getState();
  const hasAnyFieldState = Boolean(
    state.terrain || state.reservoir || state.placement,
  );
  if (!hasAnyFieldState) return null;
  if (!state.terrain || !state.reservoir || !state.placement) {
    throw new Error("The field setup is incomplete; reopen New Study.");
  }
  return {
    terrain: {
      ...state.terrain,
      extent: { ...state.terrain.extent },
    },
    reservoir: {
      ...state.reservoir,
      well_ij: [...state.reservoir.well_ij],
      covered_fingerprints: [...state.reservoir.covered_fingerprints],
    },
    roads: state.roads ? { ...state.roads } : null,
    placement: { ...state.placement },
    wells: state.wells.map((well) => ({ ...well })),
    sources: state.sources.map((source) => ({ ...source })),
  };
}

function failedPreparation(
  bannerId: string,
  message: string,
): ScreeningPreparation {
  return { request: null, issue: { bannerId, message } };
}

/**
 * Resolve the exact request that Screen would submit from the current stores.
 * This is shared by command enablement and execution so no UI path can submit
 * stale wells, sources, geology, or launch-pad coverage.
 */
export function prepareScreeningRequest(
  draft: InlineScreenRequest | null,
): ScreeningPreparation {
  if (!draft) {
    return failedPreparation("compose-invalid", "Create or open a study before screening.");
  }

  try {
    const field = currentFieldSetup();
    let request = draft;
    if (field) {
      const imported = useFieldStore.getState().reservoirRuntime;
      if (!imported) {
        return failedPreparation(
          "reservoir-relink-required",
          "This saved field is a read-only result summary. Create a new study and re-import the reservoir model before screening.",
        );
      }
      if (field.sources.length === 0) {
        return failedPreparation(
          "source-required",
          "Add at least one CO2 source in the basin view before screening.",
        );
      }
      const sourceIssue = sourceValidationIssue(field.sources);
      if (sourceIssue) {
        return failedPreparation("source-invalid", sourceIssue);
      }
      request = buildStudyRequest({
        field,
        imported,
        base: draft,
        scheduleMode: "covered",
      });
    }

    const report = validateDraft(request);
    if (!report.valid) {
      return failedPreparation(
        "compose-invalid",
        `Cannot screen: ${report.errors.length} validation issue(s) in the composer.`,
      );
    }
    return { request, issue: null };
  } catch (error) {
    if (error instanceof NoCoveredSchedulesError) {
      return failedPreparation("coverage-empty", error.message);
    }
    return failedPreparation(
      "compose-invalid",
      error instanceof Error ? error.message : "The screening request could not be built.",
    );
  }
}

function clearPreparationBanners(): void {
  const ui = useUiStore.getState();
  for (const id of PREPARATION_BANNERS) ui.dismissBanner(id);
}

/**
 * The workbench controller. Owns run execution (SSE + watchdog + sync
 * fallback) and wires every menu/toolbar action into the registry. Studies are
 * loaded explicitly through New/Open; mount performs no study-asset fetches.
 * Actions read fresh store state so they never go stale.
 */
export function useWorkbench(): void {
  const abortRef = useRef<AbortController | null>(null);
  const watchdogRef = useRef<number | null>(null);

  // Register the action surface once; blank boot performs no study-data load.
  useEffect(() => {
    function clearWatchdog() {
      if (watchdogRef.current != null) {
        window.clearInterval(watchdogRef.current);
        watchdogRef.current = null;
      }
    }

    function armWatchdog() {
      clearWatchdog();
      watchdogRef.current = window.setInterval(() => {
        const run = useRunStore.getState();
        if (run.status !== "running") return;
        if (run.lastEventAt && Date.now() - run.lastEventAt > STALL_TIMEOUT_MS) {
          run.markStalled();
        }
      }, 2_000);
    }

    function onResult(request: ScreenRequest, result: ScreenResult) {
      const study = useStudyStore.getState().study;
      const entry = useLedgerStore.getState().recordRun(request, result, {
        label: `${study.name} \u00b7 ${shortFingerprint(result.request_fingerprint)}`,
        study,
      });
      useRunStore.getState().finish("completed");
      // Default the scrubber to the lowest carbon price and open the ranking.
      const axis = carbonPriceAxis(result);
      if (axis.length > 0) useSelectionStore.getState().setCarbonPrice(axis[0].scenarioId);
      useSelectionStore.getState().clear();
      useWorkspaceStore.getState().setActiveTab("ranking");
      void entry;
    }

    function onFailure(error: unknown) {
      clearWatchdog();
      mapErrorToUi(error);
      const message = error instanceof Error ? error.message : String(error);
      useRunStore.getState().finish("failed", message);
    }

    async function runStream(request: ScreenRequest) {
      const runId = request.run_id as string;
      const controller = new AbortController();
      abortRef.current = controller;
      useRunStore.getState().begin(runId);
      useWorkspaceStore.getState().setActiveTab("run");
      armWatchdog();
      try {
        await streamScreen(
          request,
          {
            onEvent: (event) => useRunStore.getState().pushEvent(event),
            onResult: (result) => {
              clearWatchdog();
              onResult(request, result);
            },
            onError: onFailure,
            onCancelled: () => {
              clearWatchdog();
              useRunStore.getState().finish("cancelled");
            },
          },
          controller.signal,
        );
      } catch (streamErr) {
        // Stream failed to connect — fall back to the synchronous endpoint.
        if (streamErr instanceof ApiError) return onFailure(streamErr);
        try {
          const result = await postScreen(request);
          clearWatchdog();
          onResult(request, result);
        } catch (syncErr) {
          onFailure(syncErr);
        }
      } finally {
        abortRef.current = null;
      }
    }

    function screen() {
      const draft = useComposeStore.getState().draft;
      const run = useRunStore.getState();
      if (run.status === "running" || run.status === "stalled") return;
      const prepared = prepareScreeningRequest(draft);
      if (!prepared.request || prepared.issue) {
        useWorkspaceStore.getState().setActiveTab("compose");
        useUiStore.getState().pushBanner({
          id: prepared.issue?.bannerId ?? "compose-invalid",
          severity: "warning",
          message: prepared.issue?.message ?? "The screening request is not ready.",
        });
        return;
      }
      clearPreparationBanners();
      const request: ScreenRequest = {
        ...prepared.request,
        run_id: crypto.randomUUID(),
      };
      void runStream(request);
    }

    async function cancelRun() {
      const run = useRunStore.getState();
      if (run.runId) {
        try {
          await deleteRun(run.runId);
        } catch {
          /* best effort */
        }
      }
      abortRef.current?.abort();
    }

    // Register the full action surface for the command registry.
    useActionsStore.getState().register({
      screen,
      cancelRun,
      canScreen: () => {
        const status = useRunStore.getState().status;
        return (
          status !== "running" &&
          status !== "stalled" &&
          prepareScreeningRequest(useComposeStore.getState().draft).request !== null
        );
      },
      canCancel: () => {
        const status = useRunStore.getState().status;
        return status === "running" || status === "stalled";
      },
      hasActiveResult: () => useLedgerStore.getState().activeEntryId != null,
      canRecompose: () => {
        const entry = useLedgerStore.getState().activeEntry();
        if (!entry || entry.requestPayloadMode === "artifact_referenced") return false;
        if (entry.request.mode !== "inline") return false;
        return !(
          entry.imported &&
          useUiStore.getState().banners.some((banner) => banner.id === "memo-legacy")
        );
      },
      createNewStudy: (options) => {
        const status = useRunStore.getState().status;
        if (status === "running" || status === "stalled") {
          useUiStore.getState().pushBanner({
            id: "new-study-run-active",
            severity: "warning",
            message: "Finish or cancel the active screening run before creating a new study.",
          });
          return;
        }
        useStudyStore.getState().create(options);
        useLedgerStore.getState().setActive(null);
        useSelectionStore.getState().clear();
        useRunStore.getState().reset();
        const workspace = useWorkspaceStore.getState();
        workspace.setViewport(options.startView);
        workspace.setExaggeration(options.verticalExaggeration);
        workspace.setActiveTool("select");
        workspace.setActiveTab("compose");
        try {
          const field = currentFieldSetup();
          const imported = useFieldStore.getState().reservoirRuntime;
          if (!field || !imported) {
            throw new Error(
              "The imported terrain and reservoir must be linked before creating a study.",
            );
          }
          useComposeStore.getState().loadBase(
            buildStudyRequest({
              field,
              imported,
              base: createDefaultStudyRequestBase(),
              scheduleMode: "grid",
            }),
          );
          useUiStore.getState().dismissBanner("new-study-request-failed");
        } catch (error) {
          useComposeStore.setState({ draft: null, past: [], future: [] });
          useUiStore.getState().pushBanner({
            id: "new-study-request-failed",
            severity: "danger",
            message:
              error instanceof Error
                ? error.message
                : "The study request could not be initialized.",
          });
        }
        useUiStore.getState().dismissBanner("new-study-run-active");
      },
      openStudy: async () => {
        try {
          const memo = await pickStudyMemo();
          if (memo) {
            useComposeStore.setState({ draft: null, past: [], future: [] });
            useLedgerStore.getState().importMemo(memo);
            if (memo.study) useStudyStore.getState().load(memo.study);
            if (
              !isLegacyMemo(memo) &&
              memo.request_payload_mode !== "artifact_referenced" &&
              memo.request.mode === "inline"
            ) {
              useComposeStore.getState().loadBase({
                ...memo.request,
                run_id: null,
              });
            }
            const ui = useUiStore.getState();
            ui.dismissBanner("memo-reservoir-relink");
            if (
              memo.field_setup &&
              memo.request_payload_mode === "artifact_referenced" &&
              useFieldStore.getState().reservoirRuntime == null
            ) {
              ui.pushBanner({
                id: "memo-reservoir-relink",
                severity: "info",
                message:
                  "The imported reservoir files for this study could not be found in data/imports. Re-import the model via New Study to screen again.",
              });
            }
            const axis = carbonPriceAxis(memo.result);
            if (axis.length > 0) useSelectionStore.getState().setCarbonPrice(axis[0].scenarioId);
            useWorkspaceStore.getState().setActiveTab("ranking");
          }
        } catch (err) {
          useUiStore.getState().pushBanner({
            id: "open-failed",
            severity: "danger",
            message: err instanceof Error ? err.message : "Failed to open study memo.",
          });
        }
      },
      saveStudy: async () => {
        const entry = useLedgerStore.getState().activeEntry();
        if (entry && entry.requestPayloadMode !== "artifact_referenced") {
          await exportStudyMemo(entry);
        }
      },
      saveStudyAs: async () => {
        const entry = useLedgerStore.getState().activeEntry();
        if (entry && entry.requestPayloadMode !== "artifact_referenced") {
          await exportStudyMemo(entry);
        }
      },
      exportRankingCsv: async () => {
        const entry = useLedgerStore.getState().activeEntry();
        if (entry) await exportRankingCsv(entry.result, entry.label);
      },
      exportSnapshot: async () => {
        try {
          const entry = useLedgerStore.getState().activeEntry();
          const label = entry?.study?.name ?? entry?.label ?? useStudyStore.getState().study.name;
          await exportViewportSnapshot(label);
        } catch (err) {
          useUiStore.getState().pushBanner({
            id: "snapshot-failed",
            severity: "danger",
            message: err instanceof Error ? err.message : "Could not export the viewport snapshot.",
          });
        }
      },
      recomposeActive: () => {
        const entry = useLedgerStore.getState().activeEntry();
        if (entry && entry.requestPayloadMode !== "artifact_referenced") {
          if (entry.request.mode !== "inline") return;
          if (
            entry.imported &&
            useUiStore.getState().banners.some((banner) => banner.id === "memo-legacy")
          ) {
            return;
          }
          const currentDraft = useComposeStore.getState().draft;
          const hasLiveField = useFieldStore.getState().reservoir !== null;
          // A coverage-limited run stores an explicit schedules request. Keep
          // the session's editable grid when recomposing that live field.
          if (!hasLiveField || !currentDraft?.operational_grid) {
            useComposeStore.getState().loadBase({ ...entry.request, run_id: null });
          }
          useWorkspaceStore.getState().setActiveTab("compose");
        }
      },
      validate: () => {
        /* Preflight report is rendered by ValidateDialog from health/presets. */
      },
      undo: () => useComposeStore.getState().undo(),
      redo: () => useComposeStore.getState().redo(),
      canUndo: () => useComposeStore.getState().canUndo(),
      canRedo: () => useComposeStore.getState().canRedo(),
    });

    return () => clearWatchdog();
  }, []);
}

function mapErrorToUi(error: unknown): void {
  const ui = useUiStore.getState();
  if (error instanceof ApiError) {
    if (error.status === 429) {
      ui.pushBanner({
        id: "run-429",
        severity: "warning",
        message: "Another screening run is active. Cancel it before starting a new one.",
      });
      return;
    }
    if (error.status === 503) {
      ui.pushBanner({
        id: "run-503",
        severity: "danger",
        message: `A required backend dependency is unavailable: ${error.message}`,
      });
      return;
    }
    if (error.status === 422) {
      useWorkspaceStore.getState().setActiveTab("compose");
      const detail = Array.isArray(error.detail)
        ? error.detail.map((d) => `${d.loc.join(".")}: ${d.msg}`).join("; ")
        : error.message;
      ui.pushBanner({ id: "run-422", severity: "warning", message: `Invalid request: ${detail}` });
      return;
    }
  }
  ui.pushBanner({
    id: "run-error",
    severity: "danger",
    message: error instanceof Error ? error.message : "Screening run failed.",
  });
}
