from __future__ import annotations

from jatibarang_ccus.contracts import (
    Coordinate,
    NetworkCostBreakdown,
    PipelineDesignResult,
    RouteLibrary,
    RouteNode,
    RouteSegment,
    WellSelectionDecision,
)
from jatibarang_ccus.infrastructure.economics import evaluate_economic_batch
from jatibarang_ccus.infrastructure.facility import evaluate_facility_portfolio
from jatibarang_ccus.infrastructure.supply import evaluate_trucking_supply
from jatibarang_ccus.screening.orchestrator import ScreeningOrchestrator, ScreeningServices
from jatibarang_ccus.screening.schemas import (
    InlineScreenRequest,
    ProducedCO2Assumption,
    ScreeningCandidate,
)
from jatibarang_ccus.surrogate.preprocessing import schedule_fingerprint

from .helpers import FakeRunner, economic_dimensions, geology, schedule, seed, source


def inline_request(active_schedules=None) -> InlineScreenRequest:
    active_schedules = active_schedules or [schedule()]
    carbon_prices, fiscal_cases, assumptions = economic_dimensions()
    provenance = fiscal_cases[0].provenance[0]
    return InlineScreenRequest(
        mode="inline",
        geologies={"G": geology()},
        seeds={f"S{index}": seed(item) for index, item in enumerate(active_schedules)},
        candidates=[
            ScreeningCandidate(
                candidate_id=candidate_id,
                location=Coordinate(latitude=-6.48, longitude=108.31 + offset * 0.01),
                geology_id="G",
                seed_by_schedule_fingerprint={
                    schedule_fingerprint(item): f"S{schedule_index}"
                    for schedule_index, item in enumerate(active_schedules)
                },
                produced_co2=ProducedCO2Assumption(mole_fraction=0.65, provenance=provenance),
            )
            for offset, candidate_id in enumerate(["W01", "W02"])
        ],
        sources=[source()],
        schedules=active_schedules,
        annual_co2_budget_tonnes=320_000.0,
        carbon_prices=carbon_prices,
        fiscal_cases=fiscal_cases,
        economic_assumptions=assumptions,
        detailed_top_k=1,
    )


def route_library(route_request) -> RouteLibrary:
    nodes = [
        RouteNode(id=item.id, kind="source", location=item.location, elevation_m=10.0)
        for item in route_request.sources
    ] + [
        RouteNode(id=item.candidate_id, kind="well", location=item.location, elevation_m=10.0)
        for item in route_request.well_demands
    ]
    source_id = route_request.sources[0].id
    source_location = route_request.sources[0].location
    segments = [
        RouteSegment(
            id=f"{source_id}--{demand.candidate_id}",
            from_node=source_id,
            to_node=demand.candidate_id,
            geometry=[source_location, demand.location],
            elevation_m=[10.0, 10.0],
            length_km=50.0,
            min_slope=0.0,
            max_slope=0.0,
            route_cost=1.0,
            terrain_sha256="A" * 64,
        )
        for demand in route_request.well_demands
    ]
    return RouteLibrary(
        nodes=nodes,
        segments=segments,
        fingerprint="B" * 64,
        provenance={"terrain_sha256": "A" * 64},
    )


def pipeline_result(design_request, selected: list[str], domain_status: str = "accepted") -> PipelineDesignResult:
    costs = NetworkCostBreakdown(
        cost_case=design_request.cost_case,
        cost_year=2025,
        pipeline_capex_usd=100_000.0,
        booster_capex_usd=0.0,
        annual_maintenance_usd=3_000.0,
        annual_booster_energy_usd=0.0,
        annual_opex_usd=3_000.0,
        commodity_supply_usd_per_tonne=8.0,
        present_value_lifecycle_cost_usd=200_000.0,
        levelized_transport_usd_per_tonne=2.0,
        levelized_delivered_usd_per_tonne=10.0,
        provenance={"fixture": True},
    )
    return PipelineDesignResult(
        domain_status=domain_status,
        solver="fixture",
        solver_status="optimal",
        termination_condition="optimal",
        objective_mode="max_net_value",
        objective_value_usd=1_000_000.0,
        objective_bound_usd=1_000_000.0,
        optimality_gap=0.0,
        selected_wells=selected,
        well_decisions=[
            WellSelectionDecision(
                candidate_id=item.candidate_id,
                selected=item.candidate_id in selected,
                reason="selected" if item.candidate_id in selected else "network_cost",
            )
            for item in design_request.well_demands
        ],
        built_segments=[],
        boosters=[],
        node_pressures_bar={"W01": 100.0},
        source_annual_flows_tonnes={design_request.sources[0].id: 20_000.0},
        source_peak_flows_kg_s={design_request.sources[0].id: 1.0},
        delivered_cost_usd_per_tonne={"W01": 10.0},
        per_well_allocated_cost_usd={"W01": 200_000.0},
        costs=costs,
        constraint_audit={},
        hydraulic_verification={},
        solve_time_seconds=0.01,
        route_provenance={"fingerprint": "B" * 64},
        pipeline_capex_usd=100_000.0,
        booster_capex_usd=0.0,
        annual_opex_usd=3_000.0,
        total_network_cost_usd=200_000.0,
    )


