import type {
  CarbonPricePlan,
  PredictionResult,
  ScreenResult,
} from "../api/types";
import { planForPrice } from "./priceScrubber";

/**
 * Display adapters that make the workbench useful even when no pipeline network
 * is economic (the correct HnP outcome at pilot CO₂ volumes) — the backend then
 * may return an empty development shortlist. New results retain requested
 * detail slots from the pre-logistics ranking; older/imported results can still
 * omit them, while each `well_strategies` entry carries a compact prediction.
 * These helpers preserve that backward-compatible fallback.
 */

export interface DisplayPrediction {
  scenarioId: string;
  candidateId: string;
  prediction: PredictionResult;
}

/**
 * Predictions to plot: the detailed (spatial) ones when present, otherwise the
 * compact per-well strategy predictions for the focused plan.
 */
export function displayPredictions(
  result: ScreenResult,
  carbonPriceId: string | null,
): DisplayPrediction[] {
  const detailed = Object.entries(result.detailed_predictions);
  if (detailed.length > 0) {
    const plan = planForPrice(result, carbonPriceId);
    const scenarioToWell = new Map(
      (plan?.well_strategies ?? []).map((s) => [s.scenario_id, s.candidate_id]),
    );
    return detailed.map(([scenarioId, prediction]) => ({
      scenarioId,
      candidateId: scenarioToWell.get(scenarioId) ?? scenarioId,
      prediction,
    }));
  }
  const plan = planForPrice(result, carbonPriceId);
  if (!plan) return [];
  // One representative prediction per candidate (dedup identical scenarios).
  const byCandidate = new Map<string, DisplayPrediction>();
  for (const strat of plan.well_strategies) {
    if (!byCandidate.has(strat.candidate_id)) {
      byCandidate.set(strat.candidate_id, {
        scenarioId: strat.scenario_id,
        candidateId: strat.candidate_id,
        prediction: strat.prediction,
      });
    }
  }
  return [...byCandidate.values()];
}

export interface PreliminaryRankRow {
  candidateId: string;
  scenarioId: string;
  preliminaryNpv: number;
  preLogisticsValue: number;
  selected: boolean;
}

/**
 * A pre-logistics well ranking for when the backend shortlist is empty. Ranks
 * the focused plan's candidates by preliminary NPV.
 */
export function preliminaryRanking(plan: CarbonPricePlan | null): PreliminaryRankRow[] {
  if (!plan) return [];
  const byCandidate = new Map<string, PreliminaryRankRow>();
  for (const strat of plan.well_strategies) {
    const existing = byCandidate.get(strat.candidate_id);
    if (!existing || strat.preliminary_npv_usd > existing.preliminaryNpv) {
      byCandidate.set(strat.candidate_id, {
        candidateId: strat.candidate_id,
        scenarioId: strat.scenario_id,
        preliminaryNpv: strat.preliminary_npv_usd,
        preLogisticsValue: strat.pre_logistics_value_usd,
        selected: plan.selected_wells.includes(strat.candidate_id),
      });
    }
  }
  return [...byCandidate.values()].sort((a, b) => b.preliminaryNpv - a.preliminaryNpv);
}
