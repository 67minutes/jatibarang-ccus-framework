import { Panel } from "../ui/Panel";
import { useLedgerStore } from "../state/ledger.store";
import { useSelectionStore } from "../state/selection.store";
import { selectPlan } from "./ProjectTree";
import { FacilityPFD } from "../results/FacilityPFD";
import { Badge, FlagList, ConfidenceNote } from "../ui/confidence";
import { num, usd, tonnes } from "../util/format";
import type {
  BuiltSegment,
  CarbonPricePlan,
  WellStrategyResult,
} from "../api/types";
import { useComposeStore } from "../compose/compose.store";
import { useStudyStore } from "../state/study.store";
import { useFieldStore } from "../state/field.store";

/**
 * The inspector (right region): properties, results, and confidence flags for
 * the current selection. The FieldTwin properties panel, repurposed for results
 * rather than editable geometry — the scene is read-only.
 */
export function Inspector() {
  const activeEntry = useLedgerStore((s) => s.entryById(s.activeEntryId));
  const selection = useSelectionStore((s) => s.selection);
  const carbonPriceId = useSelectionStore((s) => s.carbonPriceId);
  const draft = useComposeStore((s) => s.draft);
  const study = useStudyStore((s) => s.study);
  const fieldReservoir = useFieldStore((s) => s.reservoir);
  const placement = useFieldStore((s) => s.placement);
  const wells = useFieldStore((s) => s.wells);
  const sources = useFieldStore((s) => s.sources);

  const plan = activeEntry ? selectPlan(activeEntry.result, carbonPriceId) : null;

  return (
    <Panel title="Inspector">
      {!activeEntry && fieldReservoir && placement ? (
        <FieldSetupDetail
          selection={selection}
          fieldName={placement.name}
          modelFile={fieldReservoir.source_file}
          wells={wells}
          sources={sources}
        />
      ) : !activeEntry && draft ? (
        <div className="study-draft-inspector">
          <h3>{study.name}</h3>
          <p>{draft.candidates.length} candidate wells {"\u00b7"} draft ready to screen</p>
          {study.analyst && <p>Analyst: {study.analyst}</p>}
        </div>
      ) : !activeEntry ? (
        <p className="empty-hint">No study loaded.</p>
      ) : selection.kind === "none" || !selection.id ? (
        <p className="empty-hint">
          Select a well, route, or facility in the tree, scene, or ranking table.
        </p>
      ) : !plan ? (
        <p className="empty-hint">No plan available for the current carbon price.</p>
      ) : (
        <SelectionDetail
          plan={plan}
          kind={selection.kind}
          id={selection.id}
          sharedReservoir={Boolean(fieldReservoir)}
        />
      )}
    </Panel>
  );
}

function SelectionDetail({
  plan,
  kind,
  id,
  sharedReservoir,
}: {
  plan: CarbonPricePlan;
  kind: string;
  id: string;
  sharedReservoir: boolean;
}) {
  if (kind === "well") {
    const strat = plan.well_strategies.find((w) => w.candidate_id === id);
    if (strat) {
      return (
        <WellDetail
          plan={plan}
          strat={strat}
          sharedReservoir={sharedReservoir}
        />
      );
    }
  }
  if (kind === "route") {
    const seg = plan.pipeline.built_segments.find((s) => s.segment_id === id);
    if (seg) return <RouteDetail seg={seg} />;
  }
  if (kind === "facility") {
    const well = plan.facility?.well_results.find((w) => w.candidate_id === id);
    if (well) return <FacilityPFD well={well} />;
  }
  return <p className="empty-hint">No detail for {kind} {id} at this price.</p>;
}

function WellDetail({
  plan,
  strat,
  sharedReservoir,
}: {
  plan: CarbonPricePlan;
  strat: WellStrategyResult;
  sharedReservoir: boolean;
}) {
  const selected = plan.selected_wells.includes(strat.candidate_id);
  const conf = strat.prediction.confidence;
  const extrap = strat.prediction.extrapolation_flags.filter((f) => f.is_extrapolation);
  return (
    <div>
      <div className="inspector-head">
        <h3>{strat.candidate_id}</h3>
        <Badge tone={selected ? "ok" : "neutral"}>{selected ? "selected" : "not selected"}</Badge>
      </div>
      <dl className="kv">
        <dt>Scenario</dt>
        <dd>{strat.scenario_id}</dd>
        <dt>Preliminary NPV</dt>
        <dd>{usd(strat.preliminary_npv_usd)}</dd>
        <dt>Pre-logistics value</dt>
        <dd>{usd(strat.pre_logistics_value_usd)}</dd>
        <dt>Annual demand</dt>
        <dd>{tonnes(strat.annual_demand_tonnes)}</dd>
        <dt>Peak mass flow</dt>
        <dd>{num(strat.peak_mass_flow_kg_s, 2)} kg/s</dd>
      </dl>

      {sharedReservoir ? <SharedReservoirNotice /> : null}
      <WellInterferenceWarnings plan={plan} wellId={strat.candidate_id} />

      {conf.extended_horizon && (
        <div style={{ margin: "6px 0" }}>
          <Badge tone="warning" title="Forecast extends beyond the validated horizon">
            extended horizon
          </Badge>
        </div>
      )}
      {extrap.length > 0 && (
        <div style={{ margin: "6px 0" }}>
          <Badge tone="warning">out of trained range</Badge>
          <ul className="confidence-note" style={{ paddingLeft: 18 }}>
            {extrap.map((f) => (
              <li key={f.quantity}>
                {f.quantity}: {num(f.observed_min, 2)}–{num(f.observed_max, 2)} vs trained{" "}
                {num(f.trained_min, 2)}–{num(f.trained_max, 2)}
              </li>
            ))}
          </ul>
        </div>
      )}
      <ConfidenceNote reasons={conf.low_confidence_reasons} />
      <FlagList flags={strat.flags} />
    </div>
  );
}

