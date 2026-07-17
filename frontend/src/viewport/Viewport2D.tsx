import { useMemo } from "react";
import { useLedgerStore } from "../state/ledger.store";
import { useSelectionStore } from "../state/selection.store";
import { useWorkspaceStore } from "../state/workspace.store";
import { useFieldStore } from "../state/field.store";
import { selectPlan } from "../layout/ProjectTree";
import { collectSceneObjects, projectToView, type Scene } from "./scene";
import "./viewport.css";

/**
 * The 2D map: sources, candidate wells, and the selected network in geographic
 * space. This is both the working 2D view and the automatic fallback when the
 * 3D viewport errors. Same selection model as the 3D scene.
 */
export function Viewport2D({ degraded = false }: { degraded?: boolean }) {
  const activeEntry = useLedgerStore((s) => s.entryById(s.activeEntryId));
  const carbonPriceId = useSelectionStore((s) => s.carbonPriceId);
  const selection = useSelectionStore((s) => s.selection);
  const select = useSelectionStore((s) => s.select);
  const layers = useWorkspaceStore((s) => s.layers);
  const wells = useFieldStore((s) => s.wells);
  const sources = useFieldStore((s) => s.sources);
  const placement = useFieldStore((s) => s.placement);
  const reservoir = useFieldStore((s) => s.reservoir);

  const plan = activeEntry ? selectPlan(activeEntry.result, carbonPriceId) : null;
  const resultScene = useMemo(
    () => (activeEntry ? collectSceneObjects(activeEntry.request, plan) : null),
    [activeEntry, plan],
  );
  const draftScene = useMemo<Scene | null>(() => {
    if (!placement || wells.length + sources.length === 0) return null;
    return {
      nodes: [
        ...sources.map((source) => ({
          id: source.id,
          kind: "source" as const,
          location: { latitude: source.lat, longitude: source.lon },
          dim: false,
        })),
        ...wells.map((well) => ({
          id: well.id,
          kind: "well" as const,
          location: { latitude: well.lat, longitude: well.lon },
          dim: false,
        })),
      ],
      routes: [],
      boosters: [],
    };
  }, [placement, sources, wells]);
  const scene = resultScene?.nodes.length ? resultScene : draftScene;

  if (!scene || scene.nodes.length === 0) {
    return (
      <div className="viewport-empty">
        <div>
          <p>No scene to display.</p>
          <p className="viewport-empty-dim">
            Run or open a study to see sources, wells, and the optimized network
            on the map.
          </p>
        </div>
      </div>
    );
  }

  const view = projectToView(scene, 900, 560, 40);

  return (
    <div className="viewport-2d">
      {placement && reservoir ? (
        <button
          type="button"
          className="field-breadcrumb field-entry"
          aria-label="Enter field view"
          onClick={() => {
            useFieldStore.getState().enterField();
            useWorkspaceStore.getState().setViewport("3d");
          }}
        >
          {"Field \u25b8"}
        </button>
      ) : null}
      <svg viewBox="0 0 900 560" className="viewport-svg" role="img" aria-label="Study map">
        {/* Routes */}
        {layers.routes &&
          view.routes.map((r) => (
            <polyline
              key={r.id}
              points={r.points.map((p) => `${p.x},${p.y}`).join(" ")}
              className={
                r.mode === "trucking"
                  ? "route route-trucking"
                  : `route route-pipeline${selection.id === r.id ? " route-selected" : ""}`
              }
              onClick={() => select({ kind: "route", id: r.id })}
            />
          ))}
        {/* Boosters */}
        {layers.boosters &&
          view.boosters.map((b) => (
            <g key={b.id} transform={`translate(${b.x},${b.y})`} className="booster">
              <rect x={-4} y={-4} width={8} height={8} />
            </g>
          ))}
        {/* Nodes: sources + wells */}
        {view.nodes.map((n) => (
          <g
            key={n.id}
            transform={`translate(${n.x},${n.y})`}
            className={`node node-${n.kind}${
              selection.id === n.id ? " node-selected" : ""
            }${n.dim ? " node-dim" : ""}`}
            onClick={() => select({ kind: n.kind === "source" ? "source" : "well", id: n.id })}
          >
            {n.kind === "source" ? (
              <rect x={-5} y={-5} width={10} height={10} />
            ) : (
              <circle r={5} />
            )}
            {layers.labels && (
              <text x={8} y={4} className="node-label">
                {n.id}
              </text>
            )}
          </g>
        ))}
      </svg>
      <div className="viewport-legend">
        <span><i className="lg-source" /> source</span>
        <span><i className="lg-well" /> well</span>
        <span><i className="lg-pipe" /> pipeline</span>
        <span><i className="lg-truck" /> trucking</span>
        <span><i className="lg-booster" /> booster</span>
      </div>
      <div className="viewport-mode-tag">{degraded ? "2D map · 3D unavailable" : "2D map"}</div>
    </div>
  );
}
