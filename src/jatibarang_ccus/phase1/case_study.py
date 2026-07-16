from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
import time
from typing import Any

from jatibarang_ccus.contracts import (
    CandidateWell,
    CO2Source,
    Coordinate,
    EconomicBatchRequest,
    EconomicProvenance,
    FacilityPortfolioRequest,
    FacilityPortfolioResult,
    FacilityProvenance,
    PipelineDesignRequest,
    PortfolioEconomicInput,
    RouteLibraryRequest,
    ScreenedWellValue,
)
from jatibarang_ccus.infrastructure.economic_adapters import (
    annualize_screened_value,
    assumptions_from_basis,
    basis_provenance,
    carbon_prices_from_basis,
    combine_portfolios,
    facility_for_well,
    fiscal_cases_from_basis,
    load_economic_basis,
    pipeline_raw_supply,
    uncertainty_from_percentages,
)
from jatibarang_ccus.infrastructure.economics import evaluate_economic_batch
from jatibarang_ccus.infrastructure.facility import evaluate_facility_portfolio, facility_input_from_screened_value
from jatibarang_ccus.infrastructure.pipeline import adapt_legacy_pipeline_inputs, solve_pipeline_design
from jatibarang_ccus.infrastructure.routing import build_route_library
from jatibarang_ccus.surrogate.config import REPO_ROOT


DEFAULT_ASSUMPTIONS = REPO_ROOT / "data" / "jatibarang" / "case_study_assumptions.json"


def load_assumptions(path: Path = DEFAULT_ASSUMPTIONS) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Case-study assumptions file is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _scenario_parameters(grid: dict[str, list[Any]]) -> list[dict[str, float | int]]:
    keys = ["injection_rate_m3_day", "soak_days", "production_days", "production_bhp_psi", "cycles"]
    return [dict(zip(keys, values)) for values in itertools.product(*(grid[key] for key in keys))]


def _retention_fraction(params: dict[str, float | int]) -> float:
    soak = float(params["soak_days"])
    production = float(params["production_days"])
    return max(0.50, min(0.78, 0.64 + 0.006 * (soak - 30.0) - 0.0015 * (production - 190.0)))


def _source_model(assumptions: dict[str, Any]) -> CO2Source:
    payload = assumptions["co2_source"]
    return CO2Source(
        id=str(payload.get("id", "SUBANG")),
        name=str(payload["name"]),
        location=Coordinate(latitude=float(payload["latitude"]), longitude=float(payload["longitude"])),
        capacity_tonnes_per_year=float(payload["capacity_tonnes_per_year"]),
        max_mass_flow_kg_s=float(payload["max_mass_flow_kg_s"]),
        outlet_pressure_bar=float(payload["outlet_pressure_bar"]),
        outlet_temperature_c=float(payload["outlet_temperature_c"]),
        co2_purity=float(payload["co2_purity"]),
    )


def _candidate_models(assumptions: dict[str, Any]) -> list[CandidateWell]:
    return [
        CandidateWell(
            id=str(candidate["id"]),
            location=Coordinate(latitude=float(candidate["latitude"]), longitude=float(candidate["longitude"])),
            oil_factor=float(candidate["oil_factor"]),
            storage_factor=float(candidate["storage_factor"]),
            influence_radius_m=float(candidate.get("influence_radius_m", 500.0)),
        )
        for candidate in assumptions["candidates"]
    ]


