import { useHealth, usePresets } from "../api/queries";
import { Badge } from "../ui/confidence";

/**
 * Preflight report (design §7.1): dependency readiness from /health and per
 * preset readiness from /presets, shown exactly as reported — a NOT READY or
 * BLOCKED preset appears with its reason and never gates the app.
 */
export function ValidateDialog() {
  const health = useHealth();
  const presets = usePresets();

  return (
    <div className="preflight">
      <h4>Dependencies</h4>
      {health.isError ? (
        <p className="empty-hint">Backend unreachable — cannot read /health.</p>
      ) : health.data ? (
        <ul className="preflight-list">
          <Check label="Surrogate checkpoint" ok={health.data.surrogate_loaded} />
          <Check label="CBC solver" ok={health.data.solver_available} />
          <Check label="Overall status" ok={health.data.status === "ready"} note={health.data.status} />
          <li>
            <span>Active runs</span>
            <span className="mono">{health.data.active_runs}</span>
          </li>
        </ul>
      ) : (
        <p className="empty-hint">Checking…</p>
      )}

      <h4 style={{ marginTop: 14 }}>Presets</h4>
      {presets.data && presets.data.length > 0 ? (
        <ul className="preflight-list">
          {presets.data.map((p) => (
            <li key={p.preset_id}>
              <span className="mono">{p.preset_id}</span>
              <span>
                <Badge tone={p.ready ? "ok" : "warning"}>{p.ready ? "ready" : "not ready"}</Badge>
                {!p.ready && p.reason && <span className="preflight-reason"> {p.reason}</span>}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="empty-hint">No preset metadata.</p>
      )}
      <p className="empty-hint" style={{ paddingLeft: 0 }}>
        The demo uses an inline request, so a NOT READY preset does not block
        screening.
      </p>
    </div>
  );
}

function Check({ label, ok, note }: { label: string; ok: boolean; note?: string }) {
  return (
    <li>
      <span>{label}</span>
      <span>
        <Badge tone={ok ? "ok" : "danger"}>{note ?? (ok ? "ready" : "missing")}</Badge>
      </span>
    </li>
  );
}
