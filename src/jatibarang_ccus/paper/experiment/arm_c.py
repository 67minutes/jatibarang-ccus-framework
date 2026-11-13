from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import statistics
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from jatibarang_ccus.contracts import (
    Coordinate,
    PipelineDesignRequest,
    PipelineWellDemand,
    RouteLibraryRequest,
)
from jatibarang_ccus.infrastructure.crossover import crossover_table
from jatibarang_ccus.paper.field_scenarios import (
    CachedOrchestratorFieldScenarioResolver,
    FieldScenarioExperimentResult,
    FieldScenarioResolveContext,
    FieldScenarioSolveRecord,
    build_field_scenario_design,
    run_field_scenario_resolves,
)
from jatibarang_ccus.screening.orchestrator import (
    ScreeningOrchestrator,
    build_default_orchestrator,
    routing_assumptions_for_terrain,
)
from jatibarang_ccus.screening.prediction_cache import PredictionCache
from jatibarang_ccus.screening.presets import CompactPresetBank
from jatibarang_ccus.screening.schemas import PresetScreenRequest, ScreenResult
from jatibarang_ccus.surrogate.config import REPO_ROOT
from jatibarang_ccus.surrogate.runner import load_surrogate

from .schemas import (
    CarbonPriceRankingRow,
    CarbonPriceRegretRow,
    NpvVsCarbonPriceRow,
    PipelineCostCrossoverRow,
    PipelinePressureRow,
    PipelineRouteRow,
    ScreeningSurfaceRow,
    atomic_write_csv,
    atomic_write_json,
    canonical_sha256,
    sha256_file,
)


FULL_PRESET_ID = "jatibarang_full_v1"
FIELD_SCENARIO_SEED = 20260717
ARTICLE6_PRICE_ID = "article6_jcm"
DEFAULT_WORKSPACE = REPO_ROOT / "output" / "feature007-experiment"


def _quantile(values: Sequence[float], probability: float) -> float:
    return float(np.quantile(np.asarray(values, dtype=float), probability))


def _retention_fraction(prediction: Any) -> float:
    injected = [
        float(value)
        for value in prediction.inventory.injected_co2_tonnes
        if value is not None
    ]
    produced_back = [
        float(value)
        for value in prediction.inventory.produced_back_co2_tonnes
        if value is not None
    ]
    if not injected or not produced_back or injected[-1] <= 0:
        raise ValueError(
            f"scenario {prediction.scenario_id} lacks usable CO2 inventory"
        )
    retained = injected[-1] - produced_back[-1]
    return max(0.0, min(1.0, retained / injected[-1]))


def aggregate_screening_surface(
    scenarios: Iterable[Any],
    prediction_cache: Mapping[str, Any],
) -> list[ScreeningSurfaceRow]:
    grouped: dict[tuple[str, float, int], dict[str, Any]] = {}
    for scenario in scenarios:
        key = (
            scenario.candidate_id,
            float(scenario.schedule.injection_rate_m3_day),
            int(scenario.schedule.cycles),
        )
        bucket = grouped.setdefault(
            key,
            {
                "permeability": float(
                    np.mean(
                        scenario.predict_request.geology.permeability_md.as_array(
                            dtype=np.float64
                        )
                    )
                ),
                "oil": [],
                "retention": [],
            },
        )
        prediction = prediction_cache[scenario.input_fingerprint]
        bucket["oil"].append(
            float(sum(prediction.production.delta_oil_m3))
        )
        bucket["retention"].append(_retention_fraction(prediction))

    rows: list[ScreeningSurfaceRow] = []
    for (geology_id, rate, cycles), values in sorted(grouped.items()):
        oil = values["oil"]
        retention = values["retention"]
        rows.append(
            ScreeningSurfaceRow(
                geology_id=geology_id,
                mean_permeability_md=values["permeability"],
                injection_rate_m3_day=rate,
                incremental_oil_m3=statistics.fmean(oil),
                co2_retention_fraction=statistics.fmean(retention),
                cycles=cycles,
                sample_count=len(oil),
                incremental_oil_p10_m3=_quantile(oil, 0.10),
                incremental_oil_p90_m3=_quantile(oil, 0.90),
                co2_retention_p10_fraction=_quantile(retention, 0.10),
                co2_retention_p90_fraction=_quantile(retention, 0.90),
                source_class="surrogate_prediction",
            )
        )
    return rows


