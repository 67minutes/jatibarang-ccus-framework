import { create } from "zustand";
import type { ProgressEvent } from "../api/types";

/**
 * In-flight screening run state. Separate from the ledger (which holds
 * completed, immutable runs) because this slice mutates rapidly as SSE events
 * arrive. `stalled` is a designed state (design §7.3): it offers cancel and
 * never auto-aborts.
 */

export type RunStatus =
  | "idle"
  | "running"
  | "stalled"
  | "completed"
  | "failed"
  | "cancelled";

interface RunState {
  status: RunStatus;
  runId: string | null;
  startedAt: number | null;
  finishedAt: number | null;
  lastEventAt: number | null;
  events: ProgressEvent[];
  /** Warnings surfaced during the run, in arrival order. */
  warnings: ProgressEvent[];
  errorMessage: string | null;

  begin: (runId: string) => void;
  pushEvent: (event: ProgressEvent) => void;
  markStalled: () => void;
  finish: (status: Extract<RunStatus, "completed" | "failed" | "cancelled">, message?: string) => void;
  reset: () => void;
}

export const useRunStore = create<RunState>((set) => ({
  status: "idle",
  runId: null,
  startedAt: null,
  finishedAt: null,
  lastEventAt: null,
  events: [],
  warnings: [],
  errorMessage: null,

  begin: (runId) =>
    set({
      status: "running",
      runId,
      startedAt: Date.now(),
      finishedAt: null,
      lastEventAt: Date.now(),
      events: [],
      warnings: [],
      errorMessage: null,
    }),
  pushEvent: (event) =>
    set((s) => ({
      status: s.status === "stalled" ? "running" : s.status,
      lastEventAt: Date.now(),
      events: [...s.events, event],
      warnings: event.event === "warning" ? [...s.warnings, event] : s.warnings,
    })),
  markStalled: () => set((s) => (s.status === "running" ? { status: "stalled" } : s)),
  finish: (status, message) =>
    set({ status, finishedAt: Date.now(), errorMessage: message ?? null }),
  reset: () =>
    set({
      status: "idle",
      runId: null,
      startedAt: null,
      finishedAt: null,
      lastEventAt: null,
      events: [],
      warnings: [],
      errorMessage: null,
    }),
}));
