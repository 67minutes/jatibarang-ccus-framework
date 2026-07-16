import { useMemo } from "react";
import {
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useLedgerStore } from "../state/ledger.store";
import { useSelectionStore } from "../state/selection.store";
import {
  carbonPriceAxis,
  economicForPlan,
  kpiSummary,
  planForPrice,
} from "./priceScrubber";
import { Badge, ConfidenceNote, CostBasisBanner } from "../ui/confidence";
import { num, pct, tonnes, usd } from "../util/format";
import type { EconomicBreakdown, InlineScreenRequest } from "../api/types";
import "./results.css";

/**
 * The economics panel with the carbon-price scrubber (design §7.4). Dragging
 * the scrubber re-pivots the KPIs, the NPV curve marker, and — via the shared
 * carbon-price selection — the ranking and scene, all client-side.
 */
export function Economics() {
  const activeEntry = useLedgerStore((s) => s.entryById(s.activeEntryId));
  const carbonPriceId = useSelectionStore((s) => s.carbonPriceId);
  const setCarbonPrice = useSelectionStore((s) => s.setCarbonPrice);

  const result = activeEntry?.result ?? null;
  const fiscalCaseId =
    (activeEntry?.request as InlineScreenRequest | undefined)?.selection_fiscal_case_id ?? "pre_tax";

  const axis = useMemo(() => (result ? carbonPriceAxis(result) : []), [result]);
  const curve = useMemo(() => {
    if (!result) return [];
    return axis.map((point) => {
      const plan = planForPrice(result, point.scenarioId);
      const econ = plan ? economicForPlan(plan, fiscalCaseId) : null;
      return { price: point.price, npv: econ ? econ.npv_usd : null, scenarioId: point.scenarioId };
    });
  }, [result, axis, fiscalCaseId]);

  if (!result) {
    return <p className="empty-hint">No results yet. Economics appear after a screening run.</p>;
  }

  const plan = planForPrice(result, carbonPriceId);
  const econ = plan ? economicForPlan(plan, fiscalCaseId) : null;
  const kpi = kpiSummary(econ);
  const anyEconomics = result.plans.some((p) => (p.economics?.results.length ?? 0) > 0);
  const focusIndex = Math.max(
    0,
    axis.findIndex((p) => p.scenarioId === (plan?.carbon_price_scenario_id ?? "")),
  );
  const focusPrice = axis[focusIndex]?.price ?? 0;

  return (
    <div className="economics">
      <div className="scrubber">
        <div className="scrubber-head">
          <span className="scrubber-label">Carbon price</span>
          <span className="scrubber-value">${focusPrice}/t</span>
          {result.cross_price_comparison.pivot_observed && (
            <Badge tone="info" title="The selected set changes across carbon prices">
              pivot
            </Badge>
          )}
        </div>
        <input
          type="range"
          min={0}
          max={Math.max(0, axis.length - 1)}
          step={1}
          value={focusIndex}
          onChange={(e) => {
            const point = axis[Number(e.target.value)];
            if (point) setCarbonPrice(point.scenarioId);
          }}
          className="scrubber-range"
          aria-label="Carbon price"
        />
        <div className="scrubber-ticks">
          {axis.map((p) => (
            <span key={p.scenarioId}>${p.price}</span>
          ))}
        </div>
      </div>

      {!anyEconomics && (
        <div className="no-econ-note">
          No development economics: no carbon price produced a viable network
          (<span className="mono">{plan?.pipeline.domain_status ?? "no_viable_network"}</span>).
          At Huff-and-Puff volumes trucking is the indicated supply mode; NPV
          requires a selected development. Pre-logistics well values are in the
          Ranking tab.
        </div>
      )}

      <div className="npv-curve">
        <ResponsiveContainer width="100%" height={120}>
          <LineChart data={curve} margin={{ top: 6, right: 12, bottom: 0, left: 0 }}>
            <XAxis dataKey="price" tick={{ fontSize: 10, fill: "#9aa0a8" }} stroke="#34383f" />
            <YAxis
              tick={{ fontSize: 10, fill: "#9aa0a8" }}
              stroke="#34383f"
              tickFormatter={(v) => usd(v)}
              width={54}
            />
            <Tooltip
              contentStyle={{ background: "#202329", border: "1px solid #454a52", fontSize: 11 }}
              formatter={(v: number) => usd(v)}
              labelFormatter={(l) => `$${l}/t`}
            />
            <ReferenceLine x={focusPrice} stroke="#d1352b" strokeWidth={1.5} />
            <ReferenceLine y={0} stroke="#454a52" strokeDasharray="3 3" />
            <Line type="monotone" dataKey="npv" stroke="#93b83a" strokeWidth={2} dot={{ r: 2 }} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="kpi-row">
        <Kpi label="NPV" value={usd(kpi.npv)} sub={kpi.npvLow != null ? `${usd(kpi.npvLow)} … ${usd(kpi.npvHigh)}` : undefined} accent />
        <Kpi label="IRR" value={kpi.irr != null ? pct(kpi.irr) : statusOf(econ, "irr")} />
        <Kpi label="Break-even carbon" value={kpi.breakEvenCarbon != null ? `$${num(kpi.breakEvenCarbon, 1)}/t` : statusOf(econ, "carbon")} />
        <Kpi label="Break-even oil" value={kpi.breakEvenOil != null ? `$${num(kpi.breakEvenOil, 1)}/bbl` : statusOf(econ, "oil")} />
        <Kpi label="Net CO₂ stored" value={tonnes(kpi.netStored)} />
      </div>

      {econ && <Breakdown breakdown={econ.breakdown} />}

      <ConfidenceNote reasons={kpi.confidenceReasons} />
      <CostBasisBanner what="Economic outputs" />
    </div>
  );
}