def field_scenario_tables(
    result: FieldScenarioExperimentResult,
    price_by_id: Mapping[str, float],
) -> tuple[
    list[CarbonPriceRankingRow],
    list[NpvVsCarbonPriceRow],
    list[CarbonPriceRegretRow],
]:
    independent_npv: dict[tuple[str, str], list[float]] = defaultdict(list)
    correlated_npv: dict[tuple[str, str], list[float]] = defaultdict(list)
    independent_regret: dict[tuple[str, str], list[float]] = defaultdict(list)
    correlated_regret: dict[tuple[str, str], list[float]] = defaultdict(list)
    independent_cells: dict[tuple[str, str, str], float] = {}

    def collect(records: Sequence[Any], *, correlated: bool) -> None:
        npv_target = correlated_npv if correlated else independent_npv
        regret_target = (
            correlated_regret if correlated else independent_regret
        )
        for record in records:
            chosen = record.carbon_price_scenario_id
            for realized, value in record.result.get(
                "npv_by_carbon_price_usd",
                {},
            ).items():
                npv_target[(chosen, realized)].append(float(value))
                if not correlated:
                    independent_cells[
                        (record.assignment_id, chosen, realized)
                    ] = float(value)
            for realized, value in record.result.get(
                "regret_by_realized_price_usd",
                {},
            ).items():
                regret_target[(chosen, realized)].append(float(value))

    collect(result.independent, correlated=False)
    collect(result.correlated, correlated=True)
    if not independent_npv:
        raise ValueError("field-scenario result contains no independent NPV values")

    curves: list[NpvVsCarbonPriceRow] = []
    for (chosen, realized), values in sorted(independent_npv.items()):
        correlated_values = correlated_npv.get((chosen, realized), [])
        curves.append(
            NpvVsCarbonPriceRow(
                scenario_id=f"chosen:{chosen}",
                carbon_price_usd_per_tonne=price_by_id[realized],
                npv_usd=statistics.fmean(values),
                npv_low_usd=_quantile(values, 0.10),
                npv_high_usd=_quantile(values, 0.90),
                correlated_npv_usd=(
                    statistics.median(correlated_values)
                    if correlated_values
                    else None
                ),
                source_class="arm_c_integrated_result",
                chosen_price_scenario_id=chosen,
                realized_price_scenario_id=realized,
            )
        )

    rankings: list[CarbonPriceRankingRow] = []
    realized_ids = sorted(
        {realized for _chosen, realized in independent_npv},
        key=lambda item: price_by_id[item],
    )
    for realized in realized_ids:
        ranked = sorted(
            (
                (chosen, statistics.fmean(values))
                for (chosen, active_realized), values in independent_npv.items()
                if active_realized == realized
            ),
            key=lambda item: (-item[1], item[0]),
        )
        correlated_ranked = sorted(
            (
                (chosen, statistics.median(values))
                for (chosen, active_realized), values in correlated_npv.items()
                if active_realized == realized
            ),
            key=lambda item: (-item[1], item[0]),
        )
        correlated_rank_by_policy = {
            chosen: rank
            for rank, (chosen, _value) in enumerate(
                correlated_ranked,
                start=1,
            )
        }
        rank_samples: dict[str, list[float]] = defaultdict(list)
        assignment_ids = sorted(
            {
                assignment
                for assignment, _chosen, active_realized
                in independent_cells
                if active_realized == realized
            }
        )
        for assignment_id in assignment_ids:
            assignment_ranked = sorted(
                (
                    (chosen, value)
                    for (
                        active_assignment,
                        chosen,
                        active_realized,
                    ), value in independent_cells.items()
                    if active_assignment == assignment_id
                    and active_realized == realized
                ),
                key=lambda item: (-item[1], item[0]),
            )
            for assignment_rank, (chosen, _value) in enumerate(
                assignment_ranked,
                start=1,
            ):
                rank_samples[chosen].append(float(assignment_rank))
        for rank, (chosen, mean_npv) in enumerate(ranked, start=1):
            independent_values = independent_npv[(chosen, realized)]
            correlated_values = correlated_npv[(chosen, realized)]
            rankings.append(
                CarbonPriceRankingRow(
                    scenario_id=f"chosen:{chosen}",
                    carbon_price_usd_per_tonne=price_by_id[realized],
                    rank=rank,
                    independent_rank_p10=_quantile(
                        rank_samples[chosen],
                        0.10,
                    ),
                    independent_rank_p90=_quantile(
                        rank_samples[chosen],
                        0.90,
                    ),
                    independent_npv_mean_usd=mean_npv,
                    independent_npv_p10_usd=_quantile(
                        independent_values,
                        0.10,
                    ),
                    independent_npv_p90_usd=_quantile(
                        independent_values,
                        0.90,
                    ),
                    independent_assignment_count=len(
                        independent_values
                    ),
                    correlated_rank=correlated_rank_by_policy[chosen],
                    correlated_npv_median_usd=statistics.median(
                        correlated_values
                    ),
                    source_class="arm_c_integrated_result",
                    chosen_price_scenario_id=chosen,
                    realized_price_scenario_id=realized,
                )
            )

    regret_rows: list[CarbonPriceRegretRow] = []
    for (chosen, realized), values in sorted(independent_regret.items()):
        correlated_values = correlated_regret.get((chosen, realized), [])
        regret_rows.append(
            CarbonPriceRegretRow(
                chosen_price_scenario=chosen,
                realized_price_scenario=realized,
                regret_usd=statistics.fmean(values),
                regret_p10_usd=_quantile(values, 0.10),
                regret_p90_usd=_quantile(values, 0.90),
                correlated_regret_usd=(
                    statistics.median(correlated_values)
                    if correlated_values
                    else None
                ),
                source_class="arm_c_integrated_result",
                independent_assignment_count=len(values),
            )
        )
    return rankings, curves, regret_rows


