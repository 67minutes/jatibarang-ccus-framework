import { useMemo, useState } from "react";
import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useLedgerStore } from "../state/ledger.store";
import { useSelectionStore } from "../state/selection.store";
import { displayPredictions, type DisplayPrediction } from "./displayData";
import "./results.css";

/**
 * Production & storage curves from the detailed predictions (top-k scenarios
 * with full series). Screening shows scenario spaghetti with the selected
 * scenario highlighted.
 */

type Field = "cumulative_oil_m3" | "cumulative_gas_m3" | "co2_inventory_tonnes";

const FIELDS: { key: Field; label: string }[] = [
  { key: "cumulative_oil_m3", label: "Cumulative oil (m³)" },
  { key: "cumulative_gas_m3", label: "Cumulative gas (m³)" },
  { key: "co2_inventory_tonnes", label: "Net CO₂ stored (t)" },
];

export function Production() {
  const activeEntry = useLedgerStore((s) => s.entryById(s.activeEntryId));
  const selection = useSelectionStore((s) => s.selection);
  const carbonPriceId = useSelectionStore((s) => s.carbonPriceId);
  const [field, setField] = useState<Field>("cumulative_oil_m3");

  const result = activeEntry?.result ?? null;
  const predictions = useMemo(
    () => (result ? displayPredictions(result, carbonPriceId) : []),
    [result, carbonPriceId],
  );

  const { data, series, labelOf } = useMemo(() => toChart(predictions, field), [predictions, field]);

  if (!result) {
    return <p className="empty-hint">No results yet. Production curves appear after a run.</p>;
  }
  if (predictions.length === 0) {
    return (
      <p className="empty-hint">
        No predictions available for this study.
      </p>
    );
  }

  const selectedScenario = selection.scenarioId ?? null;

  return (
    <div className="production">
      <div className="production-controls">
        {FIELDS.map((f) => (
          <button
            key={f.key}
            type="button"
            className={`chip${field === f.key ? " chip-active" : ""}`}
            onClick={() => setField(f.key)}
          >
            {f.label}
          </button>
        ))}
      </div>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 8 }}>
          <XAxis
            dataKey="step"
            tick={{ fontSize: 10, fill: "#9aa0a8" }}
            stroke="#34383f"
            label={{ value: "timeline step", fontSize: 10, fill: "#6b7178", position: "insideBottom", dy: 10 }}
          />
          <YAxis tick={{ fontSize: 10, fill: "#9aa0a8" }} stroke="#34383f" width={60} />
          <Tooltip
            contentStyle={{ background: "#202329", border: "1px solid #454a52", fontSize: 11 }}
          />
          {series.map((sid) => {
            const isSel =
              sid === selectedScenario ||
              (selection.kind === "well" && labelOf(sid) === selection.id);
            return (
              <Line
                key={sid}
                name={labelOf(sid)}
                type="monotone"
                dataKey={sid}
                stroke={isSel ? "#d1352b" : "#5a6068"}
                strokeWidth={isSel ? 2.4 : 1}
                dot={false}
                isAnimationActive={false}
                connectNulls
              />
            );
          })}
        </LineChart>
      </ResponsiveContainer>
      <p className="empty-hint" style={{ paddingLeft: 0 }}>
        {predictions.length > 1
          ? "Overlapping lines indicate identical wells (uniform demo geology). Select a well to highlight it."
          : "Select a shortlist row or well to highlight its scenario."}
      </p>
    </div>
  );
}

interface ChartRow {
  step: number;
  [scenarioId: string]: number | null;
}

function toChart(
  predictions: DisplayPrediction[],
  field: Field,
): { data: ChartRow[]; series: string[]; labelOf: (sid: string) => string } {
  const series = predictions.map((p) => p.scenarioId);
  const labels = new Map(predictions.map((p) => [p.scenarioId, p.candidateId]));
  const maxLen = Math.max(0, ...predictions.map((p) => seriesFor(p.prediction, field).length));
  const data: ChartRow[] = [];
  for (let i = 0; i < maxLen; i++) {
    const row: ChartRow = { step: i };
    for (const p of predictions) {
      const values = seriesFor(p.prediction, field);
      const v = values[i];
      row[p.scenarioId] = v == null || !Number.isFinite(v) ? null : v;
    }
    data.push(row);
  }
  return { data, series, labelOf: (sid) => labels.get(sid) ?? sid };
}

function seriesFor(p: DisplayPrediction["prediction"], field: Field): (number | null)[] {
  if (field === "co2_inventory_tonnes") return p.inventory.co2_inventory_tonnes;
  return p.production[field];
}
