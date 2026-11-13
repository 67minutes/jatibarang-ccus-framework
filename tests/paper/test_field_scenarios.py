from __future__ import annotations

from collections import Counter
from types import SimpleNamespace

import pytest

from jatibarang_ccus.paper.field_scenarios import (
    CachedOrchestratorFieldScenarioResolver,
    FieldScenarioResolveContext,
    assignment_rows,
    build_field_scenario_design,
    run_field_scenario_resolves,
)
from tests.screening.test_orchestration_integration import inline_request


WELLS = [f"W{index:02d}" for index in range(1, 21)]
REALIZATIONS = [f"case_{index:04d}" for index in range(1, 21)]


def test_locked_design_has_20_unique_bijections_and_20_correlated_sweeps() -> None:
    design = build_field_scenario_design(WELLS, REALIZATIONS)

    assert len(design.independent) == 20
    assert len(design.correlated) == 20
    signatures = {
        tuple(assignment.well_to_realization[well] for well in WELLS)
        for assignment in design.independent
    }
    assert len(signatures) == 20
    for assignment in design.independent:
        assert set(assignment.well_to_realization) == set(WELLS)
        assert set(assignment.well_to_realization.values()) == set(REALIZATIONS)
        assert assignment.shared_realization_id is None
    assert [item.shared_realization_id for item in design.correlated] == REALIZATIONS
    assert all(
        set(item.well_to_realization.values()) == {item.shared_realization_id}
        for item in design.correlated
    )

    rows = assignment_rows(design)
    assert len(rows) == 800
    assert Counter(row["mode"] for row in rows) == {
        "independent_limit": 400,
        "correlated_limit": 400,
    }


def test_resolve_grid_reuses_cache_objects_and_calls_each_cell_once() -> None:
    design = build_field_scenario_design(WELLS, REALIZATIONS)
    cache = {
        realization: {"realization": realization, "schedule_rollouts": object()}
        for realization in REALIZATIONS
    }
    calls: list[tuple[str, str]] = []

    def resolver(context):
        calls.append(
            (context.assignment.assignment_id, context.carbon_price_scenario_id)
        )
        for well, realization in context.assignment.well_to_realization.items():
            assert context.rollouts_by_well[well] is cache[realization]
        return {"portfolio_id": "resolved", "regret_usd": 0.0}

    result = run_field_scenario_resolves(
        design,
        ["p04", "p20", "p40", "p50"],
        cache,
        resolver,
    )

    assert result.surrogate_evaluations_during_resolve == 0
    assert result.rollout_cache_entries == 20
    assert result.downstream_resolve_count == 160
    assert len(calls) == len(set(calls)) == 160
    assert len(result.independent) == 80
    assert len(result.correlated) == 80
    regret = result.distribution_summary["independent_limit"][
        "by_carbon_price"
    ]["p04"]["regret_usd"]
    assert regret["count"] == 20
    assert regret["median"] == 0.0
    assert result.provenance["named_well_single_assignment_claim"] is False
    assert result.provenance["regret_policy"].startswith("summarize_resolver_supplied")


def test_design_and_runner_refuse_incomplete_dimensions() -> None:
    with pytest.raises(ValueError, match="equal well and realization"):
        build_field_scenario_design(WELLS, REALIZATIONS[:-1])

    design = build_field_scenario_design(WELLS, REALIZATIONS)
    with pytest.raises(ValueError, match="missing realizations"):
        run_field_scenario_resolves(
            design,
            ["p04"],
            {key: {} for key in REALIZATIONS[:-1]},
            lambda _context: {},
        )