def _representative_assignment_id(
    result: FieldScenarioExperimentResult,
    price_id: str,
) -> str:
    candidates = sorted(
        (
            float(record.result["portfolio_npv_usd"]),
            record.assignment_id,
        )
        for record in result.independent
        if record.carbon_price_scenario_id == price_id
        and record.result.get("portfolio_npv_usd") is not None
    )
    if not candidates:
        raise ValueError(
            f"no independent assignment has an NPV for {price_id}"
        )
    median_npv = statistics.median(value for value, _assignment in candidates)
    return min(
        candidates,
        key=lambda item: (abs(item[0] - median_npv), item[1]),
    )[1]


def pipeline_route_rows(
    result: ScreenResult,
    price_id: str,
    bank: CompactPresetBank,
) -> list[PipelineRouteRow]:
    plan = next(
        item
        for item in result.plans
        if item.carbon_price_scenario_id == price_id
    )
    if plan.domain_status != "accepted" or not plan.selected_wells:
        reason = str(
            plan.pipeline.hydraulic_verification.get("reason")
            or plan.pipeline.constraint_audit.get("reason")
            or plan.domain_status
        )
        raise ValueError(
            f"representative Article 6/JCM network is not viable: {reason}"
        )
    rows: list[PipelineRouteRow] = []
    source_ids = {source.id for source in bank.metadata.sources}
    well_ids = {
        candidate.candidate_id for candidate in bank.metadata.candidates
    }

    def node_type(node_id: str) -> str:
        if node_id in source_ids:
            return "source"
        if node_id in well_ids:
            return "well"
        if "booster" in node_id.lower():
            return "booster"
        return "junction"

    for route in plan.pipeline.route_provenance.get(
        "selected_route_geometries",
        [],
    ):
        geometry = route["geometry"]
        for point_order, point in enumerate(geometry):
            rows.append(
                PipelineRouteRow(
                    route_id=route["segment_id"],
                    point_order=point_order,
                    longitude=float(point["longitude"]),
                    latitude=float(point["latitude"]),
                    node_type=(
                        node_type(str(route["from_node"]))
                        if point_order == 0
                        else node_type(str(route["to_node"]))
                        if point_order == len(geometry) - 1
                        else "junction"
                    ),
                    mode="pipeline",
                    selected=True,
                    route_method=str(route.get("route_method", "")),
                    source_class="arm_c_integrated_result",
                )
            )
    if plan.trucking_route_preview is not None:
        for leg in plan.trucking_route_preview.legs:
            if not leg.route:
                continue
            for point_order, (latitude, longitude) in enumerate(leg.route):
                rows.append(
                    PipelineRouteRow(
                        route_id=f"trucking--{leg.candidate_id}",
                        point_order=point_order,
                        longitude=longitude,
                        latitude=latitude,
                        node_type=(
                            "source"
                            if point_order == 0
                            else "well"
                            if point_order == len(leg.route) - 1
                            else "junction"
                        ),
                        mode="trucking",
                        selected=True,
                        source_class="arm_c_integrated_result",
                    )
                )
    locations = {
        candidate.candidate_id: candidate.location
        for candidate in bank.metadata.candidates
    }
    for decision in plan.pipeline.well_decisions:
        if decision.selected:
            continue
        location = locations[decision.candidate_id]
        rows.append(
            PipelineRouteRow(
                route_id=f"decision--{decision.candidate_id}",
                point_order=0,
                longitude=location.longitude,
                latitude=location.latitude,
                node_type="well",
                mode="",
                selected=False,
                reason=decision.reason,
                route_method="optimizer_decision_audit",
                source_class="arm_c_integrated_result",
            )
        )
    if not rows:
        raise ValueError("accepted network produced no auditable route geometry")
    return rows


