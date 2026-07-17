import { create } from "zustand";
import type { NewStudyOptions } from "./study.store";

/**
 * Registry of imperative actions that live in feature components (Phase 3+).
 *
 * The command registry is defined in Phase 2 and must build/typecheck before
 * the data-flow controllers exist. Commands call through this registry; a
 * command whose handler is not yet registered reports itself disabled, so the
 * WIMP menu is complete from day one and fills in as phases land.
 */

export interface WorkbenchActions {
  createNewStudy?: (options: NewStudyOptions) => void;
  openStudy?: () => void;
  saveStudy?: () => void;
  saveStudyAs?: () => void;
  exportRankingCsv?: () => void;
  exportSnapshot?: () => void;
  screen?: () => void;
  cancelRun?: () => void;
  validate?: () => void;
  recomposeActive?: () => void;
  canScreen?: () => boolean;
  canCancel?: () => boolean;
  hasActiveResult?: () => boolean;
  undo?: () => void;
  redo?: () => void;
  canUndo?: () => boolean;
  canRedo?: () => boolean;
}

interface ActionsState {
  actions: WorkbenchActions;
  register: (actions: Partial<WorkbenchActions>) => void;
}

export const useActionsStore = create<ActionsState>((set) => ({
  actions: {},
  register: (actions) =>
    set((s) => ({ actions: { ...s.actions, ...actions } })),
}));

/** Non-reactive accessor for use inside command run()/isEnabled() closures. */
export function getActions(): WorkbenchActions {
  return useActionsStore.getState().actions;
}
