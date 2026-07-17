import { useMemo, useState } from "react";
import { useComposeStore } from "./compose.store";
import {
  readCarbonPrices,
  readFiscalCases,
  validateDraft,
} from "./validation";
import { runCommand, isCommandEnabled } from "../chrome/commands";
import { Badge } from "../ui/confidence";
import type {
  CarbonPriceScenario,
  CostCase,
  OperationalGrid,
  SupplyScenario,
} from "../api/types";
import { RequestDrawer } from "./RequestDrawer";
import { useFieldStore } from "../state/field.store";
import {
  sourceValidationIssue,
  studySchedulePlan,
  type StudySchedulePlan,
} from "./studyRequest";
import type { OperatingScheduleInput } from "./coverage";
import "./compose.css";

const COST_CASES: CostCase[] = ["low", "base", "high"];
const SUPPLY: SupplyScenario[] = ["optimized_pipeline", "trucking_counterfactual"];

/**
 * The study composer (design §7.2). Edits the decision surface over a loaded
 * base request, mirrors the backend 422 rules, flags trained-range excursions
 * amber, previews the scenario count, and exposes the literal request JSON.
 */
export function Composer() {
  const draft = useComposeStore((s) => s.draft);
  const setCarbonPrices = useComposeStore((s) => s.setCarbonPrices);
  const setCostCase = useComposeStore((s) => s.setCostCase);
  const setSupply = useComposeStore((s) => s.setSupplyScenarios);
  const setBudget = useComposeStore((s) => s.setAnnualBudget);
  const setProjectLife = useComposeStore((s) => s.setProjectLife);
  const setFiscal = useComposeStore((s) => s.setSelectionFiscalCase);
  const setShortlistK = useComposeStore((s) => s.setShortlistTopK);
  const setDetailedK = useComposeStore((s) => s.setDetailedTopK);
  const setGrid = useComposeStore((s) => s.setOperationalGrid);
  const fieldReservoir = useFieldStore((s) => s.reservoir);
  const reservoirRuntime = useFieldStore((s) => s.reservoirRuntime);
  const fieldWells = useFieldStore((s) => s.wells);
  const fieldSources = useFieldStore((s) => s.sources);

  const report = useMemo(() => validateDraft(draft), [draft]);
  const coverageState = useMemo(() => {
    if (!draft?.operational_grid || !reservoirRuntime) {
      return { plan: null as StudySchedulePlan | null, error: null as string | null };
    }
    try {
      return {
        plan: studySchedulePlan(draft.operational_grid, reservoirRuntime),
        error: null,
      };
    } catch (error) {
      return {
        plan: null,
        error: error instanceof Error ? error.message : "Launch-pad coverage is unavailable.",
      };
    }
  }, [draft?.operational_grid, reservoirRuntime]);
  const sourceIssue = useMemo(
    () => sourceValidationIssue(fieldSources),
    [fieldSources],
  );

  if (!draft) {
    return (
      <p className="empty-hint">
        No study definition is open. Create a study or open a saved study memo
        from the File menu.
      </p>
    );
  }

  const prices = readCarbonPrices(draft);
  const fiscal = readFiscalCases(draft);
  const supply = draft.supply_scenarios ?? SUPPLY;
  const grid = draft.operational_grid ?? null;

  return (
    <div className="composer">
      <div className="composer-cols">
        <section className="compose-section">
          <h4>Carbon prices <span className="compose-hint">≥ 4, USD/tonne</span></h4>
          <CarbonPriceEditor prices={prices} onChange={setCarbonPrices} />
        </section>

        <section className="compose-section">
          <h4>Supply & cost</h4>
          <label className="compose-row">
            <span>Cost case</span>
            <select value={draft.cost_case ?? "base"} onChange={(e) => setCostCase(e.target.value as CostCase)}>
              {COST_CASES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </label>
          <div className="compose-row">
            <span>Supply scenarios</span>
            <div className="compose-checks">
              {SUPPLY.map((s) => (
                <label key={s} className="compose-check">
                  <input
                    type="checkbox"
                    checked={supply.includes(s)}
                    onChange={(e) => {
                      const next = e.target.checked
                        ? [...supply, s]
                        : supply.filter((x) => x !== s);
                      setSupply(next.length ? next : [s]);
                    }}
                  />
                  {s.replace("_", " ")}
                </label>
              ))}
            </div>
          </div>
          <label className="compose-row">
            <span>Selection fiscal case</span>
            <select value={draft.selection_fiscal_case_id ?? "pre_tax"} onChange={(e) => setFiscal(e.target.value)}>
              {fiscal.map((f) => (
                <option key={f.case_id} value={f.case_id}>{f.case_id} ({f.mode})</option>
              ))}
            </select>
          </label>
        </section>

        <section className="compose-section">
          <h4>Budget & horizon</h4>
          <label className="compose-row">
            <span>Annual CO₂ budget (t/yr)</span>
            <input
              type="number"
              value={draft.annual_co2_budget_tonnes}
              min={1}
              onChange={(e) => setBudget(Number(e.target.value))}
            />
          </label>
          <label className="compose-row">
            <span>Project life (years)</span>
            <input
              type="number"
              value={draft.project_life_years ?? 8}
              min={1}
              max={50}
              onChange={(e) => setProjectLife(Number(e.target.value))}
            />
          </label>
          <label className="compose-row">
            <span>Shortlist top-k</span>
            <input
              type="number"
              value={draft.shortlist_top_k ?? 5}
              min={1}
              max={10}
              onChange={(e) => setShortlistK(Number(e.target.value))}
            />
          </label>
          <label className="compose-row">
            <span>Detailed top-k (plume)</span>
            <input
              type="number"
              value={draft.detailed_top_k ?? 5}
              min={0}
              max={10}
              onChange={(e) => setDetailedK(Number(e.target.value))}
            />
          </label>
        </section>

        <section className="compose-section compose-grid-section">
          <h4>Operational grid <span className="compose-hint">swept ranges</span></h4>
          {grid ? (
            <OperationalGridEditor
              grid={grid}
              report={report}
              coverage={coverageState.plan}
              coverageError={coverageState.error}
              runtimeAvailable={reservoirRuntime !== null}
              onChange={setGrid}
            />
          ) : (
            <p className="empty-hint">
              This study uses an explicit schedule list rather than a swept grid.
            </p>
          )}
        </section>
      </div>

      <ComposeFooter
        report={report}
        candidateCount={fieldReservoir ? fieldWells.length : draft.candidates.length}
        scheduleCount={
          fieldReservoir
            ? coverageState.plan?.schedules.length ?? 0
            : report.scheduleCount
        }
        fieldIssue={
          fieldReservoir && !reservoirRuntime
            ? "Relink the imported reservoir model before screening."
            : fieldReservoir && fieldSources.length === 0
              ? "Add at least one CO2 source in the basin view before screening."
              : fieldReservoir && sourceIssue
                ? sourceIssue
                : coverageState.error
        }
      />
    </div>
  );
}

function CarbonPriceEditor({
  prices,
  onChange,
}: {
  prices: CarbonPriceScenario[];
  onChange: (prices: CarbonPriceScenario[]) => void;
}) {
  return (
    <div className="carbon-editor">
      {prices.map((p, i) => (
        <div key={p.scenario_id} className="carbon-row">
          <span className="mono carbon-id">{p.scenario_id}</span>
          <input
            type="number"
            value={p.carbon_price_usd_per_tonne}
            min={0}
            step={1}
            onChange={(e) => {
              const next = prices.slice();
              next[i] = { ...p, carbon_price_usd_per_tonne: Number(e.target.value) };
              onChange(next);
            }}
          />
          <button
            type="button"
            className="carbon-del"
            aria-label={`Remove ${p.scenario_id}`}
            disabled={prices.length <= 4}
            onClick={() => onChange(prices.filter((_, j) => j !== i))}
          >
            ✕
          </button>
        </div>
      ))}
      <button
        type="button"
        className="btn carbon-add"
        onClick={() => {
          const id = `cp_custom_${prices.length + 1}`;
          onChange([
            ...prices,
            {
              scenario_id: id,
              carbon_price_usd_per_tonne: 20,
              source_type: "economic_assumption",
              provenance: prices[0]?.provenance ?? [],
            },
          ]);
        }}
      >
        + Add price
      </button>
    </div>
  );
}

function OperationalGridEditor({
  grid,
  report,
  coverage,
  coverageError,
  runtimeAvailable,
  onChange,
}: {
  grid: OperationalGrid;
  report: ReturnType<typeof validateDraft>;
  coverage: StudySchedulePlan | null;
  coverageError: string | null;
  runtimeAvailable: boolean;
  onChange: (grid: OperationalGrid) => void;
}) {
  const dims: { key: keyof OperationalGrid; label: string }[] = [
    { key: "injection_rate_m3_day", label: "Injection rate (m³/day)" },
    { key: "injection_duration_days", label: "Injection duration (days)" },
    { key: "soak_duration_days", label: "Soak duration (days)" },
    { key: "production_duration_days", label: "Production duration (days)" },
    { key: "production_bhp_psi", label: "Production BHP (psi)" },
    { key: "cycles", label: "Cycles" },
  ];
  const warnFields = new Set(report.warnings.map((w) => w.field));
  return (
    <div className="grid-editor">
      <ScheduleCoveragePanel
        coverage={coverage}
        error={coverageError}
        runtimeAvailable={runtimeAvailable}
      />
      {dims.map(({ key, label }) => {
        const warned = warnFields.has(`operational_grid.${key}`);
        return (
          <label key={key} className={`compose-row${warned ? " compose-warn" : ""}`}>
            <span>{label}</span>
            <NumberListInput
              values={grid[key]}
              integer={key === "cycles"}
              onChange={(values) => onChange({ ...grid, [key]: values })}
            />
          </label>
        );
      })}
    </div>
  );
}

function scheduleKey(schedule: OperatingScheduleInput): string {
  return [
    schedule.injection_rate_m3_day,
    schedule.injection_duration_days,
    schedule.soak_duration_days,
    schedule.production_duration_days,
    schedule.production_bhp_psi,
    schedule.cycles,
  ].join("|");
}

function ScheduleCoveragePanel({
  coverage,
  error,
  runtimeAvailable,
}: {
  coverage: StudySchedulePlan | null;
  error: string | null;
  runtimeAvailable: boolean;
}) {
  if (error) {
    return <p className="coverage-message coverage-error">{error}</p>;
  }
  if (!runtimeAvailable || !coverage) {
    return (
      <p className="coverage-message">
        Relink the imported reservoir model to calculate launch-pad coverage.
      </p>
    );
  }

  const rows = [
    ...coverage.coverage.enabled.map((schedule) => ({ schedule, covered: true })),
    ...coverage.coverage.disabled.map((schedule) => ({ schedule, covered: false })),
  ];
  return (
    <div className="schedule-coverage" aria-label="Launch-pad schedule coverage">
      <div className="coverage-summary">
        <div>
          <strong>
            {coverage.coverage.covered.toLocaleString()} / {coverage.coverage.total.toLocaleString()}
          </strong>
          <span>grid schedules covered</span>
        </div>
        <Badge tone={coverage.coverage.covered === coverage.coverage.total ? "ok" : "warning"}>
          {coverage.coverage.covered === coverage.coverage.total ? "complete" : "limited"}
        </Badge>
      </div>
      {coverage.usesNativeFallback ? (
        <p className="coverage-native">
          The imported native schedule is real and runnable but outside this {coverage.coverage.total.toLocaleString()}-point grid; Screen runs that one schedule.
        </p>
      ) : coverage.native.available && !coverage.native.onGrid ? (
        <p className="coverage-native">
          One additional native launch pad is outside the active grid.
        </p>
      ) : null}
      {coverage.coverage.disabled.length > 0 ? (
        <p className="coverage-explanation">
          no launch pad for this schedule — import a bank or run MRST offline
        </p>
      ) : null}
      <details className="coverage-details">
        <summary>Review all {rows.length.toLocaleString()} combinations</summary>
        <div className="coverage-table" role="table" aria-label="Schedule combinations">
          <div className="coverage-row coverage-head" role="row">
            <span>rate</span><span>inj.</span><span>soak</span><span>prod.</span><span>BHP</span><span>cycles</span><span>status</span>
          </div>
          {rows.map(({ schedule, covered }) => (
            <div
              key={scheduleKey(schedule)}
              className={`coverage-row${covered ? "" : " coverage-row-disabled"}`}
              role="row"
              aria-disabled={!covered}
            >
              <span>{schedule.injection_rate_m3_day.toLocaleString()}</span>
              <span>{schedule.injection_duration_days}</span>
              <span>{schedule.soak_duration_days}</span>
              <span>{schedule.production_duration_days}</span>
              <span>{schedule.production_bhp_psi}</span>
              <span>{schedule.cycles}</span>
              <span>{covered ? "covered" : "unavailable"}</span>
            </div>
          ))}
        </div>
      </details>
    </div>
  );
}

function NumberListInput({
  values,
  integer,
  onChange,
}: {
  values: number[];
  integer?: boolean;
  onChange: (values: number[]) => void;
}) {
  // Local text buffer; commit the parsed list on blur so intermediate typing
  // (e.g. a trailing comma) never produces an invalid draft.
  const [text, setText] = useState(values.join(", "));
  return (
    <input
      type="text"
      className="mono"
      value={text}
      onChange={(e) => setText(e.target.value)}
      onBlur={() => {
        const out = text
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean)
          .map((s) => (integer ? Math.round(Number(s)) : Number(s)))
          .filter((n) => Number.isFinite(n));
        const next = out.length ? out : values;
        onChange(next);
        setText(next.join(", "));
      }}
    />
  );
}

