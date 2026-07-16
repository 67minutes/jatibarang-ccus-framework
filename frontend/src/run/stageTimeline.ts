import type { ProgressEvent } from "../api/types";
import { PORTFOLIO_STAGE_PREFIX } from "../api/types";

/**
 * Fold the raw SSE event stream into an ordered stage timeline for the run
 * console. Stages appear in first-seen order; the per-price portfolio stages
 * (`portfolio:{id}`) are labelled by their carbon-price scenario id.
 */

export type StageStatus = "pending" | "active" | "done";

export interface StageRow {
  stage: string;
  label: string;
  status: StageStatus;
  completed: number;
  total: number;
}

const STAGE_LABELS: Record<string, string> = {
  resolve: "Resolve request",
  surrogate: "Surrogate inference",
  preliminary_economics: "Preliminary economics",
  routing: "Route library",
};

function labelFor(stage: string): string {
  if (stage.startsWith(PORTFOLIO_STAGE_PREFIX)) {
    return `Network + economics @ ${stage.slice(PORTFOLIO_STAGE_PREFIX.length)}`;
  }
  return STAGE_LABELS[stage] ?? stage;
}

export function buildTimeline(events: ProgressEvent[]): StageRow[] {
  const order: string[] = [];
  const rows = new Map<string, StageRow>();

  const ensure = (stage: string): StageRow => {
    let row = rows.get(stage);
    if (!row) {
      row = { stage, label: labelFor(stage), status: "pending", completed: 0, total: 0 };
      rows.set(stage, row);
      order.push(stage);
    }
    return row;
  };

  for (const e of events) {
    if (e.event === "result" || e.event === "error" || e.event === "cancelled" || e.event === "warning") {
      continue;
    }
    if (!e.stage) continue;
    const row = ensure(e.stage);
    if (e.total) row.total = e.total;
    if (e.completed) row.completed = e.completed;
    if (e.event === "stage_started" || e.event === "run_started") row.status = "active";
    else if (e.event === "stage_completed") {
      row.status = "done";
      if (row.total) row.completed = row.total;
    } else if (e.event === "progress" && row.status === "pending") {
      row.status = "active";
    }
  }

  return order.map((s) => rows.get(s)!);
}

export interface DedupSummary {
  logical: number;
  unique: number;
  cacheHits: number;
}

/** Pull the live dedup counters from the surrogate stage payload if present. */
export function dedupFromEvents(events: ProgressEvent[]): DedupSummary | null {
  for (let i = events.length - 1; i >= 0; i--) {
    const p = events[i].payload;
    if (p && (typeof p.unique_inference_count === "number" || typeof p.logical_scenario_count === "number")) {
      return {
        logical: Number(p.logical_scenario_count ?? 0),
        unique: Number(p.unique_inference_count ?? 0),
        cacheHits: Number(p.inference_cache_hits ?? 0),
      };
    }
  }
  return null;
}