def _evaluate_candidate(
    candidate: CandidateWell,
    params: dict[str, float | int],
    economics: dict[str, float],
    carbon_price: float,
) -> ScreenedWellValue:
    injection_rate = float(params["injection_rate_m3_day"])
    soak = float(params["soak_days"])
    production_days = float(params["production_days"])
    bhp = float(params["production_bhp_psi"])
    cycles = int(params["cycles"])

    inj_factor = (injection_rate / 9000.0) ** 0.35
    storage_inj_factor = (injection_rate / 9000.0) ** 0.90
    production_factor = (production_days / 190.0) ** 0.60
    soak_oil_factor = max(0.82, 1.0 - 0.015 * abs(soak - 30.0))
    bhp_factor = max(0.88, 1.0 - 0.0005 * abs(bhp - 675.0))

    oil_bbl = 8500.0 * candidate.oil_factor * inj_factor * production_factor * soak_oil_factor * bhp_factor * cycles
    retention = _retention_fraction(params)
    stored_co2_tonnes = 9500.0 * candidate.storage_factor * storage_inj_factor * ((soak / 30.0) ** 0.25) * cycles * retention
    injected_co2_tonnes = stored_co2_tonnes / max(retention, 1e-6)
    peak_produced_gas = 0.55 * injection_rate * (production_days / 190.0) * (1.0 + 0.05 * cycles)
    produced_co2_fraction = max(0.25, min(0.80, 0.30 + 0.07 * cycles + 0.03 * candidate.storage_factor))

    oil_margin = oil_bbl * (economics["oil_price_usd_per_bbl"] - economics["lifting_cost_usd_per_bbl"])
    carbon_revenue = stored_co2_tonnes * carbon_price * economics["certification_haircut"]
    flat_co2_cost = injected_co2_tonnes * economics["delivered_co2_cost_usd_per_tonne"]
    mrv = stored_co2_tonnes * economics["mrv_cost_usd_per_tonne"]
    workover = cycles * economics["workover_cost_usd_per_cycle"]
    preliminary_without_carbon = oil_margin - flat_co2_cost - mrv - workover

    return ScreenedWellValue(
        candidate_id=candidate.id,
        parameters=params,
        oil_bbl=oil_bbl,
        stored_co2_tonnes=stored_co2_tonnes,
        injected_co2_tonnes=injected_co2_tonnes,
        preliminary_npv_usd=preliminary_without_carbon + carbon_revenue,
        npv_without_carbon_usd=preliminary_without_carbon,
        carbon_price_usd_per_tonne=carbon_price,
        peak_produced_gas_m3_day=peak_produced_gas,
        produced_co2_fraction=produced_co2_fraction,
    )


def _best_by_candidate(results: list[ScreenedWellValue]) -> dict[str, ScreenedWellValue]:
    best: dict[str, ScreenedWellValue] = {}
    for result in results:
        current = best.get(result.candidate_id)
        if current is None or result.preliminary_npv_usd > current.preliminary_npv_usd:
            best[result.candidate_id] = result
    return best


def _ranking(
    *,
    selected_results: dict[str, Any],
    best_by_candidate: dict[str, ScreenedWellValue],
) -> list[str]:
    selected = sorted(selected_results.values(), key=lambda item: item.npv_usd, reverse=True)
    selected_ids = [item.portfolio_id for item in selected]
    unselected = [
        item.candidate_id
        for item in sorted(best_by_candidate.values(), key=lambda value: value.preliminary_npv_usd, reverse=True)
        if item.candidate_id not in selected_ids
    ]
    return selected_ids + unselected


def _priority_shift(current_rank: list[str], comparison_rank: list[str], threshold: int) -> int:
    changed = 0
    for candidate_id in current_rank:
        if abs(current_rank.index(candidate_id) - comparison_rank.index(candidate_id)) >= threshold:
            changed += 1
    return changed


def _evaluate_selected_facility_portfolio(
    *,
    best_for_selected: dict[str, ScreenedWellValue],
    node_pressures_bar: dict[str, float],
    assumptions: dict[str, Any],
    cost_case: str,
    portfolio_id: str,
) -> FacilityPortfolioResult:
    """Adapt selected Phase 1 screening values to one Feature 003 portfolio call."""

    wells = []
    for candidate_id, value in best_for_selected.items():
        delivery_pressure = node_pressures_bar.get(
            candidate_id,
            float(assumptions["pipeline"]["dense_phase_min_pressure_bar"]),
        )
        wells.append(
            facility_input_from_screened_value(
                candidate_id=candidate_id,
                parameters=value.parameters,
                injected_co2_tonnes=value.injected_co2_tonnes,
                stored_co2_tonnes=value.stored_co2_tonnes,
                delivery_pressure_bar=delivery_pressure,
                peak_produced_gas_m3_day=value.peak_produced_gas_m3_day,
                produced_co2_fraction=value.produced_co2_fraction,
                assumptions=assumptions,
            )
        )
    request = FacilityPortfolioRequest(
        portfolio_id=portfolio_id,
        cost_case=cost_case,
        design_basis_version="1.0.0",
        cost_basis_version="1.0.0",
        wells=wells,
        provenance=[
            FacilityProvenance(
                source_class="pipeline_result",
                source_id=portfolio_id,
                notes="Selected-well delivery pressures and ownership boundary from Feature 002.",
            )
        ],
    )
    return evaluate_facility_portfolio(request)


