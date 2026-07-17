from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from jatibarang_ccus.contracts import (
    CO2Source,
    Coordinate,
    PipelineDesignRequest,
    PipelineWellDemand,
    RouteLibrary,
)


def _source(**updates):
    payload = {
        "id": "S1",
        "name": "Source",
        "location": Coordinate(latitude=-6.5, longitude=108.0),
        "capacity_tonnes_per_year": 100_000.0,
        "max_mass_flow_kg_s": 100.0,
        "outlet_pressure_bar": 120.0,
        "outlet_temperature_c": 27.0,
        "co2_purity": 0.98,
    }
    payload.update(updates)
    return CO2Source(**payload)


def _demand(**updates):
    payload = {
        "candidate_id": "W1",
        "location": Coordinate(latitude=-6.48, longitude=108.1),
        "annual_demand_tonnes": 20_000.0,
        "peak_mass_flow_kg_s": 10.0,
        "pre_logistics_value_usd": 2_000_000.0,
    }
    payload.update(updates)
    return PipelineWellDemand(**payload)


def test_source_rejects_unqualified_impure_stream() -> None:
    with pytest.raises(ValidationError):
        _source(co2_purity=0.90)


def test_minimum_cost_requires_mandatory_well_or_delivery_target() -> None:
    with pytest.raises(ValidationError):
        PipelineDesignRequest(
            objective_mode="min_lifecycle_cost",
            sources=[_source()],
            well_demands=[_demand()],
            route_library=RouteLibrary(nodes=[], segments=[], fingerprint="x", provenance={}),
            annual_co2_budget_tonnes=50_000.0,
            assumptions={"pipeline": {}, "economics": {}},
        )


def test_annual_demand_and_peak_flow_are_independent_positive_units() -> None:
    demand = _demand(annual_demand_tonnes=15_000.0, peak_mass_flow_kg_s=25.0)
    assert demand.annual_demand_tonnes == 15_000.0
    assert demand.peak_mass_flow_kg_s == 25.0


def test_tracked_json_schema_covers_the_public_design_request() -> None:
    schema_path = Path(__file__).resolve().parents[2] / "specs" / "002-pipeline-optimizer" / "contracts" / "pipeline-optimizer.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert {"sources", "well_demands", "route_library", "annual_co2_budget_tonnes", "assumptions"} <= set(schema["required"])
    assert schema["properties"]["objective_mode"]["enum"] == ["max_net_value", "min_lifecycle_cost"]
