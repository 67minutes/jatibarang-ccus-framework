from __future__ import annotations

from pathlib import Path

import pytest

from jatibarang_ccus.contracts import CO2Source, Coordinate, PipelineWellDemand
from jatibarang_ccus.imports.roads import (
    GREATCIRCLE_DETOUR_FACTOR,
    RoadsRegistry,
    compute_trucking_legs,
    haversine_km,
)
from tests.imports.test_roads import EXTENT, write_pbf


def _source(lat: float, lon: float) -> CO2Source:
    return CO2Source(
        id="S01",
        name="Source",
        location=Coordinate(latitude=lat, longitude=lon),
        capacity_tonnes_per_year=500_000.0,
        max_mass_flow_kg_s=600.0,
        outlet_pressure_bar=120.0,
        outlet_temperature_c=27.0,
        co2_purity=0.98,
    )


def _demand(
    candidate_id: str,
    lat: float,
    lon: float,
    mass: float,
) -> PipelineWellDemand:
    return PipelineWellDemand(
        candidate_id=candidate_id,
        location=Coordinate(latitude=lat, longitude=lon),
        annual_demand_tonnes=mass,
        peak_mass_flow_kg_s=25.0,
        pre_logistics_value_usd=1.0,
    )


def test_fallback_uses_massweighted_greatcircle_detour() -> None:
    source = _source(-6.50, 107.02)
    near = _demand("W01", -6.50, 107.06, 100_000.0)
    far = _demand("W02", -6.50, 107.18, 300_000.0)

    weighted, provenance, legs = compute_trucking_legs(
        [source],
        [near, far],
        None,
    )

    assert provenance == "greatcircle_detour_estimate"
    near_km = (
        haversine_km(-6.50, 107.02, -6.50, 107.06)
        * GREATCIRCLE_DETOUR_FACTOR
    )
    far_km = (
        haversine_km(-6.50, 107.02, -6.50, 107.18)
        * GREATCIRCLE_DETOUR_FACTOR
    )
    assert legs[0].distance_km == pytest.approx(near_km)
    assert legs[1].distance_km == pytest.approx(far_km)
    assert weighted == pytest.approx(
        (near_km * 100_000 + far_km * 300_000) / 400_000
    )
    assert legs[0].route is None


def test_road_mode_routes_over_the_network(tmp_path: Path) -> None:
    pbf = tmp_path / "toy.osm.pbf"
    write_pbf(pbf)
    registry = RoadsRegistry(tmp_path / "imports")
    record = registry.imports(pbf, EXTENT)
    graph = registry.graph(record.road_network_id)
    source = _source(-6.50, 107.02)
    demand = _demand("W01", -6.50, 107.18, 200_000.0)

    weighted, provenance, legs = compute_trucking_legs(
        [source],
        [demand],
        graph,
    )

    assert provenance == f"osm_road_network:{record.road_network_id}"
    direct = haversine_km(-6.50, 107.02, -6.50, 107.18)
    assert legs[0].distance_km > direct * 1.5
    assert legs[0].route and len(legs[0].route) >= 3
    assert weighted == pytest.approx(legs[0].distance_km)
