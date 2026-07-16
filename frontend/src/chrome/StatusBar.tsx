import { useEffect, useState } from "react";
import { useHealth } from "../api/queries";
import { useCursorStore } from "../state/cursor.store";
import { useSelectionStore } from "../state/selection.store";
import { useLedgerStore } from "../state/ledger.store";
import { useRunStore } from "../state/run.store";
import { shortFingerprint } from "../memo/studyMemo";
import "./chrome.css";

/**
 * The status bar: ambient truth (design §3 clause 3 / §3.6). Always visible,
 * never modal — cursor readout, selection, active study fingerprint, run
 * wall-clock, and the backend health dot.
 */
export function StatusBar() {
  const readout = useCursorStore((s) => s.readout);
  const selection = useSelectionStore((s) => s.selection);
  const activeEntry = useLedgerStore((s) => s.entryById(s.activeEntryId));
  const runStatus = useRunStore((s) => s.status);
  const startedAt = useRunStore((s) => s.startedAt);
  const finishedAt = useRunStore((s) => s.finishedAt);
  const health = useHealth();

  const healthClass =
    health.isError || health.data?.status === "degraded"
      ? "status-dot-danger"
      : health.data?.status === "ready"
        ? "status-dot-ok"
        : "status-dot-unknown";
  const healthLabel = health.isError
    ? "backend unreachable"
    : health.data
      ? health.data.status
      : "checking…";

  return (
    <footer className="statusbar">
      <span className="status-cell mono">
        {readout
          ? `(${readout.i},${readout.j})` +
            (readout.latitude != null && readout.longitude != null
              ? `  ${readout.latitude.toFixed(4)}, ${readout.longitude.toFixed(4)}`
              : "") +
            (readout.elevation_m != null ? `  el ${Math.round(readout.elevation_m)}m` : "")
          : "—"}
      </span>
      <span className="status-cell">
        sel: {selection.kind === "none" ? "none" : `${selection.kind} ${selection.id}`}
      </span>
      <span className="status-cell mono">
        study: {activeEntry ? shortFingerprint(activeEntry.fingerprint) : "—"}
      </span>
      <RunClock status={runStatus} startedAt={startedAt} finishedAt={finishedAt} />
      <div className="status-spacer" />
      <span className="status-cell status-health" title={String(healthLabel)}>
        <span className={`status-dot ${healthClass}`} aria-hidden />
        {healthLabel}
      </span>
    </footer>
  );
}

function RunClock({
  status,
  startedAt,
  finishedAt,
}: {
  status: string;
  startedAt: number | null;
  finishedAt: number | null;
}) {
  const [now, setNow] = useState(Date.now());
  const ticking = status === "running" || status === "stalled";
  useEffect(() => {
    if (!ticking) return;
    const id = window.setInterval(() => setNow(Date.now()), 200);
    return () => window.clearInterval(id);
  }, [ticking]);

  if (status === "idle" || !startedAt) return <span className="status-cell">run: —</span>;
  const end = ticking ? now : (finishedAt ?? startedAt);
  const seconds = (end - startedAt) / 1000;
  return (
    <span className={`status-cell mono${status === "stalled" ? " status-stalled" : ""}`}>
      run: {status} {seconds.toFixed(1)}s
    </span>
  );
}