function statusOf(
  econ: ReturnType<typeof economicForPlan>,
  which: "irr" | "carbon" | "oil",
): string {
  if (!econ) return "—";
  if (which === "irr") return econ.irr.status.replace(/_/g, " ");
  if (which === "carbon") return econ.break_even_carbon_price.status.replace(/_/g, " ");
  return econ.break_even_oil_price.status.replace(/_/g, " ");
}

function Kpi({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: boolean;
}) {
  return (
    <div className={`kpi${accent ? " kpi-accent" : ""}`}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {sub && <div className="kpi-sub mono">{sub}</div>}
    </div>
  );
}

function Breakdown({ breakdown }: { breakdown: EconomicBreakdown }) {
  const revenue = [
    { label: "Oil revenue", value: breakdown.oil_revenue_usd },
    { label: "Gas revenue", value: breakdown.gas_revenue_usd },
    { label: "Carbon revenue", value: breakdown.carbon_revenue_usd },
  ];
  const cost = [
    { label: "CO₂ supply & transport", value: breakdown.co2_supply_and_transport_usd },
    { label: "Facility CAPEX", value: breakdown.facility_capex_usd },
    { label: "Facility OPEX", value: breakdown.facility_opex_usd },
    { label: "Pipeline CAPEX", value: breakdown.pipeline_capex_usd + breakdown.booster_capex_usd },
    { label: "Lifting", value: breakdown.lifting_cost_usd },
    { label: "Workover", value: breakdown.workover_cost_usd },
    { label: "MRV", value: breakdown.mrv_cost_usd },
    { label: "Carbon tax", value: breakdown.carbon_tax_usd },
  ].filter((c) => c.value > 0);
  const max = Math.max(breakdown.total_revenue_usd, breakdown.total_cost_usd, 1);

  return (
    <div className="breakdown">
      <div className="breakdown-col">
        <h5>Revenue · {usd(breakdown.total_revenue_usd)}</h5>
        {revenue.map((r) => (
          <Bar key={r.label} label={r.label} value={r.value} max={max} tone="rev" />
        ))}
      </div>
      <div className="breakdown-col">
        <h5>Cost · {usd(breakdown.total_cost_usd)}</h5>
        {cost.map((c) => (
          <Bar key={c.label} label={c.label} value={c.value} max={max} tone="cost" />
        ))}
      </div>
    </div>
  );
}

function Bar({
  label,
  value,
  max,
  tone,
}: {
  label: string;
  value: number;
  max: number;
  tone: "rev" | "cost";
}) {
  return (
    <div className="bar-row">
      <span className="bar-label">{label}</span>
      <span className="bar-track">
        <span className={`bar-fill bar-${tone}`} style={{ width: `${(value / max) * 100}%` }} />
      </span>
      <span className="bar-value mono">{usd(value)}</span>
    </div>
  );
}
