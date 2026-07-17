import { useMemo } from "react";
import { useLedgerStore } from "../state/ledger.store";
import { useSelectionStore } from "../state/selection.store";
import { planForPrice, selectionAtPrice } from "./priceScrubber";
import { preliminaryRanking } from "./displayData";
import { Badge } from "../ui/confidence";
import { usd } from "../util/format";
import type { ScreenFlag, ScreenResult } from "../api/types";
import { scientificDisplayText } from "../ui/presentation";
import "./results.css";

/**
 * The ranking table — the results anchor. Rows are shortlist items; selecting a
 * row drives the global selection. Each row shows whether the well is in the
 * selected set at the focused carbon price, and carries any cell-addressable
 * flags for that well.
 */
export function RankingTable() {
  const activeEntry = useLedgerStore((s) => s.entryById(s.activeEntryId));
  const carbonPriceId = useSelectionStore((s) => s.carbonPriceId);
  const selection = useSelectionStore((s) => s.selection);
  const select = useSelectionStore((s) => s.select);

  const result = activeEntry?.result ?? null;
  const flagsByWell = useMemo(
    () => (result ? flagIndex(result, carbonPriceId) : new Map<string, ScreenFlag[]>()),
    [result, carbonPriceId],
  );

  if (!result) {
    return <p className="empty-hint">No results yet. Run a screening study to populate the ranking.</p>;
  }

  const plan = planForPrice(result, carbonPriceId);
  const selected = plan ? selectionAtPrice(result, plan.carbon_price_scenario_id) : new Set<string>();
  const focusPrice = plan?.carbon_price_usd_per_tonne;

  // No development shortlist (e.g. no viable pipeline at HnP volumes): fall back
  // to a pre-logistics well ranking so the panel stays useful and honest.
  if (result.shortlist.length === 0) {
    return <PreLogisticsRanking plan={plan} focusPrice={focusPrice} />;
  }

  return (
    <div className="ranking">
      <div className="ranking-caption">
        Shortlist across carbon prices · selection shown for{" "}
        <strong>{focusPrice != null ? `$${focusPrice}/t` : "—"}</strong>
        {result.status === "completed_with_failures" && (
          <Badge tone="warning" title="Some scenarios failed; see the run console">
            partial
          </Badge>
        )}
      </div>
      <table className="data-table">
        <thead>
          <tr>
            <th className="num">#</th>
            <th>Candidate</th>
            <th>At focus price</th>
            <th className="num">Designated NPV</th>
            <th>Prices</th>
            <th>Notes</th>
          </tr>
        </thead>
        <tbody>
          {result.shortlist.map((item) => {
            const isSelectedRow = selection.kind === "well" && selection.id === item.candidate_id;
            const inSelection = selected.has(item.candidate_id);
            const flags = flagsByWell.get(item.candidate_id) ?? [];
            return (
              <tr
                key={`${item.rank}-${item.candidate_id}`}
                className={isSelectedRow ? "row-selected" : ""}
                onClick={() =>
                  select({ kind: "well", id: item.candidate_id, scenarioId: item.scenario_id })
                }
              >
                <td className="num">{item.rank}</td>
                <td className="mono">{item.candidate_id}</td>
                <td>
                  <Badge tone={inSelection ? "ok" : "neutral"}>
                    {inSelection ? "in selection" : "dropped"}
                  </Badge>
                </td>
                <td className="num">{usd(item.designated_npv_usd)}</td>
                <td className="mono ranking-prices">{item.carbon_price_scenario_ids.length}</td>
                <td className="ranking-notes">
                  {item.reasons
                    .slice(0, 2)
                    .map((reason) => scientificDisplayText(reason.replace(/_/g, " ")))
                    .join("; ")}
                  {flags.length > 0 && (
                    <Badge
                      tone={flags.some((f) => f.severity === "blocking") ? "danger" : "warning"}
                      title={flags
                        .map(
                          (flag) =>
                            `${scientificDisplayText(flag.code.replace(/_/g, " "))}: ${scientificDisplayText(flag.message)}`,
                        )
                        .join("\n")}
                    >
                      {flags.length} flag{flags.length > 1 ? "s" : ""}
                    </Badge>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function PreLogisticsRanking({
  plan,
  focusPrice,
}: {
  plan: import("../api/types").CarbonPricePlan | null;
  focusPrice: number | undefined;
}) {
  const selection = useSelectionStore((s) => s.selection);
  const select = useSelectionStore((s) => s.select);
  const rows = preliminaryRanking(plan);
  if (rows.length === 0) {
    return <p className="empty-hint">No candidate wells to rank for this study.</p>;
  }
  const reason = plan?.pipeline.domain_status ?? "no_viable_network";
  return (
    <div className="ranking">
      <div className="ranking-caption">
        No development shortlist at <strong>{focusPrice != null ? `$${focusPrice}/t` : "—"}</strong> —{" "}
        <Badge tone="warning" title={scientificDisplayText(reason)}>
          {scientificDisplayText(reason.replace(/_/g, " "))}
        </Badge>
        <span>showing pre-logistics well ranking</span>
      </div>
      <table className="data-table">
        <thead>
          <tr>
            <th className="num">#</th>
            <th>Candidate</th>
            <th className="num">Preliminary NPV</th>
            <th className="num">Pre-logistics value</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={row.candidateId}
              className={selection.kind === "well" && selection.id === row.candidateId ? "row-selected" : ""}
              onClick={() => select({ kind: "well", id: row.candidateId, scenarioId: row.scenarioId })}
            >
              <td className="num">{i + 1}</td>
              <td className="mono">{row.candidateId}</td>
              <td className="num">{usd(row.preliminaryNpv)}</td>
              <td className="num">{usd(row.preLogisticsValue)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="empty-hint" style={{ paddingLeft: 0 }}>
        At Huff-and-Puff CO₂ volumes a dedicated pipeline is not economic; the
        wells remain individually valuable pre-logistics. Trucking supply is the
        indicated mode. Final development economics require a viable network.
      </p>
    </div>
  );
}

/** Index flags by candidate for the focused plan (cell-addressable warnings). */
function flagIndex(result: ScreenResult, carbonPriceId: string | null): Map<string, ScreenFlag[]> {
  const plan = planForPrice(result, carbonPriceId);
  const byWell = new Map<string, ScreenFlag[]>();
  if (!plan) return byWell;
  const add = (candidateId: string, flag: ScreenFlag) => {
    const list = byWell.get(candidateId) ?? [];
    list.push(flag);
    byWell.set(candidateId, list);
  };
  for (const strat of plan.well_strategies) {
    for (const flag of strat.flags) add(strat.candidate_id, flag);
  }
  // Plan-level flags scoped by scenario_ids map to their wells via strategies.
  const scenarioToWell = new Map(plan.well_strategies.map((s) => [s.scenario_id, s.candidate_id]));
  for (const flag of plan.flags) {
    for (const scenarioId of flag.scenario_ids) {
      const well = scenarioToWell.get(scenarioId);
      if (well) add(well, flag);
    }
  }
  return byWell;
}