def accepted_pipeline(design_request) -> PipelineDesignResult:
    return pipeline_result(design_request, ["W01"])


def test_shared_pipeline_deduplicates_and_calls_facilities_only_for_selected_wells() -> None:
    calls: list[tuple[str, object]] = []

    class RecordingRunner(FakeRunner):
        def predict_compiled_batch(self, compiled, *, microbatch_size=16):
            calls.append(("module2", len(compiled)))
            return super().predict_compiled_batch(compiled, microbatch_size=microbatch_size)

    runner = RecordingRunner()

    def route(request):
        calls.append(("module1-route", len(request.well_demands)))
        return route_library(request)

    def pipeline(request):
        calls.append(("module1", tuple(item.candidate_id for item in request.well_demands)))
        return accepted_pipeline(request)

    def facility(request):
        calls.append(("module3", tuple(item.candidate_id for item in request.wells)))
        return evaluate_facility_portfolio(request)

    def economics(request):
        stages = tuple(item.evaluation_stage for item in request.portfolios)
        calls.append(("module4", stages))
        return evaluate_economic_batch(request)

    orchestrator = ScreeningOrchestrator(
        runner,
        services=ScreeningServices(
            route_builder=route,
            pipeline_solver=pipeline,
            facility_evaluator=facility,
            economic_evaluator=economics,
            trucking_evaluator=evaluate_trucking_supply,
            solver_checker=lambda _solver: None,
        ),
    )
    result = orchestrator.run(inline_request())

    assert result.logical_scenario_count == 2
    assert result.unique_inference_count == 1
    assert result.inference_cache_hits == 1
    assert runner.compiled_count == 1
    assert all(plan.selected_wells == ["W01"] for plan in result.plans)
    assert all(tuple(item.candidate_id for item in plan.facility.well_results) == ("W01",) for plan in result.plans)
    first_surrogate = next(index for index, item in enumerate(calls) if item[0] == "module2")
    first_select = next(index for index, item in enumerate(calls) if item[0] == "module1")
    first_facility = next(index for index, item in enumerate(calls) if item[0] == "module3")
    first_final_economics = next(
        index for index, item in enumerate(calls) if item[0] == "module4" and "final" in item[1]
    )
    assert first_surrogate < first_select < first_facility < first_final_economics
    assert sum(item[0] == "module1" for item in calls) == 8
    assert result.plans[0].trucking_counterfactual is not None
    assert result.plans[0].discrepancy_audit.method == "single_non_convergent_selected_set_counterfactual"
    assert result.plans[0].economics.accounting_verdict == "PASS"


def test_sync_and_event_pipeline_return_the_same_result() -> None:
    services = ScreeningServices(
        route_builder=route_library,
        pipeline_solver=accepted_pipeline,
        facility_evaluator=evaluate_facility_portfolio,
        economic_evaluator=evaluate_economic_batch,
        trucking_evaluator=evaluate_trucking_supply,
        solver_checker=lambda _solver: None,
    )
    orchestrator = ScreeningOrchestrator(FakeRunner(), services=services)
    request = inline_request()
    sync = orchestrator.run(request)
    stream_events = list(orchestrator.stream(request.model_copy(update={"run_id": "stream-run"})))
    streamed = next(item.payload["result"] for item in stream_events if item.event == "result")

    assert [item.event for item in stream_events][0] == "run_started"
    assert [item.event for item in stream_events][-1] == "result"
    sync_payload = sync.model_dump(mode="json")
    assert [item["selected_wells"] for item in streamed["plans"]] == [
        item["selected_wells"] for item in sync_payload["plans"]
    ]
    assert [item["domain_status"] for item in streamed["plans"]] == [
        item["domain_status"] for item in sync_payload["plans"]
    ]
    assert streamed["cross_price_comparison"] == sync_payload["cross_price_comparison"]
    assert streamed["shortlist"] == sync_payload["shortlist"]
    assert streamed["logical_scenario_count"] == sync.logical_scenario_count


