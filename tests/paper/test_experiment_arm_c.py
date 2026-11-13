from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from jatibarang_ccus.paper.experiment.arm_c import (
    aggregate_screening_surface,
    field_scenario_tables,
    pipeline_route_rows,
)
from jatibarang_ccus.paper.experiment.aggregate import (
    economics_rows_from_field_scenarios,
)
from jatibarang_ccus.paper.field_scenarios import (
    CachedOrchestratorFieldScenarioResolver,
    build_field_scenario_design,
    run_field_scenario_resolves,
)
from jatibarang_ccus.screening.orchestrator import (
    ScreeningOrchestrator,
    ScreeningServices,
)
from jatibarang_ccus.screening.presets import materialize_inline_scenarios
from jatibarang_ccus.surrogate.postprocessing import build_prediction_result
from jatibarang_ccus.surrogate.preprocessing import compile_request
from tests.screening.helpers import FakeRunner, schedule
from tests.screening.test_orchestration_integration import (
    accepted_pipeline,
    inline_request,
    route_library,
)
from jatibarang_ccus.infrastructure.economics import evaluate_economic_batch
from jatibarang_ccus.infrastructure.facility import evaluate_facility_portfolio
from jatibarang_ccus.infrastructure.supply import evaluate_trucking_supply


class _Grid:
    def as_array(self, **_kwargs):
        return np.full((64, 64), 100.0)


def _scenario(fingerprint: str):
    return SimpleNamespace(
        candidate_id="W01",
        input_fingerprint=fingerprint,
        schedule=SimpleNamespace(
            injection_rate_m3_day=9000.0,
            cycles=3,
        ),
        predict_request=SimpleNamespace(
            geology=SimpleNamespace(permeability_md=_Grid())
        ),
    )


def _prediction(
    scenario_id: str,
    *,
    oil: float,
    injected: float,
    produced_back: float,
):
    return SimpleNamespace(
        scenario_id=scenario_id,
        production=SimpleNamespace(delta_oil_m3=[oil]),
        inventory=SimpleNamespace(
            injected_co2_tonnes=[injected],
            produced_back_co2_tonnes=[produced_back],
        ),
    )


def test_screening_surface_is_an_arithmetic_schedule_aggregate() -> None:
    rows = aggregate_screening_surface(
        [_scenario("one"), _scenario("two")],
        {
            "one": _prediction(
                "one",
                oil=10.0,
                injected=100.0,
                produced_back=20.0,
            ),
            "two": _prediction(
                "two",
                oil=30.0,
                injected=100.0,
                produced_back=40.0,
            ),
        },
    )

    assert len(rows) == 1
    assert rows[0].sample_count == 2
    assert rows[0].incremental_oil_m3 == 20.0
    assert rows[0].co2_retention_fraction == 0.7
    assert rows[0].mean_permeability_md == 100.0


def test_pipeline_route_uses_selected_trucked_legs_not_counterfactual() -> None:
    actual_leg = SimpleNamespace(
        candidate_id="W01",
        route=[(-6.5, 108.3), (-6.4, 108.4)],
    )
    counterfactual_leg = SimpleNamespace(
        candidate_id="W02",
        route=[(-6.6, 108.2), (-6.3, 108.5)],
    )
    plan = SimpleNamespace(
        carbon_price_scenario_id="article6_jcm",
        domain_status="accepted",
        selected_wells=["W01"],
        pipeline=SimpleNamespace(
            route_provenance={"selected_route_geometries": []},
            well_decisions=[],
        ),
        trucking_route_preview=SimpleNamespace(legs=[actual_leg]),
        trucking_counterfactual=SimpleNamespace(
            supply=SimpleNamespace(legs=[counterfactual_leg])
        ),
    )
    result = SimpleNamespace(plans=[plan])
    bank = SimpleNamespace(
        metadata=SimpleNamespace(
            sources=[SimpleNamespace(id="S01")],
            candidates=[
                SimpleNamespace(
                    candidate_id="W01",
                    location=SimpleNamespace(
                        latitude=-6.4,
                        longitude=108.4,
                    ),
                ),
                SimpleNamespace(
                    candidate_id="W02",
                    location=SimpleNamespace(
                        latitude=-6.3,
                        longitude=108.5,
                    ),
                ),
            ],
        )
    )

    rows = pipeline_route_rows(result, "article6_jcm", bank)

    assert {row.route_id for row in rows} == {"trucking--W01"}
    assert all(row.selected for row in rows)


def test_two_geology_two_schedule_fixture_reaches_arm_c_aggregation() -> None:
    request = inline_request(
        [schedule(cycles=3), schedule(cycles=4)]
    ).model_copy(update={"detailed_top_k": 0})
    second_geology = request.geologies["G"].model_copy(
        update={"anisotropy_ratio": 0.25}
    )
    candidates = [
        request.candidates[0],
        request.candidates[1].model_copy(
            update={"geology_id": "G2"}
        ),
    ]
    request = request.model_copy(
        update={
            "geologies": {
                "G": request.geologies["G"],
                "G2": second_geology,
            },
            "candidates": candidates,
        }
    )
    runner = FakeRunner()
    orchestrator = ScreeningOrchestrator(
        runner,
        services=ScreeningServices(
            route_builder=route_library,
            pipeline_solver=accepted_pipeline,
            facility_evaluator=evaluate_facility_portfolio,
            economic_evaluator=evaluate_economic_batch,
            trucking_evaluator=evaluate_trucking_supply,
            solver_checker=lambda _solver: None,
        ),
    )
    materialized = materialize_inline_scenarios(request)
    compiled = [
        compile_request(item.predict_request, runner.checkpoint["stats"])
        for item in materialized
    ]
    predicted = runner.predict_compiled_batch(compiled)
    cache = {
        item.input_fingerprint: build_prediction_result(
            compiled_item,
            raw,
            runner,
            include_fields=False,
        )
        for item, compiled_item, raw in zip(
            materialized,
            compiled,
            predicted,
            strict=True,
        )
    }
    assert len(cache) == 4
    initial = orchestrator.run_with_prediction_cache(request, cache)

    design = build_field_scenario_design(
        ["W01", "W02"],
        ["case_a", "case_b"],
        independent_count=2,
    )
    resolver = CachedOrchestratorFieldScenarioResolver(
        orchestrator,
        request,
        {"case_a": "W01", "case_b": "W02"},
    )
    experiment = run_field_scenario_resolves(
        design,
        [price.scenario_id for price in request.carbon_prices],
        {"case_a": cache, "case_b": cache},
        resolver,
    )
    price_by_id = {
        price.scenario_id: price.carbon_price_usd_per_tonne
        for price in request.carbon_prices
    }
    rankings, curves, regret = field_scenario_tables(
        experiment,
        price_by_id,
    )
    economics = economics_rows_from_field_scenarios(
        {
            "independent_assignment_count": 2,
            "field_scenario": experiment.model_dump(mode="json"),
            "screen_result": initial.model_dump(mode="json"),
        }
    )

    assert experiment.surrogate_evaluations_during_resolve == 0
    assert len(rankings) == 16
    assert len(curves) == 16
    assert len(regret) == 16
    assert len(economics) == 4
    assert all(row.valid_metric_count >= 0 for row in economics)
