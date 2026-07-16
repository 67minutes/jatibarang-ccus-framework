import { create } from "zustand";
import type { ScreenRequest, ScreenResult } from "../api/types";
import {
  type LedgerEntry,
  memoToEntry,
  shortFingerprint,
  type StudyMemo,
} from "../memo/studyMemo";

/**
 * The run ledger: this session's completed runs, keyed by request fingerprint
 * and immutable once recorded. Holds the active exploration entry and the
 * two-entry compare selection (design §7.4).
 */

interface LedgerState {
  entries: LedgerEntry[];
  activeEntryId: string | null;
  compareIds: [string | null, string | null];

  recordRun: (
    request: ScreenRequest,
    result: ScreenResult,
    opts?: { label?: string; imported?: boolean },
  ) => LedgerEntry;
  importMemo: (memo: StudyMemo) => LedgerEntry;
  setActive: (entryId: string | null) => void;
  setCompare: (slot: 0 | 1, entryId: string | null) => void;
  renameEntry: (entryId: string, label: string) => void;
  removeEntry: (entryId: string) => void;

  activeEntry: () => LedgerEntry | null;
  entryById: (entryId: string | null) => LedgerEntry | null;
}

export const useLedgerStore = create<LedgerState>((set, get) => ({
  entries: [],
  activeEntryId: null,
  compareIds: [null, null],

  recordRun: (request, result, opts) => {
    const entry: LedgerEntry = {
      entryId: crypto.randomUUID(),
      fingerprint: result.request_fingerprint,
      label:
        opts?.label ??
        `run ${shortFingerprint(result.request_fingerprint)}`,
      savedAt: new Date().toISOString(),
      request,
      result,
      imported: opts?.imported ?? false,
    };
    set((s) => ({ entries: [entry, ...s.entries], activeEntryId: entry.entryId }));
    return entry;
  },

  importMemo: (memo) => {
    const entry = memoToEntry(memo, true);
    set((s) => ({ entries: [entry, ...s.entries], activeEntryId: entry.entryId }));
    return entry;
  },

  setActive: (activeEntryId) => set({ activeEntryId }),
  setCompare: (slot, entryId) =>
    set((s) => {
      const next: [string | null, string | null] = [...s.compareIds];
      next[slot] = entryId;
      return { compareIds: next };
    }),
  renameEntry: (entryId, label) =>
    set((s) => ({
      entries: s.entries.map((e) =>
        e.entryId === entryId ? { ...e, label } : e,
      ),
    })),
  removeEntry: (entryId) =>
    set((s) => ({
      entries: s.entries.filter((e) => e.entryId !== entryId),
      activeEntryId: s.activeEntryId === entryId ? null : s.activeEntryId,
    })),

  activeEntry: () => get().entryById(get().activeEntryId),
  entryById: (entryId) =>
    entryId ? get().entries.find((e) => e.entryId === entryId) ?? null : null,
}));