def run_screening(
    assumptions: dict[str, Any],
    *,
    mrst_mean_seconds: float,
    surrogate_uncertainty: dict[str, float] | None = None,
) -> dict[str, Any]:
    grid = _scenario_parameters(assumptions["screening_grid"])
    economics = assumptions["economics"]
    carbon_prices = assumptions["carbon_prices_usd_per_tonne"]
    source = _source_model(assumptions)
    candidates = _candidate_models(assumptions)
    scenario_count = len(grid) * len(candidates)
    uncertainty = surrogate_uncertainty or {"production_error_pct": 0.0, "co2_mass_error_pct": 0.0}
    economic_basis = load_economic_basis()
    economic_assumptions = assumptions_from_basis(economic_basis)
    feature004_carbon_prices = carbon_prices_from_basis(economic_basis)
    pre_tax_case = next(item for item in fiscal_cases_from_basis(economic_basis) if item.mode == "pre_tax")

    start = time.perf_counter()
    route_sources, route_demands = adapt_legacy_pipeline_inputs(
        source=source,
        candidates=candidates,
        well_values=[],
        assumptions=assumptions,
    )
    route_library = build_route_library(
        RouteLibraryRequest(
            sources=route_sources,
            well_demands=route_demands,
            routing_assumptions=assumptions["routing"],
        )
    )

    by_price: dict[str, dict[str, Any]] = {}
    rankings: dict[str, list[str]] = {}
    break_evens: dict[str, float] = {}
    phase1_adapter_cache: dict[tuple[Any, ...], Any] = {}
    for label, price in carbon_prices.items():
        all_values = [
            _evaluate_candidate(candidate, params, economics, float(price))
            for candidate in candidates
            for params in grid
        ]
        best = _best_by_candidate(all_values)
        pipeline_sources, pipeline_demands = adapt_legacy_pipeline_inputs(
            source=source,
            candidates=candidates,
            well_values=list(best.values()),
            assumptions=assumptions,
        )
        request = PipelineDesignRequest(
            objective_mode=str(assumptions["pipeline"].get("objective_mode", "max_net_value")),
            sources=pipeline_sources,
            well_demands=pipeline_demands,
            route_library=route_library,
            annual_co2_budget_tonnes=float(assumptions["co2_source"]["capacity_tonnes_per_year"]),
            assumptions=assumptions,
            cost_case=str(assumptions["pipeline"].get("cost_case", "base")),
            solver=str(assumptions["pipeline"].get("solver", "cbc")),
        )
        pipeline = solve_pipeline_design(request)
        phase1_minimum_selection_adapter = False
        if (
            pipeline.domain_status == "no_viable_network"
            and int(assumptions["pipeline"].get("minimum_selected_wells", 0)) > 0
        ):
            # Temporary compatibility behavior for the Phase 1 abstract proxy.
            # Feature 002 itself retains rational zero-selection semantics; Feature
            # 005 will replace this forced proxy with real surrogate demand/value.
            legacy_priority = min(
                pipeline_demands,
                key=lambda item: (
                    (item.location.latitude - source.location.latitude) ** 2
                    + (item.location.longitude - source.location.longitude) ** 2,
                    item.candidate_id,
                ),
            ).candidate_id
            adapter_demands = [
                item.model_copy(update={"mandatory": item.candidate_id == legacy_priority})
                for item in pipeline_demands
            ]
            mandatory_demand = next(item for item in adapter_demands if item.mandatory)
            adapter_key = (
                legacy_priority,
                mandatory_demand.annual_demand_tonnes,
                mandatory_demand.peak_mass_flow_kg_s,
                request.cost_case,
                route_library.fingerprint,
            )
            pipeline = phase1_adapter_cache.get(adapter_key)
            if pipeline is None:
                pipeline = solve_pipeline_design(
                    request.model_copy(
                        update={
                            "objective_mode": "min_lifecycle_cost",
                            "well_demands": adapter_demands,
                        }
                    )
                )
                if pipeline.domain_status == "accepted":
                    phase1_adapter_cache[adapter_key] = pipeline
            if pipeline.domain_status != "accepted":
                raise RuntimeError(
                    "Phase 1 minimum-selection compatibility solve failed: "
                    f"{pipeline.domain_status} ({pipeline.termination_condition}; {pipeline.constraint_audit})."
                )
            phase1_minimum_selection_adapter = True
        best_for_selected = {candidate_id: best[candidate_id] for candidate_id in pipeline.selected_wells}

        economic_results = {}
        facility_portfolio = (
            _evaluate_selected_facility_portfolio(
                best_for_selected=best_for_selected,
                node_pressures_bar=pipeline.node_pressures_bar,
                assumptions=assumptions,
                cost_case=request.cost_case,
                portfolio_id=f"phase1-{label}",
            )
            if best_for_selected
            else None
        )
        facilities_by_id = (
            {item.candidate_id: item for item in facility_portfolio.well_results}
            if facility_portfolio is not None
            else {}
        )
        economic_portfolios: list[PortfolioEconomicInput] = []
        total_injected = sum(value.injected_co2_tonnes for value in best_for_selected.values())
        for candidate_id, value in best_for_selected.items():
            facility = facilities_by_id[candidate_id]
            periods = annualize_screened_value(
                value,
                project_life_years=int(economics["project_life_years"]),
                surface_loss_fraction=facility.loss_ledger.net_storage_debit_fraction,
            )
            allocation_fraction = value.injected_co2_tonnes / total_injected if total_injected else 0.0
            economic_portfolios.append(
                PortfolioEconomicInput(
                    portfolio_id=candidate_id,
                    evaluation_stage="preliminary",
                    project_life_years=int(economics["project_life_years"]),
                    periods=periods,
                    supply=pipeline_raw_supply(
                        pipeline,
                        periods,
                        int(economics["project_life_years"]),
                        allocation_fraction=allocation_fraction,
                    ),
                    facility=facility_for_well(
                        facility,
                        periods,
                        int(economics["project_life_years"]),
                    ),
                    uncertainty=uncertainty_from_percentages(periods, uncertainty, candidate_id),
                    provenance=[
                        EconomicProvenance(
                            source_class="engineering_correlation",
                            source_id=f"phase1-analytic-proxy-{candidate_id}",
                            notes="Development-only compatibility profile; not final Feature 001 coupling.",
                        )
                    ],
                )
            )

        aggregate = (
            combine_portfolios(economic_portfolios, portfolio_id=f"phase1-{label}-aggregate")
            if economic_portfolios
            else None
        )
        batch = (
            evaluate_economic_batch(
                EconomicBatchRequest(
                    portfolios=[*economic_portfolios, aggregate],
                    carbon_prices=feature004_carbon_prices,
                    fiscal_cases=[pre_tax_case],
                    assumptions=economic_assumptions,
                    provenance=basis_provenance(economic_basis),
                )
            )
            if aggregate is not None
            else None
        )
        scenario_id = "article6_jcm" if label == "jcm_bilateral" else label
        if batch is not None:
            for result in batch.results:
                if (
                    result.carbon_price_scenario_id == scenario_id
                    and result.portfolio_id in best_for_selected
                ):
                    economic_results[result.portfolio_id] = result
            aggregate_result = next(
                result
                for result in batch.results
                if result.carbon_price_scenario_id == scenario_id
                and result.portfolio_id == aggregate.portfolio_id
            )
        else:
            aggregate_result = None

        ranking = _ranking(selected_results=economic_results, best_by_candidate=best)
        rankings[label] = ranking
        selected_results = list(economic_results.values())
        break_evens[label] = (
            float(aggregate_result.break_even_carbon_price.value or 0.0)
            if aggregate_result is not None
            else 0.0
        )
        discount_rate = economic_assumptions.discount_rate
        portfolio_npv_without_carbon = (
            aggregate_result.npv_usd
            - sum(
                row.carbon_revenue_usd / ((1.0 + discount_rate) ** row.year)
                for row in aggregate_result.annual_cashflows
            )
            if aggregate_result is not None
            else 0.0
        )
        by_price[label] = {
            "carbon_price": float(price),
            "portfolio_npv_usd": aggregate_result.npv_usd if aggregate_result is not None else 0.0,
            "portfolio_npv_low_usd": aggregate_result.npv_low_usd if aggregate_result is not None else 0.0,
            "portfolio_npv_high_usd": aggregate_result.npv_high_usd if aggregate_result is not None else 0.0,
            "portfolio_npv_without_carbon_usd": portfolio_npv_without_carbon,
            "portfolio_storage_tonnes": (
                aggregate_result.storage.primary_net_stored_co2_tonnes
                if aggregate_result is not None
                else 0.0
            ),
            "selected_wells": pipeline.selected_wells,
            "ranking": ranking,
            "best_by_candidate": {key: value.model_dump() for key, value in best.items()},
            "economic_results": {key: value.model_dump() for key, value in economic_results.items()},
            "economic_portfolio_result": (
                aggregate_result.model_dump() if aggregate_result is not None else None
            ),
            "economic_basis_version": economic_assumptions.version,
            "economic_qualification": "development_proxy_only_not_final_feature005_coupling",
            "facility_results": {
                candidate_id: facility.model_dump()
                for candidate_id, facility in facilities_by_id.items()
            },
            "facility_portfolio": facility_portfolio.model_dump() if facility_portfolio is not None else None,
            "pipeline": pipeline.model_dump(),
            "milp_candidate_limit": None,
            "phase1_minimum_selection_adapter": phase1_minimum_selection_adapter,
        }

    elapsed_minutes = (time.perf_counter() - start) / 60.0
    current_rank = rankings["current_idx"]
    jcm_rank = rankings["jcm_bilateral"]
    rank_delta_threshold = int(economics["priority_change_rank_delta"])

    return {
        "scenario_count": scenario_count,
        "screening_runtime_minutes": elapsed_minutes,
        "equivalent_mrst_weeks": scenario_count * mrst_mean_seconds / (60.0 * 60.0 * 24.0 * 7.0),
        "route_provenance": route_library.provenance,
        "by_price": by_price,
        "changed_priority_count": _priority_shift(current_rank, jcm_rank, rank_delta_threshold),
        "candidate_count": len(candidates),
        "break_even_carbon_price_usd_per_tonne": break_evens["current_idx"],
        "method": "A* SRTM routing + CoolProp hydraulics/facility + Pyomo/CBC MILP + Feature 004 annual NumPy DCF (development proxy adapter)",
    }


def main() -> None:
    from jatibarang_ccus.phase1.metrics import mrst_mean_runtime_seconds, surrogate_metric_summary

    parser = argparse.ArgumentParser(description="Run real Phase 1 integrated screening.")
    parser.add_argument("--assumptions", type=Path, default=DEFAULT_ASSUMPTIONS)
    args = parser.parse_args()
    assumptions = load_assumptions(args.assumptions)
    metrics = surrogate_metric_summary()
    result = run_screening(
        assumptions,
        mrst_mean_seconds=mrst_mean_runtime_seconds(),
        surrogate_uncertainty={
            "production_error_pct": float(metrics["cumulative_production_error_pct"]),
            "co2_mass_error_pct": float(metrics["end_sequence_co2_mass_error_pct"]),
        },
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