/**
 * Render only overlap pairs explicitly returned by the active price plan.
 * The Inspector deliberately does not reconstruct overlap from distance or
 * radius values: that scientific verdict belongs to the backend audit.
 */
export function WellInterferenceWarnings({
  plan,
  wellId,
}: {
  plan: CarbonPricePlan;
  wellId: string;
}) {
  const pairs = plan.interference.flagged_pairs.filter(
    (pair) =>
      pair.overlap &&
      (pair.first_well_id === wellId || pair.second_well_id === wellId),
  );
  if (pairs.length === 0) return null;

  return (
    <section className="confidence-note" aria-label="Interference warnings">
      <Badge tone="warning">
        {pairs.length === 1 ? "interference overlap" : `${pairs.length} interference overlaps`}
      </Badge>
      <ul>
        {pairs.map((pair) => {
          const otherWell =
            pair.first_well_id === wellId
              ? pair.second_well_id
              : pair.first_well_id;
          return (
            <li key={`${pair.first_well_id}-${pair.second_well_id}`}>
              {otherWell}: {num(pair.distance_m, 0)} m spacing vs{" "}
              {num(pair.radius_sum_m, 0)} m combined influence radius
              {pair.recommendations.length > 0 ? (
                <ul aria-label={`Recommendations for ${otherWell}`}>
                  {pair.recommendations.map((recommendation) => (
                    <li key={recommendation}>{recommendation.replace(/_/g, " ")}</li>
                  ))}
                </ul>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function SharedReservoirNotice() {
  return (
    <p className="shared-reservoir-notice">
      Reservoir response assumes the local geology at this site matches the
      study&apos;s reservoir model.
    </p>
  );
}

function FieldSetupDetail({
  selection,
  fieldName,
  modelFile,
  wells,
  sources,
}: {
  selection: ReturnType<typeof useSelectionStore.getState>["selection"];
  fieldName: string;
  modelFile: string;
  wells: ReturnType<typeof useFieldStore.getState>["wells"];
  sources: ReturnType<typeof useFieldStore.getState>["sources"];
}) {
  if (selection.kind === "well" && selection.id) {
    const well = wells.find((item) => item.id === selection.id);
    if (well) {
      return (
        <div>
          <div className="inspector-head">
            <h3>{well.name}</h3>
            <Badge tone={well.kind === "native" ? "ok" : "neutral"}>
              {well.kind === "native" ? "model well" : "candidate"}
            </Badge>
          </div>
          <dl className="kv">
            <dt>Stable ID</dt>
            <dd>{well.id}</dd>
            <dt>Latitude</dt>
            <dd>{well.lat.toFixed(6)}</dd>
            <dt>Longitude</dt>
            <dd>{well.lon.toFixed(6)}</dd>
            <dt>Reservoir model</dt>
            <dd>{modelFile}</dd>
          </dl>
          <SharedReservoirNotice />
        </div>
      );
    }
  }
  if (selection.kind === "source" && selection.id) {
    const source = sources.find((item) => item.id === selection.id);
    if (source) {
      return (
        <div>
          <div className="inspector-head">
            <h3>{source.name}</h3>
            <Badge tone="neutral">CO₂ source</Badge>
          </div>
          <dl className="kv">
            <dt>Annual capacity</dt>
            <dd>{tonnes(source.annual_capacity_t)}/yr</dd>
            <dt>Peak flow</dt>
            <dd>{num(source.max_mass_flow_kg_s, 2)} kg/s</dd>
            <dt>Outlet pressure</dt>
            <dd>{num(source.outlet_pressure_bar, 1)} bar</dd>
            <dt>CO₂ purity</dt>
            <dd>{(source.co2_purity * 100).toFixed(1)}%</dd>
          </dl>
        </div>
      );
    }
  }
  return (
    <div className="study-draft-inspector">
      <h3>{fieldName}</h3>
      <p>{modelFile}</p>
      <p>
        {wells.length} well{wells.length === 1 ? "" : "s"} · {sources.length}{" "}
        source{sources.length === 1 ? "" : "s"}
      </p>
      <p>Select or right-click an object in the basin scene to inspect or edit it.</p>
    </div>
  );
}

function RouteDetail({ seg }: { seg: BuiltSegment }) {
  return (
    <div>
      <div className="inspector-head">
        <h3>{seg.from_node} → {seg.to_node}</h3>
        <Badge tone={seg.dense_phase_ok ? "ok" : "danger"}>
          {seg.dense_phase_ok ? "dense-phase ok" : "dense-phase violated"}
        </Badge>
      </div>
      <dl className="kv">
        <dt>Length</dt>
        <dd>{num(seg.length_km, 2)} km</dd>
        <dt>Diameter</dt>
        <dd>{num(seg.diameter_in, 1)} in</dd>
        <dt>Flow</dt>
        <dd>{tonnes(seg.flow_tonnes_per_year)}/yr</dd>
        <dt>Inlet / outlet</dt>
        <dd>{num(seg.inlet_pressure_bar, 1)} / {num(seg.outlet_pressure_bar, 1)} bar</dd>
        <dt>Pressure drop</dt>
        <dd>{num(seg.pressure_drop_bar, 2)} bar</dd>
        <dt>Velocity</dt>
        <dd>{num(seg.velocity_m_s, 2)} m/s</dd>
      </dl>
      <p className="empty-hint" style={{ paddingLeft: 0 }}>
        Pressure-along-route profile renders in the viewport when this route is
        selected.
      </p>
    </div>
  );
}