def run_commercial_trunk(
    orchestrator: ScreeningOrchestrator,
    bank: CompactPresetBank,
) -> Any:
    latitude = statistics.fmean(
        candidate.location.latitude for candidate in bank.metadata.candidates
    )
    longitude = statistics.fmean(
        candidate.location.longitude for candidate in bank.metadata.candidates
    )
    annual_tonnes = 500_000.0
    peak_mass_flow = annual_tonnes * 1000.0 / (365.0 * 86_400.0)
    demand = PipelineWellDemand(
        candidate_id="COMMERCIAL-HUB",
        location=Coordinate(latitude=latitude, longitude=longitude),
        annual_demand_tonnes=annual_tonnes,
        peak_mass_flow_kg_s=peak_mass_flow,
        pre_logistics_value_usd=0.0,
        influence_radius_m=500.0,
        mandatory=True,
        provenance={
            "source_class": "screening_cost_proxy",
            "basis": "source_capacity_reference_trunk",
        },
    )
    routing = routing_assumptions_for_terrain(
        bank.metadata.terrain_id,
        orchestrator.assumptions["routing"],
    )
    route_library = orchestrator.services.route_builder(
        RouteLibraryRequest(
            sources=bank.metadata.sources,
            well_demands=[demand],
            routing_assumptions=routing,
        )
    )
    pipeline = orchestrator.services.pipeline_solver(
        PipelineDesignRequest(
            objective_mode="min_lifecycle_cost",
            supply_scenario_id="commercial_reference_trunk",
            sources=bank.metadata.sources,
            well_demands=[demand],
            route_library=route_library,
            annual_co2_budget_tonnes=annual_tonnes,
            assumptions=orchestrator.assumptions,
            cost_case="base",
            delivery_target_tonnes_per_year=annual_tonnes,
            solver=str(orchestrator.assumptions["pipeline"].get("solver", "cbc")),
        )
    )
    if pipeline.domain_status != "accepted" or not pipeline.built_segments:
        raise ValueError(
            "commercial reference trunk did not produce an accepted hydraulic design"
        )
    return pipeline


def pipeline_pressure_rows(
    pipeline: Any,
    *,
    dense_phase_floor_bar: float,
) -> list[PipelinePressureRow]:
    rows: list[PipelinePressureRow] = []
    cumulative = 0.0
    for segment in pipeline.built_segments:
        for point_index, point in enumerate(segment.continuous_profile):
            if rows and point_index == 0:
                continue
            rows.append(
                PipelinePressureRow(
                    route_id=segment.segment_id,
                    distance_km=cumulative + float(point.distance_km),
                    pressure_bar=float(point.pressure_bar),
                    dense_phase_floor_bar=dense_phase_floor_bar,
                    maop_bar=float(segment.maop_bar),
                    source_class="screening_cost_proxy",
                )
            )
        cumulative += float(segment.length_km)
    if not rows:
        raise ValueError("commercial trunk has no continuous pressure profile")
    return rows


def pipeline_cost_crossover_rows(
    representative: ScreenResult,
    commercial_pipeline: Any,
    price_id: str,
) -> list[PipelineCostCrossoverRow]:
    """Evaluate the locked three-mode cost sweep on the selected route basis."""

    plan = next(
        item
        for item in representative.plans
        if item.carbon_price_scenario_id == price_id
    )
    if plan.trucking_counterfactual is None or not plan.selected_wells:
        raise ValueError(
            "representative Arm C plan lacks selected trucking-distance evidence"
        )
    trunk_km = sum(
        float(segment.length_km) for segment in commercial_pipeline.built_segments
    )
    full_route_km = float(plan.trucking_counterfactual.supply.distance_km)
    per_well_annual_tonnes = (
        float(plan.trucking_counterfactual.supply.annual_mass_tonnes)
        / len(plan.selected_wells)
    )
    # Retain the existing Feature 5 hybrid last-mile screening basis.  The
    # trunk and full-route distances above come from the actual two routing
    # results; this constant is not fitted to their outcome.
    lastmile_km = 5.0
    annual_tonnes_grid = [
        10_000.0 * (10 ** (index / 8.0)) for index in range(17)
    ]
    rows: list[PipelineCostCrossoverRow] = []
    for cost_case in ("low", "base", "high"):
        for raw in crossover_table(
            annual_tonnes_grid=annual_tonnes_grid,
            trunk_km=trunk_km,
            lastmile_km=lastmile_km,
            full_route_km=full_route_km,
            per_well_annual_tonnes=per_well_annual_tonnes,
            cost_case=cost_case,
        ):
            rows.append(
                PipelineCostCrossoverRow(
                    **raw,
                    cost_case=cost_case,
                    source_class="screening_cost_proxy",
                    commercial_trunk_km=trunk_km,
                    representative_full_route_km=full_route_km,
                    hybrid_lastmile_basis_km=lastmile_km,
                )
            )
    return rows


