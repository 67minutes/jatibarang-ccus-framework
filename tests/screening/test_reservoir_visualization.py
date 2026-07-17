from __future__ import annotations

from jatibarang_ccus.infrastructure.economics import evaluate_economic_batch
from jatibarang_ccus.infrastructure.facility import evaluate_facility_portfolio
from jatibarang_ccus.infrastructure.supply import evaluate_trucking_supply
from jatibarang_ccus.screening.orchestrator import ScreeningOrchestrator, ScreeningServices
from jatibarang_ccus.screening.schemas import ScreenResult

from .helpers import FakeRunner
from .test_orchestration_integration import accepted_pipeline, inline_request, route_library


def test_detailed_reservoir_is_aligned_with_prediction_and_preserves_physical_grid() -> None:
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

    result = orchestrator.run(inline_request())

    assert set(result.detailed_reservoirs) == set(result.detailed_predictions)
    scenario_id, reservoir = next(iter(result.detailed_reservoirs.items()))
    assert reservoir.scenario_id == scenario_id
    assert reservoir.geology_id == "G"
    assert (reservoir.grid.nx, reservoir.grid.ny, reservoir.grid.nz) == (64, 64, 1)
    assert (
        reservoir.grid.length_x_m,
        reservoir.grid.length_y_m,
        reservoir.grid.thickness_m,
    ) == (900.0, 600.0, 6.0)
    assert len(reservoir.static_fields.permeability_md.values) == 4096
    assert reservoir.static_fields.permeability_md.values[0] == 100.0
    assert reservoir.baseline_state is not None
    assert reservoir.baseline_state.pressure_bar.values[0] == 55.0
    assert reservoir.field_metadata["permeability_md"].scale == "log10"
    assert reservoir.field_metadata["pressure_bar"].source_class == "seed_and_surrogate_prediction"
    assert reservoir.provenance["baseline_source_id"] == "fixture-seed"
    assert reservoir.provenance["baseline_semantics"] == "final_warm_start_frame"
    assert reservoir.provenance["surveyed_orientation"] is False


def test_detailed_reservoirs_is_backward_compatible_when_absent() -> None:
    fields = ScreenResult.model_fields
    assert fields["detailed_reservoirs"].default_factory() == {}