def test_synthetic_fixture_proves_price_pivot_and_partial_failure_outcomes() -> None:
    seen: dict[str, int] = {}

    def pivot_pipeline(request):
        scenario_id = request.supply_scenario_id.split("--", 1)[1]
        count = seen.get(scenario_id, 0)
        seen[scenario_id] = count + 1
        if scenario_id == "current_idx":
            return pipeline_result(request, [], domain_status="no_viable_network")
        selected = ["W01"] if scenario_id == "domestic_maturing" else ["W02"]
        return pipeline_result(request, selected)

    orchestrator = ScreeningOrchestrator(
        FakeRunner(),
        services=ScreeningServices(
            route_builder=route_library,
            pipeline_solver=pivot_pipeline,
            facility_evaluator=evaluate_facility_portfolio,
            economic_evaluator=evaluate_economic_batch,
            trucking_evaluator=evaluate_trucking_supply,
            solver_checker=lambda _solver: None,
        ),
    )
    result = orchestrator.run(inline_request())

    assert result.status == "completed_with_failures"
    assert result.plans[0].domain_status == "no_viable_network"
    assert result.plans[0].selected_wells == []
    assert result.plans[0].facility is None
    assert result.cross_price_comparison.pivot_observed is True
    assert result.cross_price_comparison.transitions[0].entrants == ["W01"]
    assert result.cross_price_comparison.transitions[1].entrants == ["W02"]
    assert result.cross_price_comparison.transitions[1].exits == ["W01"]


def test_candidate_schedule_choice_is_independent_for_each_carbon_price() -> None:
    request = inline_request([schedule(cycles=3), schedule(cycles=4)])
    cycle_by_portfolio = {
        f"W01--{schedule_fingerprint(item)[:12]}": item.cycles for item in request.schedules
    }

    def pivot_economics(batch_request):
        result = evaluate_economic_batch(batch_request)
        if not all(item.evaluation_stage == "preliminary" for item in batch_request.portfolios):
            return result
        adjusted = []
        for item in result.results:
            cycles = cycle_by_portfolio.get(item.portfolio_id, 3)
            preferred = 3 if item.carbon_price_scenario_id == "current_idx" else 4
            score = 1_000_000_000.0 if cycles == preferred else 0.0
            adjusted.append(
                item.model_copy(update={"npv_usd": score, "pre_tax_npv_usd": score})
            )
        return result.model_copy(update={"results": adjusted})

    orchestrator = ScreeningOrchestrator(
        FakeRunner(),
        services=ScreeningServices(
            route_builder=route_library,
            pipeline_solver=accepted_pipeline,
            facility_evaluator=evaluate_facility_portfolio,
            economic_evaluator=pivot_economics,
            trucking_evaluator=evaluate_trucking_supply,
            solver_checker=lambda _solver: None,
        ),
    )
    result = orchestrator.run(request)
    chosen_cycles = [
        next(item for item in plan.well_strategies if item.candidate_id == "W01").schedule.cycles
        for plan in result.plans
    ]
    assert chosen_cycles == [3, 4, 4, 4]


def test_orchestrator_cancellation_is_cooperative_and_terminal() -> None:
    orchestrator = ScreeningOrchestrator(
        FakeRunner(),
        services=ScreeningServices(
            route_builder=route_library,
            pipeline_solver=accepted_pipeline,
            facility_evaluator=evaluate_facility_portfolio,
            economic_evaluator=evaluate_economic_batch,
            trucking_evaluator=evaluate_trucking_supply,
            solver_checker=lambda _solver: None,
        ),
    )
    events = orchestrator.stream(inline_request().model_copy(update={"run_id": "cancel-me"}))
    assert next(events).event == "run_started"
    assert orchestrator.cancel("cancel-me") is True
    remaining = list(events)
    assert remaining[-1].event == "cancelled"
    assert orchestrator.cancel("cancel-me") is False