def shortlist_payload(
    result: ScreenResult,
    bank: CompactPresetBank,
) -> list[dict[str, Any]]:
    if len(result.shortlist) != 5:
        raise ValueError(
            f"Arm C requires five unique shortlisted plans, got {len(result.shortlist)}"
        )
    output = []
    produced_fraction_by_candidate = {
        candidate.candidate_id: candidate.produced_co2.mole_fraction
        for candidate in bank.metadata.candidates
    }
    for item in result.shortlist:
        if item.designated_carbon_price_scenario_id is None:
            raise ValueError(
                f"shortlist item {item.scenario_id} lacks a designated price"
            )
        plan = next(
            value
            for value in result.plans
            if value.carbon_price_scenario_id
            == item.designated_carbon_price_scenario_id
        )
        strategy = next(
            value
            for value in plan.well_strategies
            if value.scenario_id == item.scenario_id
        )
        output.append(
            {
                "plan_id": f"top-{item.rank:02d}",
                "rank": item.rank,
                "candidate_id": item.candidate_id,
                "scenario_id": item.scenario_id,
                "designated_carbon_price_scenario_id": (
                    item.designated_carbon_price_scenario_id
                ),
                "carbon_price_usd_per_tonne": (
                    plan.carbon_price_usd_per_tonne
                ),
                "fiscal_case": "pre_tax",
                "surrogate_value": item.designated_npv_usd,
                "schedule": strategy.schedule.model_dump(mode="json"),
                "peak_mass_flow_kg_s": strategy.peak_mass_flow_kg_s,
                "delivery_pressure_bar": float(
                    plan.pipeline.node_pressures_bar.get(
                        item.candidate_id,
                        80.0,
                    )
                ),
                "produced_co2_mole_fraction": float(
                    produced_fraction_by_candidate[item.candidate_id]
                ),
                "facility": strategy.facility,
                "prediction_summary": {
                    "peak_produced_gas_std_m3_day": max(
                        (
                            float(delta) / float(step.dt_days)
                            for step, delta in zip(
                                strategy.prediction.timeline,
                                strategy.prediction.production.delta_gas_m3,
                                strict=True,
                            )
                            if step.stage == "produce" and step.dt_days > 0
                        ),
                        default=0.0,
                    ),
                },
            }
        )
    return output


