import { create } from "zustand";
import type {
  CarbonPriceScenario,
  CostCase,
  InlineScreenRequest,
  OperationalGrid,
  SupplyScenario,
} from "../api/types";

/**
 * The compose draft: a working copy of an inline screening request.
 *
 * The heavy nested blocks (geologies, seeds, candidates, economic_assumptions)
 * come from a loaded base — the demo seed design or a re-composed ledger entry
 * — and are treated as opaque. The composer exposes the decision surface an
 * engineer actually turns between runs: carbon prices, cost case, supply
 * scenarios, the operational grid, budget, fiscal selection, and top-k.
 *
 * Undo/redo (design §3.4) is scoped to these study-definition edits via draft
 * snapshots.
 */

interface ComposeState {
  draft: InlineScreenRequest | null;
  past: InlineScreenRequest[];
  future: InlineScreenRequest[];

  loadBase: (draft: InlineScreenRequest) => void;
  setCarbonPrices: (prices: CarbonPriceScenario[]) => void;
  setCostCase: (cost: CostCase) => void;
  setSupplyScenarios: (scenarios: SupplyScenario[]) => void;
  setAnnualBudget: (tonnes: number) => void;
  setProjectLife: (years: number) => void;
  setSelectionFiscalCase: (caseId: string) => void;
  setShortlistTopK: (k: number) => void;
  setDetailedTopK: (k: number) => void;
  setOperationalGrid: (grid: OperationalGrid) => void;

  undo: () => void;
  redo: () => void;
  canUndo: () => boolean;
  canRedo: () => boolean;
}

const HISTORY_LIMIT = 50;

function mutate(
  state: ComposeState,
  change: (draft: InlineScreenRequest) => InlineScreenRequest,
): Partial<ComposeState> {
  if (!state.draft) return {};
  return {
    past: [...state.past, state.draft].slice(-HISTORY_LIMIT),
    future: [],
    draft: change(state.draft),
  };
}

export const useComposeStore = create<ComposeState>((set, get) => ({
  draft: null,
  past: [],
  future: [],

  loadBase: (draft) => set({ draft, past: [], future: [] }),

  setCarbonPrices: (carbon_prices) =>
    set((s) => mutate(s, (d) => ({ ...d, carbon_prices }))),
  setCostCase: (cost_case) => set((s) => mutate(s, (d) => ({ ...d, cost_case }))),
  setSupplyScenarios: (supply_scenarios) =>
    set((s) => mutate(s, (d) => ({ ...d, supply_scenarios }))),
  setAnnualBudget: (annual_co2_budget_tonnes) =>
    set((s) => mutate(s, (d) => ({ ...d, annual_co2_budget_tonnes }))),
  setProjectLife: (project_life_years) =>
    set((s) => mutate(s, (d) => ({ ...d, project_life_years }))),
  setSelectionFiscalCase: (selection_fiscal_case_id) =>
    set((s) => mutate(s, (d) => ({ ...d, selection_fiscal_case_id }))),
  setShortlistTopK: (shortlist_top_k) =>
    set((s) => mutate(s, (d) => ({ ...d, shortlist_top_k }))),
  setDetailedTopK: (detailed_top_k) =>
    set((s) => mutate(s, (d) => ({ ...d, detailed_top_k }))),
  setOperationalGrid: (operational_grid) =>
    set((s) => mutate(s, (d) => ({ ...d, operational_grid, schedules: null }))),

  undo: () =>
    set((s) => {
      if (s.past.length === 0 || !s.draft) return {};
      const previous = s.past[s.past.length - 1];
      return {
        past: s.past.slice(0, -1),
        future: [s.draft, ...s.future],
        draft: previous,
      };
    }),
  redo: () =>
    set((s) => {
      if (s.future.length === 0 || !s.draft) return {};
      const next = s.future[0];
      return {
        past: [...s.past, s.draft],
        future: s.future.slice(1),
        draft: next,
      };
    }),
  canUndo: () => get().past.length > 0,
  canRedo: () => get().future.length > 0,
}));
