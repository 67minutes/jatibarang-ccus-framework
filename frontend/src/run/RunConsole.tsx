import { useEffect, useMemo, useState } from "react";
import { useRunStore } from "../state/run.store";
import { useLedgerStore } from "../state/ledger.store";
import { buildTimeline, dedupFromEvents } from "./stageTimeline";
import { runCommand, isCommandEnabled } from "../chrome/commands";
import { Badge } from "../ui/confidence";
import "./run-console.css";

/**
 * The run console (design §7.3): the live stage timeline over the real
 * orchestrator stages, the dedup counter, inline warnings, wall-clock, and a
 * cancel control. The stalled state is designed and offers cancel.
 */
export function RunConsole() {
  const status = useRunStore((s) => s.status);
  const events = useRunStore((s) => s.events);
  const warnings = useRunStore((s) => s.warnings);
  const startedAt = useRunStore((s) => s.startedAt);
  const finishedAt = useRunStore((s) => s.finishedAt);
  const errorMessage = useRunStore((s) => s.errorMessage);
  const activeEntry = useLedgerStore((s) => s.entryById(s.activeEntryId));

  const timeline = useMemo(() => buildTimeline(events), [events]);
  const dedup = useMemo(() => dedupFromEvents(events), [events]);
  const resultDedup = activeEntry
    ? {
        logical: activeEntry.result.logical_scenario_count,
        unique: activeEntry.result.unique_inference_count,
        cacheHits: activeEntry.result.inference_cache_hits,
      }
    : null;
  const counters = status === "completed" && resultDedup ? resultDedup : dedup;

  if (status === "idle" && events.length === 0) {
    return (
      <p className="empty-hint">
        No run in progress. Compose a study and press Screen (Ctrl+Enter) to
        start. Progress appears here in real time.
      </p>
    );
  }

  return (
    <div className="run-console">
      <div className="run-header">
        <StatusBadge status={status} />
        {counters && (
          <span className="run-dedup mono" title="unique inferences / logical scenarios">
            dedup {counters.unique}/{counters.logical}
            {counters.cacheHits ? ` · ${counters.cacheHits} cache hits` : ""}
          </span>
        )}
        <RunElapsed
          startedAt={startedAt}
          finishedAt={finishedAt}
          live={status === "running" || status === "stalled"}
        />
        {(status === "running" || status === "stalled") && (
          <button
            type="button"
            className="btn"
            disabled={!isCommandEnabled("study.cancel")}
            onClick={() => runCommand("study.cancel")}
          >
            ■ Cancel
          </button>
        )}
      </div>

      {status === "stalled" && (
        <div className="run-stalled">
          No progress for a while — the run may be slow (large physics) or the
          backend may be stuck. It has not been aborted. You can keep waiting or
          cancel.
        </div>
      )}
      {status === "failed" && errorMessage && (
        <div className="run-error-line">Run failed: {errorMessage}</div>
      )}

      <ol className="stage-list">
        {timeline.map((row) => (
          <li key={row.stage} className={`stage stage-${row.status}`}>
            <span className="stage-dot" aria-hidden />
            <span className="stage-label">{row.label}</span>
            {row.total > 0 && (
              <span className="stage-progress mono">
                {row.completed}/{row.total}
              </span>
            )}
          </li>
        ))}
      </ol>

      {warnings.length > 0 && (
        <div className="run-warnings">
          <h4>Warnings ({warnings.length})</h4>
          <ul>
            {warnings.map((w, i) => (
              <li key={i}>
                <span className="mono run-warn-stage">{w.stage}</span> {w.message}
                {Array.isArray(w.payload?.scenario_ids) && (w.payload.scenario_ids as unknown[]).length > 0 && (
                  <span className="run-warn-scope mono">
                    {" "}
                    · {(w.payload.scenario_ids as unknown[]).length} cell(s)
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const tone =
    status === "completed"
      ? "ok"
      : status === "failed"
        ? "danger"
        : status === "stalled"
          ? "warning"
          : status === "cancelled"
            ? "neutral"
            : "info";
  return <Badge tone={tone as never}>{status}</Badge>;
}

function RunElapsed({
  startedAt,
  finishedAt,
  live,
}: {
  startedAt: number | null;
  finishedAt: number | null;
  live: boolean;
}) {
  const now = useNow(live);
  if (!startedAt) return null;
  const end = live ? now : (finishedAt ?? startedAt);
  const seconds = (end - startedAt) / 1000;
  return <span className="run-elapsed mono">{seconds.toFixed(1)}s</span>;
}

function useNow(live: boolean): number {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!live) return;
    const id = window.setInterval(() => setNow(Date.now()), 200);
    return () => window.clearInterval(id);
  }, [live]);
  return now;
}