def run_arm_c(
    *,
    workspace: Path = DEFAULT_WORKSPACE,
    orchestrator: ScreeningOrchestrator | None = None,
) -> dict[str, Any]:
    workspace.mkdir(parents=True, exist_ok=True)
    previous_payload: dict[str, Any] | None = None
    prior_paths = (
        workspace / "arm_c_internal.json",
        workspace / "arm_c_screening.json",
    )
    for prior_path in prior_paths:
        if not prior_path.exists():
            continue
        try:
            candidate = json.loads(prior_path.read_text(encoding="utf-8"))
            if isinstance(candidate, dict):
                previous_payload = candidate
                break
        except (OSError, ValueError):
            continue
    preset_dir = (
        REPO_ROOT / "data" / "screening_presets" / FULL_PRESET_ID
    )
    manifest = json.loads(
        (preset_dir / "manifest.json").read_text(encoding="utf-8")
    )
    runner = None
    if orchestrator is None:
        runner = load_surrogate()
        orchestrator = build_default_orchestrator(runner)
    runner_info = orchestrator.runner.info_dict()
    cache_identity = {
        "checkpoint_sha256": str(runner_info["checkpoint_sha256"]),
        "preset_id": FULL_PRESET_ID,
        "preset_payload_sha256": str(manifest["payload_sha256"]),
        "preset_design_sha256": str(manifest["design_sha256"]),
    }
    prior_matches_identity = (
        previous_payload is not None
        and previous_payload.get("actual_scenario_count") == 3240
        and all(
            str(previous_payload.get("provenance", {}).get(key, ""))
            == str(value)
            for key, value in cache_identity.items()
        )
    )
    request = PresetScreenRequest(
        mode="preset",
        preset_id=FULL_PRESET_ID,
        run_id="feature007-arm-c-full",
        selection_fiscal_case_id="pre_tax",
        shortlist_top_k=5,
        detailed_top_k=0,
        scenario_limit=4096,
    )
    cache_path = workspace / "arm_c_predictions.sqlite3"
    with PredictionCache(cache_path, identity=cache_identity) as cache:
        populated = orchestrator.run_and_populate_prediction_cache(
            request,
            cache,
        )
        if populated.screen_result.logical_scenario_count != 3240:
            raise ValueError("Arm C did not evaluate the locked 3,240 scenarios")

        bank = CompactPresetBank(preset_dir / manifest["payload_file"])
        route_rows: list[PipelineRouteRow] = []
        pressure_rows: list[PipelinePressureRow] = []
        crossover_rows: list[PipelineCostCrossoverRow] = []
        top_five: list[dict[str, Any]] = []
        shortlist_status: dict[str, Any] = {
            "ready": False,
            "reason": "Arm C shortlist was not evaluated",
        }
        figure5_status: dict[str, Any] = {
            "ready": False,
            "reason": "Figure 5 route extraction was not attempted",
        }
        try:
            surface = aggregate_screening_surface(
                bank.iter_scenarios(),
                cache,
            )
            price_by_id = {
                price.scenario_id: price.carbon_price_usd_per_tonne
                for price in bank.metadata.carbon_prices
            }
            if len(price_by_id) != 4:
                raise ValueError(
                    f"Arm C requires exactly four locked carbon prices, got "
                    f"{len(price_by_id)}"
                )
            if float(price_by_id.get(ARTICLE6_PRICE_ID, -1.0)) != 40.0:
                raise ValueError(
                    "the locked Article 6/JCM representative price must be "
                    "40 USD/t"
                )
            upstream = json.loads(
                (preset_dir / "upstream_design.json").read_text(
                    encoding="utf-8"
                )
            )
            realization_to_candidate = {
                item["source_case_id"]: item["candidate_id"]
                for item in upstream["geologies"]
            }
            design = build_field_scenario_design(
                list(realization_to_candidate.values()),
                list(realization_to_candidate),
                independent_count=20,
                seed=FIELD_SCENARIO_SEED,
            )
            design_sha256 = canonical_sha256(
                design.model_dump(mode="json")
            )
            resolver = CachedOrchestratorFieldScenarioResolver(
                orchestrator,
                request,
                realization_to_candidate,
                prediction_cache=cache,
            )
            experiment_reused = False
            experiment = None
            if (
                prior_matches_identity
                and previous_payload.get("provenance", {}).get(
                    "field_scenario_design_sha256"
                )
                == design_sha256
            ):
                try:
                    candidate_experiment = (
                        FieldScenarioExperimentResult.model_validate(
                            previous_payload["field_scenario"]
                        )
                    )
                    expected_cells = {
                        (
                            assignment.mode,
                            assignment.assignment_id,
                            price_id,
                            tuple(
                                sorted(
                                    assignment.well_to_realization.items()
                                )
                            ),
                        )
                        for assignment in [
                            *design.independent,
                            *design.correlated,
                        ]
                        for price_id in price_by_id
                    }
                    actual_cells = {
                        (
                            record.mode,
                            record.assignment_id,
                            record.carbon_price_scenario_id,
                            tuple(
                                sorted(
                                    record.well_to_realization.items()
                                )
                            ),
                        )
                        for record in [
                            *candidate_experiment.independent,
                            *candidate_experiment.correlated,
                        ]
                    }
                    if (
                        actual_cells == expected_cells
                        and candidate_experiment.downstream_resolve_count
                        == 160
                        and candidate_experiment.surrogate_evaluations_during_resolve
                        == 0
                    ):
                        experiment = candidate_experiment
                        experiment_reused = True
                except (KeyError, TypeError, ValueError):
                    experiment = None
            if experiment is None:
                checkpoint_path = (
                    workspace / "arm_c_field_scenario_checkpoint.json"
                )
                checkpoint_identity = {
                    **cache_identity,
                    "field_scenario_design_sha256": design_sha256,
                    "carbon_price_scenario_ids": sorted(price_by_id),
                }
                checkpoint_records: list[FieldScenarioSolveRecord] = []
                if checkpoint_path.exists():
                    checkpoint_payload = json.loads(
                        checkpoint_path.read_text(encoding="utf-8")
                    )
                    if (
                        checkpoint_payload.get("identity")
                        != checkpoint_identity
                    ):
                        raise ValueError(
                            "Arm C field-scenario checkpoint identity mismatch"
                        )
                    checkpoint_records = [
                        FieldScenarioSolveRecord.model_validate(record)
                        for record in checkpoint_payload.get("records", [])
                    ]

                def persist_record(
                    record: FieldScenarioSolveRecord,
                ) -> None:
                    checkpoint_records.append(record)
                    atomic_write_json(
                        checkpoint_path,
                        {
                            "identity": checkpoint_identity,
                            "completed_cell_count": len(
                                checkpoint_records
                            ),
                            "expected_cell_count": 160,
                            "records": [
                                value.model_dump(mode="json")
                                for value in checkpoint_records
                            ],
                        },
                    )

                experiment = run_field_scenario_resolves(
                    design,
                    list(price_by_id),
                    {
                        realization: {}
                        for realization in realization_to_candidate
                    },
                    resolver,
                    existing_records=checkpoint_records,
                    on_record=persist_record,
                )
            rankings, curves, regret = field_scenario_tables(
                experiment,
                price_by_id,
            )
            representative_id = None
            try:
                representative_id = _representative_assignment_id(
                    experiment,
                    ARTICLE6_PRICE_ID,
                )
                if representative_id not in resolver._results:
                    representative_assignment = next(
                        assignment
                        for assignment in design.independent
                        if assignment.assignment_id == representative_id
                    )
                    resolver(
                        FieldScenarioResolveContext(
                            assignment=representative_assignment,
                            carbon_price_scenario_id=ARTICLE6_PRICE_ID,
                            rollouts_by_well={
                                well: {}
                                for well in representative_assignment
                                .well_to_realization
                            },
                        )
                    )
                representative = resolver.result_for_assignment(
                    representative_id
                )
                route_rows = pipeline_route_rows(
                    representative,
                    ARTICLE6_PRICE_ID,
                    bank,
                )
                commercial = run_commercial_trunk(orchestrator, bank)
                pressure_rows = pipeline_pressure_rows(
                    commercial,
                    dense_phase_floor_bar=float(
                        orchestrator.assumptions["pipeline"][
                            "dense_phase_min_pressure_bar"
                        ]
                    ),
                )
                crossover_rows = pipeline_cost_crossover_rows(
                    representative,
                    commercial,
                    ARTICLE6_PRICE_ID,
                )
                figure5_status = {"ready": True, "reason": ""}
            except ValueError as exc:
                # A non-development or hydraulically blocked outcome is a valid
                # scientific result. Preserve the exact audit reason and do not
                # substitute a preview/reference route as a selected network.
                audit_reasons = sorted(
                    {
                        str(record.result.get("audit_reason", ""))
                        for record in experiment.independent
                        if record.carbon_price_scenario_id
                        == ARTICLE6_PRICE_ID
                        and record.result.get("audit_reason")
                    }
                )
                if (
                    representative_id is None
                    and not audit_reasons
                    and experiment_reused
                ):
                    probe_assignment = design.independent[0]
                    probe = resolver(
                        FieldScenarioResolveContext(
                            assignment=probe_assignment,
                            carbon_price_scenario_id=ARTICLE6_PRICE_ID,
                            rollouts_by_well={
                                well: {}
                                for well in probe_assignment
                                .well_to_realization
                            },
                        )
                    )
                    if probe.get("audit_reason"):
                        audit_reasons = [str(probe["audit_reason"])]
                figure5_status = {
                    "ready": False,
                    "reason": (
                        "representative Article 6/JCM network is not viable: "
                        + audit_reasons[0]
                        if representative_id is None and audit_reasons
                        else str(exc)
                    ),
                }
            try:
                top_five = shortlist_payload(populated.screen_result, bank)
                shortlist_status = {"ready": True, "reason": ""}
            except ValueError as exc:
                shortlist_status = {
                    "ready": False,
                    "reason": str(exc),
                }
        finally:
            bank.close()

        atomic_write_csv(
            workspace / "screening_surface.csv",
            surface,
            model=ScreeningSurfaceRow,
        )
        atomic_write_csv(
            workspace / "carbon_price_rankings.csv",
            rankings,
            model=CarbonPriceRankingRow,
        )
        atomic_write_csv(
            workspace / "npv_vs_carbon_price.csv",
            curves,
            model=NpvVsCarbonPriceRow,
        )
        atomic_write_csv(
            workspace / "carbon_price_regret.csv",
            regret,
            model=CarbonPriceRegretRow,
        )
        figure5_paths = {
            "route": workspace / "pipeline_route.csv",
            "pressure": workspace / "pipeline_pressure_profile.csv",
            "crossover": workspace / "pipeline_cost_crossover.csv",
        }
        if figure5_status["ready"]:
            atomic_write_csv(
                figure5_paths["route"],
                route_rows,
                model=PipelineRouteRow,
            )
            atomic_write_csv(
                figure5_paths["pressure"],
                pressure_rows,
                model=PipelinePressureRow,
            )
            atomic_write_csv(
                figure5_paths["crossover"],
                crossover_rows,
                model=PipelineCostCrossoverRow,
            )
        else:
            for stale in figure5_paths.values():
                stale.unlink(missing_ok=True)
        atomic_write_json(workspace / "top5_plans.json", top_five)
        artifact_names = [
            "screening_surface.csv",
            "carbon_price_rankings.csv",
            "npv_vs_carbon_price.csv",
            "carbon_price_regret.csv",
            "top5_plans.json",
        ]
        if figure5_status["ready"]:
            artifact_names.extend(
                [
                    "pipeline_route.csv",
                    "pipeline_pressure_profile.csv",
                    "pipeline_cost_crossover.csv",
                ]
            )
        if populated.cache.predicted_count > 0:
            initial_screen_seconds = float(
                populated.screen_result.timings.total_seconds
            )
            initial_predicted_count = int(populated.cache.predicted_count)
            timing_source = "current_prediction_run"
        elif prior_matches_identity:
            prior_timings = previous_payload.get("timings", {})
            prior_screen_seconds = (
                previous_payload.get("screen_result", {})
                .get("timings", {})
                .get(
                    "total_seconds",
                    populated.screen_result.timings.total_seconds,
                )
            )
            initial_screen_seconds = float(
                prior_timings.get(
                    "initial_screen_seconds",
                    prior_screen_seconds,
                )
            )
            initial_predicted_count = int(
                prior_timings.get(
                    "initial_predicted_count",
                    previous_payload.get("cache", {}).get(
                        "predicted_count",
                        0,
                    ),
                )
            )
            timing_source = "identity_matched_prior_production_run"
        else:
            initial_screen_seconds = float(
                populated.screen_result.timings.total_seconds
            )
            initial_predicted_count = 0
            timing_source = "cache_replay_no_prior_production_timing"
        assignment_seconds = {
            record.assignment_id: float(
                record.result.get("downstream_total_seconds", 0.0)
            )
            for record in [
                *experiment.independent,
                *experiment.correlated,
            ]
        }
        internal_payload = {
            "schema_version": "feature007-arm-c-v1",
            "status": "complete",
            "actual_scenario_count": 3240,
            "independent_assignment_count": len(experiment.independent) // 4,
            "correlated_assignment_count": len(experiment.correlated) // 4,
            "downstream_resolve_count": experiment.downstream_resolve_count,
            "representative_assignment_id": representative_id,
            "representative_carbon_price_scenario_id": ARTICLE6_PRICE_ID,
            "figure5": figure5_status,
            "screen_result": populated.screen_result.model_dump(mode="json"),
            "cache": populated.cache.model_dump(mode="json"),
            "timings": {
                "initial_screen_seconds": initial_screen_seconds,
                "initial_predicted_count": initial_predicted_count,
                "current_prediction_seconds": (
                    populated.cache.prediction_seconds
                ),
                "current_cache_reuse_seconds": (
                    populated.cache.reuse_seconds
                ),
                "current_screen_or_replay_seconds": (
                    populated.screen_result.timings.total_seconds
                ),
                "downstream_resolve_seconds": sum(
                    assignment_seconds.values()
                ),
                "downstream_assignment_count": len(assignment_seconds),
                "field_scenario_reused": experiment_reused,
                "initial_timing_source": timing_source,
            },
            "field_scenario": experiment.model_dump(mode="json"),
            "shortlist": top_five,
            "shortlist_status": shortlist_status,
            "artifacts": {
                name: {
                    "sha256": sha256_file(workspace / name),
                }
                for name in artifact_names
            },
            "provenance": {
                **cache_identity,
                "field_scenario_design_sha256": design_sha256,
                "named_well_single_assignment_claim": False,
                "assumptions_tuned": False,
            },
        }
        atomic_write_json(
            workspace / "arm_c_internal.json",
            internal_payload,
        )
        audit_payload = {
            key: value
            for key, value in internal_payload.items()
            if key not in {"screen_result", "field_scenario"}
        }
        audit_payload["screen_result_summary"] = {
            "logical_scenario_count": (
                populated.screen_result.logical_scenario_count
            ),
            "status": populated.screen_result.status,
            "carbon_price_plan_count": len(
                populated.screen_result.plans
            ),
            "carbon_price_scenario_ids": [
                plan.carbon_price_scenario_id
                for plan in populated.screen_result.plans
            ],
            "domain_status_by_price": {
                plan.carbon_price_scenario_id: plan.domain_status
                for plan in populated.screen_result.plans
            },
            "result_sha256": canonical_sha256(
                populated.screen_result.model_dump(mode="json")
            ),
            "timings": populated.screen_result.timings.model_dump(
                mode="json"
            ),
        }
        audit_payload["field_scenario_summary"] = {
            "independent_record_count": len(experiment.independent),
            "correlated_record_count": len(experiment.correlated),
            "downstream_resolve_count": (
                experiment.downstream_resolve_count
            ),
            "surrogate_evaluations_during_resolve": (
                experiment.surrogate_evaluations_during_resolve
            ),
            "distribution_summary": experiment.distribution_summary,
            "result_sha256": canonical_sha256(
                experiment.model_dump(mode="json")
            ),
        }
        atomic_write_json(
            workspace / "arm_c_screening.json",
            audit_payload,
        )
        return audit_payload