def test_cached_orchestrator_adapter_runs_once_per_assignment() -> None:
    design = build_field_scenario_design(
        ["W01", "W02"],
        ["case_a", "case_b"],
        independent_count=2,
    )
    request = inline_request().model_copy(update={"detailed_top_k": 0})

    class DummyOrchestrator:
        def __init__(self) -> None:
            self.calls = []

        def run_with_prediction_cache(self, assigned, cache):
            self.calls.append((assigned, cache))
            plans = [
                SimpleNamespace(
                    carbon_price_scenario_id=price.scenario_id,
                    domain_status="accepted",
                    selected_wells=["W01"],
                    pipeline=SimpleNamespace(objective_value_usd=10.0),
                    economics=None,
                )
                for price in assigned.carbon_prices
            ]
            return SimpleNamespace(
                run_id=assigned.run_id,
                plans=plans,
                cross_price_comparison=SimpleNamespace(pivot_observed=False),
            )

    orchestrator = DummyOrchestrator()
    resolver = CachedOrchestratorFieldScenarioResolver(
        orchestrator,
        request,
        {"case_a": "W01", "case_b": "W02"},
    )
    rollout_cache = {
        "case_a": {"A": SimpleNamespace(name="a")},
        "case_b": {"B": SimpleNamespace(name="b")},
    }
    result = run_field_scenario_resolves(
        design,
        [item.scenario_id for item in request.carbon_prices],
        rollout_cache,
        resolver,
    )

    assert result.downstream_resolve_count == 16
    assert len(orchestrator.calls) == 4
    assert all(call[0].detailed_top_k == 0 for call in orchestrator.calls)
    assert all(record.result["surrogate_evaluations_during_resolve"] == 0 for record in [
        *result.independent,
        *result.correlated,
    ])


def test_cached_resolver_values_chosen_policy_at_each_realized_price() -> None:
    design = build_field_scenario_design(
        ["W01", "W02"],
        ["case_a", "case_b"],
        independent_count=1,
    )
    request = inline_request().model_copy(update={"detailed_top_k": 0})
    price_ids = [item.scenario_id for item in request.carbon_prices[:2]]
    request = request.model_copy(
        update={"carbon_prices": request.carbon_prices[:2]}
    )

    metric = SimpleNamespace(value=None)

    def economics(chosen: str, values: dict[str, float]):
        return SimpleNamespace(
            results=[
                SimpleNamespace(
                    portfolio_id=f"portfolio--{chosen}",
                    carbon_price_scenario_id=realized,
                    fiscal_case_id=request.selection_fiscal_case_id,
                    npv_usd=npv,
                    npv_low_usd=npv - 1.0,
                    npv_high_usd=npv + 1.0,
                    break_even_carbon_price=metric,
                    irr=metric,
                    discounted_payback=metric,
                    break_even_oil_price=metric,
                )
                for realized, npv in values.items()
            ]
        )

    class DummyOrchestrator:
        def run_with_prediction_cache(self, assigned, cache):
            del assigned, cache
            plans = [
                SimpleNamespace(
                    carbon_price_scenario_id=price_ids[0],
                    domain_status="accepted",
                    selected_wells=["W01"],
                    well_strategies=[],
                    pipeline=SimpleNamespace(objective_value_usd=10.0),
                    economics=economics(
                        price_ids[0],
                        {price_ids[0]: 100.0, price_ids[1]: 120.0},
                    ),
                ),
                SimpleNamespace(
                    carbon_price_scenario_id=price_ids[1],
                    domain_status="accepted",
                    selected_wells=["W02"],
                    well_strategies=[],
                    pipeline=SimpleNamespace(objective_value_usd=20.0),
                    economics=economics(
                        price_ids[1],
                        {price_ids[0]: 90.0, price_ids[1]: 150.0},
                    ),
                ),
            ]
            return SimpleNamespace(
                run_id="regret-test",
                plans=plans,
                timings=SimpleNamespace(total_seconds=2.0),
                cross_price_comparison=SimpleNamespace(
                    pivot_observed=True
                ),
            )

    resolver = CachedOrchestratorFieldScenarioResolver(
        DummyOrchestrator(),
        request,
        {"case_a": "W01", "case_b": "W02"},
    )
    assignment = design.independent[0]
    context = FieldScenarioResolveContext(
        assignment=assignment,
        carbon_price_scenario_id=price_ids[0],
        rollouts_by_well={
            "W01": {"a": object()},
            "W02": {"b": object()},
        },
    )
    result = resolver(context)

    assert result["npv_by_carbon_price_usd"] == {
        price_ids[0]: 100.0,
        price_ids[1]: 120.0,
    }
    assert result["regret_by_realized_price_usd"] == {
        price_ids[0]: 0.0,
        price_ids[1]: 30.0,
    }
