import type { InlineScreenRequest, ScreenRequest, ScreenResult } from "../api/types";
import type { LedgerEntry } from "../memo/studyMemo";
import { readCarbonPrices } from "../compose/validation";

/**
 * Fingerprint-keyed comparison of two ledger entries (design §7.4). Surfaces
 * the request deltas (so no one can claim two levers moved at once), rank
 * trajectories per candidate, and per-well shortlist NPV deltas.
 */

export interface RequestDelta {
  field: string;
  a: string;
  b: string;
}

export interface RankTrajectory {
  candidateId: string;
  rankA: number | null;
  rankB: number | null;
  npvA: number | null;
  npvB: number | null;
}

export interface StudyComparison {
  sameFingerprint: boolean;
  requestDeltas: RequestDelta[];
  trajectories: RankTrajectory[];
}

function summarizeRequest(request: ScreenRequest): Record<string, string> {
  const out: Record<string, string> = { mode: request.mode };
  if (request.mode === "inline") {
    const inline = request as InlineScreenRequest;
    out.carbon_prices = readCarbonPrices(inline)
      .map((p) => `${p.scenario_id}=${p.carbon_price_usd_per_tonne}`)
      .join(", ");
    out.cost_case = inline.cost_case ?? "base";
    out.supply_scenarios = (inline.supply_scenarios ?? []).join("+");
    out.selection_fiscal_case_id = inline.selection_fiscal_case_id ?? "pre_tax";
    out.annual_co2_budget_tonnes = String(inline.annual_co2_budget_tonnes);
    out.project_life_years = String(inline.project_life_years ?? 8);
    out.candidates = String(inline.candidates.length);
    out.shortlist_top_k = String(inline.shortlist_top_k ?? 5);
  } else {
    out.preset_id = request.preset_id;
  }
  return out;
}

export function diffRequests(a: ScreenRequest, b: ScreenRequest): RequestDelta[] {
  const sa = summarizeRequest(a);
  const sb = summarizeRequest(b);
  const fields = new Set([...Object.keys(sa), ...Object.keys(sb)]);
  const deltas: RequestDelta[] = [];
  for (const field of fields) {
    const va = sa[field] ?? "—";
    const vb = sb[field] ?? "—";
    if (va !== vb) deltas.push({ field, a: va, b: vb });
  }
  return deltas;
}

function rankMap(result: ScreenResult): Map<string, { rank: number; npv: number | null }> {
  const map = new Map<string, { rank: number; npv: number | null }>();
  for (const item of result.shortlist) {
    const existing = map.get(item.candidate_id);
    if (!existing || item.rank < existing.rank) {
      map.set(item.candidate_id, { rank: item.rank, npv: item.designated_npv_usd });
    }
  }
  return map;
}

export function rankTrajectories(a: ScreenResult, b: ScreenResult): RankTrajectory[] {
  const ma = rankMap(a);
  const mb = rankMap(b);
  const ids = new Set([...ma.keys(), ...mb.keys()]);
  return [...ids]
    .map((candidateId) => ({
      candidateId,
      rankA: ma.get(candidateId)?.rank ?? null,
      rankB: mb.get(candidateId)?.rank ?? null,
      npvA: ma.get(candidateId)?.npv ?? null,
      npvB: mb.get(candidateId)?.npv ?? null,
    }))
    .sort((x, y) => (x.rankA ?? 99) - (y.rankA ?? 99));
}

export function compareEntries(a: LedgerEntry, b: LedgerEntry): StudyComparison {
  return {
    sameFingerprint: a.fingerprint === b.fingerprint,
    requestDeltas: diffRequests(a.request, b.request),
    trajectories: rankTrajectories(a.result, b.result),
  };
}