function ComposeFooter({
  report,
  candidateCount,
  scheduleCount,
  fieldIssue,
}: {
  report: ReturnType<typeof validateDraft>;
  candidateCount: number;
  scheduleCount: number;
  fieldIssue: string | null;
}) {
  const [drawer, setDrawer] = useState(false);
  const ready = report.valid && !fieldIssue && scheduleCount > 0;
  return (
    <div className="compose-footer">
      <div className="compose-preview">
        <Badge tone={ready ? "ok" : "danger"}>
          {ready ? "valid" : fieldIssue ? "setup incomplete" : `${report.errors.length} error(s)`}
        </Badge>
        <span className="mono">
          {candidateCount} wells × {scheduleCount} screened schedules ={" "}
          <strong>{candidateCount * scheduleCount}</strong> scenarios
        </span>
        {report.warnings.length > 0 && (
          <Badge tone="warning">{report.warnings.length} trained-range warning(s)</Badge>
        )}
        <button type="button" className="btn" onClick={() => setDrawer((d) => !d)}>
          {drawer ? "Hide" : "Show"} request JSON
        </button>
        <button
          type="button"
          className="btn btn-accent"
          disabled={!isCommandEnabled("study.screen")}
          onClick={() => runCommand("study.screen")}
        >
          ▶ Screen
        </button>
      </div>

      {fieldIssue ? (
        <p className="compose-field-issue" role="status">{fieldIssue}</p>
      ) : null}

      {(report.errors.length > 0 || report.warnings.length > 0) && (
        <ul className="compose-issues">
          {report.errors.map((e, i) => (
            <li key={`e${i}`} className="compose-issue-error">
              <span className="mono">{e.field}</span> {e.message}
            </li>
          ))}
          {report.warnings.map((w, i) => (
            <li key={`w${i}`} className="compose-issue-warn">
              <span className="mono">{w.field}</span> {w.message}
            </li>
          ))}
        </ul>
      )}

      {drawer && <RequestDrawer />}
    </div>
  );
}
