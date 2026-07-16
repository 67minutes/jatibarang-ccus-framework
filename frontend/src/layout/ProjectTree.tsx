import { Panel } from "../ui/Panel";
import { useLedgerStore } from "../state/ledger.store";
import { useSelectionStore, type SelectionKind } from "../state/selection.store";
import { shortFingerprint } from "../memo/studyMemo";
import type { CarbonPricePlan, ScreenResult } from "../api/types";

/**
 * The project tree (left region): the active study's objects — sources,
 * candidate wells, network, facilities — plus the session run ledger. Read-only
 * structure; a click here is the same selection event as a scene or ranking
 * click (design §4.1).
 */
export function ProjectTree() {
  const activeEntry = useLedgerStore((s) => s.entryById(s.activeEntryId));
  const entries = useLedgerStore((s) => s.entries);
  const activeEntryId = useLedgerStore((s) => s.activeEntryId);
  const setActive = useLedgerStore((s) => s.setActive);
  const carbonPriceId = useSelectionStore((s) => s.carbonPriceId);

  const result = activeEntry?.result;
  const plan = result ? selectPlan(result, carbonPriceId) : null;

  return (
    <>
      <Panel title="Study Objects">
        {!result ? (
          <p className="empty-hint">
            No study loaded. Compose and run a screening study, or open a saved
            study memo.
          </p>
        ) : (
          <StudyObjects plan={plan} result={result} />
        )}
      </Panel>
      <Panel title={`Run Ledger (${entries.length})`}>
        {entries.length === 0 ? (
          <p className="empty-hint">Completed runs appear here.</p>
        ) : (
          entries.map((e) => (
            <button
              key={e.entryId}
              type="button"
              className={`tree-node${e.entryId === activeEntryId ? " selected" : ""}`}
              onClick={() => setActive(e.entryId)}
              title={e.fingerprint}
            >
              <span className="mono">{shortFingerprint(e.fingerprint)}</span>
              <span className="tree-node-dim">{e.imported ? "· imported" : ""}</span>
            </button>
          ))
        )}
      </Panel>
    </>
  );
}

function StudyObjects({ plan, result }: { plan: CarbonPricePlan | null; result: ScreenResult }) {
  const select = useSelectionStore((s) => s.select);
  const selection = useSelectionStore((s) => s.selection);

  const wells = plan?.well_strategies.map((w) => w.candidate_id) ?? [];
  const selectedWells = new Set(plan?.selected_wells ?? []);
  const boosters = plan?.pipeline.boosters ?? [];

  return (
    <div>
      <TreeGroup label="Wells">
        {wells.map((id) => (
          <TreeNode
            key={id}
            kind="well"
            id={id}
            label={id}
            dim={!selectedWells.has(id)}
            selected={selection.kind === "well" && selection.id === id}
            onSelect={select}
          />
        ))}
      </TreeGroup>
      <TreeGroup label="Network">
        {plan?.pipeline.built_segments.length ? (
          plan.pipeline.built_segments.map((seg) => (
            <TreeNode
              key={seg.segment_id}
              kind="route"
              id={seg.segment_id}
              label={`${seg.from_node} → ${seg.to_node}`}
              selected={selection.kind === "route" && selection.id === seg.segment_id}
              onSelect={select}
            />
          ))
        ) : (
          <p className="empty-hint">No pipeline network for this price.</p>
        )}
        {boosters.map((b) => (
          <div key={b.node_id} className="tree-node tree-node-dim">
            ⛽ booster {b.node_id}
          </div>
        ))}
      </TreeGroup>
      <TreeGroup label="Facilities">
        {plan?.facility?.well_results.length ? (
          plan.facility.well_results.map((f) => (
            <TreeNode
              key={f.candidate_id}
              kind="facility"
              id={f.candidate_id}
              label={`skid ${f.candidate_id}`}
              selected={selection.kind === "facility" && selection.id === f.candidate_id}
              onSelect={select}
            />
          ))
        ) : (
          <p className="empty-hint">No selected-well facilities.</p>
        )}
      </TreeGroup>
      <TreeGroup label={`Shortlist (${result.shortlist.length})`}>
        {result.shortlist.map((item) => (
          <TreeNode
            key={`${item.rank}-${item.candidate_id}`}
            kind="well"
            id={item.candidate_id}
            scenarioId={item.scenario_id}
            label={`#${item.rank} ${item.candidate_id}`}
            selected={selection.kind === "well" && selection.id === item.candidate_id}
            onSelect={select}
          />
        ))}
      </TreeGroup>
    </div>
  );
}

function TreeGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="tree-group-label">{label}</div>
      {children}
    </div>
  );
}

function TreeNode({
  kind,
  id,
  scenarioId,
  label,
  dim,
  selected,
  onSelect,
}: {
  kind: SelectionKind;
  id: string;
  scenarioId?: string;
  label: string;
  dim?: boolean;
  selected: boolean;
  onSelect: (sel: { kind: SelectionKind; id: string; scenarioId?: string | null }) => void;
}) {
  return (
    <button
      type="button"
      className={`tree-node${selected ? " selected" : ""}${dim ? " tree-node-dim" : ""}`}
      onClick={() => onSelect({ kind, id, scenarioId: scenarioId ?? null })}
    >
      {label}
    </button>
  );
}

/** Pick the plan for the focused carbon price, defaulting to the first. */
export function selectPlan(
  result: ScreenResult,
  carbonPriceId: string | null,
): CarbonPricePlan | null {
  if (result.plans.length === 0) return null;
  if (carbonPriceId) {
    const match = result.plans.find((p) => p.carbon_price_scenario_id === carbonPriceId);
    if (match) return match;
  }
  return result.plans[0];
}
