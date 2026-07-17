from __future__ import annotations

from threading import Event

import pytest

from jatibarang_ccus.contracts import Coordinate
from jatibarang_ccus.screening.adapters import (
    discounted_supply_cost,
    interference_report,
    pipeline_demand_from_prediction,
)
from jatibarang_ccus.screening.progress import RunBusyError, RunRegistry, sse_encode
from jatibarang_ccus.screening.schemas import ProgressEvent
from jatibarang_ccus.surrogate.postprocessing import build_prediction_result
from jatibarang_ccus.surrogate.preprocessing import compile_request
from jatibarang_ccus.surrogate.schemas import PredictRequest

from .helpers import FakeRunner, geology, schedule, seed


def prediction_result(scenario_id: str = "W01-test"):
    runner = FakeRunner()
    request = PredictRequest(scenario_id=scenario_id, geology=geology(), schedule=schedule(), seed=seed())
    compiled = compile_request(request, runner.checkpoint["stats"])
    return build_prediction_result(compiled, runner.predict_compiled_batch([compiled])[0], runner, include_fields=False)


def test_pipeline_adapter_uses_peak_annual_mass_and_standard_peak_flow() -> None:
    prediction = prediction_result()
    demand = pipeline_demand_from_prediction(
        prediction,
        schedule=schedule(),
        location=Coordinate(latitude=-6.5, longitude=107.6),
        pre_logistics_value_usd=1_000_000.0,
        project_life_years=8,
        produced_co2_fraction=0.65,
    )
    assert demand.annual_demand_tonnes > 0
    assert demand.peak_mass_flow_kg_s > 0
    assert demand.influence_radius_m == prediction.plume.influence_radius_m
    assert demand.provenance["annualization"] == "maximum_calendar_year_injection"


def test_discounted_supply_addback_uses_cashflow_years() -> None:
    class Row:
        def __init__(self, year, supply):
            self.year = year
            self.supply_cost_usd = supply

    assert discounted_supply_cost([Row(0, 100.0), Row(1, 110.0), Row(2, 121.0)], 0.1) == pytest.approx(300.0)


def test_interference_matrix_is_symmetric_and_reports_overlap() -> None:
    report = interference_report(
        well_ids=["W01", "W02", "W03"],
        locations={
            "W01": Coordinate(latitude=-6.5, longitude=107.6),
            "W02": Coordinate(latitude=-6.5001, longitude=107.6001),
            "W03": Coordinate(latitude=-6.7, longitude=107.8),
        },
        influence_radii_m={"W01": 500.0, "W02": 500.0, "W03": 100.0},
    )
    assert report.matrix[0][1] is True
    assert report.matrix[1][0] is True
    assert report.matrix[0][2] is False
    assert report.flagged_pairs[0].recommendations == [
        "increase_spacing",
        "stagger_timing",
        "validate_with_full_simulation",
    ]


def test_run_registry_rejects_concurrency_and_cancels() -> None:
    registry = RunRegistry(max_active=1)
    first = registry.register("first")
    with pytest.raises(RunBusyError):
        registry.register("second")
    assert registry.cancel("first") is True
    assert first.is_set()
    registry.finish("first")
    assert registry.cancel("first") is False


def test_sse_encoding_carries_event_and_sequence() -> None:
    event = ProgressEvent(run_id="run", sequence=2, event="progress", stage="surrogate", completed=1, total=2)
    encoded = sse_encode(event)
    assert encoded.startswith("id: 2\nevent: progress\n")
    assert '"run_id":"run"' in encoded
