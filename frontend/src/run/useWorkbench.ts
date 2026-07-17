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
import { shortFingerprint } from "../memo/studyMemo";

/** Watchdog: mark the run stalled if no event arrives within this window. */
const STALL_TIMEOUT_MS = 20_000;

/**
 * The workbench controller. Owns run execution (SSE + watchdog + sync
 * fallback), wires every menu/toolbar action into the registry, and loads the
 * demo base into the composer on first mount. Actions read fresh store state so
 * they never go stale.
 */
export function useWorkbench(): void {
  const abortRef = useRef<AbortController | null>(null);
  const watchdogRef = useRef<number | null>(null);
  const baseTemplateRef = useRef<InlineScreenRequest | null>(null);

  // Load the demo base request into the composer, and the cached demo result
  // into the ledger (paired with that request so its map renders), so the
  // workbench is populated and the core demo runs even with no backend
  // (design §8). Assets are optional and degrade quietly.
  useEffect(() => {
    const requestP = fetch("/assets/demo-request.json")
      .then((r) => (r.ok ? (r.json() as Promise<InlineScreenRequest>) : null))
      .catch(() => null);

    requestP.then((draft) => {
      if (draft) baseTemplateRef.current = draft;
      if (draft && !useComposeStore.getState().draft) useComposeStore.getState().loadBase(draft);
    });

    if (useLedgerStore.getState().entries.length === 0) {
      Promise.all([
        requestP,
        fetch("/assets/canned-demo.json")
          .then((r) => (r.ok ? (r.json() as Promise<ScreenResult>) : null))
          .catch(() => null),
      ]).then(([draft, result]) => {
        if (!result) return;
        const ledger = useLedgerStore.getState();
        if (ledger.entries.some((e) => e.fingerprint === result.request_fingerprint)) return;
        const request = (draft ?? { mode: "inline" }) as ScreenRequest;
        ledger.recordRun(request, result, { label: "Jatibarang demo (cached)", imported: true });
        const axis = carbonPriceAxis(result);
        if (axis.length > 0) useSelectionStore.getState().setCarbonPrice(axis[0].scenarioId);
      });
    }
  }, []);

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
      if (!draft || run.status === "running" || run.status === "stalled") return;
      const report = validateDraft(draft);
      if (!report.valid) {
        useWorkspaceStore.getState().setActiveTab("compose");
        useUiStore.getState().pushBanner({
          id: "compose-invalid",
          severity: "warning",
          message: `Cannot screen: ${report.errors.length} validation issue(s) in the composer.`,
        });
        return;
      }
      useUiStore.getState().dismissBanner("compose-invalid");
      const request: ScreenRequest = { ...draft, run_id: crypto.randomUUID() };
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
          validateDraft(useComposeStore.getState().draft).valid
        );
      },
      canCancel: () => {
        const status = useRunStore.getState().status;
        return status === "running" || status === "stalled";
      },
      hasActiveResult: () => useLedgerStore.getState().activeEntryId != null,
      createNewStudy: (options) => {
        const current = useComposeStore.getState().draft;
        const source = options.template === "current" ? current : baseTemplateRef.current ?? current;
        if (!source) {
          useUiStore.getState().pushBanner({
            id: "new-study-unavailable",
            severity: "warning",
            message: "The study template is still loading. Try New Study again in a moment.",
          });
          return;
        }
        useStudyStore.getState().create(options);
        useComposeStore.getState().loadBase({ ...source, run_id: null });
        useLedgerStore.getState().setActive(null);
        useSelectionStore.getState().clear();
        const workspace = useWorkspaceStore.getState();
        workspace.setViewport(options.startView);
        workspace.setExaggeration(options.verticalExaggeration);
        workspace.setActiveTool("select");
        workspace.setActiveTab("compose");
        useUiStore.getState().dismissBanner("new-study-unavailable");
      },
      openStudy: async () => {
        try {
          const memo = await pickStudyMemo();
          if (memo) {
            useLedgerStore.getState().importMemo(memo);
            if (memo.study) useStudyStore.getState().load(memo.study);
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
        if (entry) await exportStudyMemo(entry);
      },
      saveStudyAs: async () => {
        const entry = useLedgerStore.getState().activeEntry();
        if (entry) await exportStudyMemo(entry);
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
        if (entry && entry.request.mode === "inline") {
          useComposeStore.getState().loadBase({ ...entry.request, run_id: null });
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
