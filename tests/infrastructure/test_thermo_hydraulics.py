from __future__ import annotations

from jatibarang_ccus.contracts import Coordinate, RouteSegment
from jatibarang_ccus.infrastructure.hydraulics import segment_hydraulics
from jatibarang_ccus.infrastructure.thermo import co2_properties, mass_flow_kg_s_from_tonnes_year, pressure_drop_bar


def test_coolprop_co2_properties_are_real_gas_and_finite() -> None:
    props = co2_properties(100.0, 27.0)
    ideal_density = 100.0 * 100_000.0 / (188.9 * (27.0 + 273.15))
    assert props.density_kg_m3 > ideal_density * 2.0
    assert props.viscosity_pa_s > 0
    assert props.enthalpy_j_kg != 0


def test_pressure_drop_monotonic_with_flow_and_diameter() -> None:
    low_flow = pressure_drop_bar(
        mass_flow_kg_s=mass_flow_kg_s_from_tonnes_year(20_000.0),
        diameter_in=6.0,
        length_km=20.0,
        elevation_gain_m=0.0,
        pressure_bar=100.0,
        temperature_c=27.0,
    )
    high_flow = pressure_drop_bar(
        mass_flow_kg_s=mass_flow_kg_s_from_tonnes_year(40_000.0),
        diameter_in=6.0,
        length_km=20.0,
        elevation_gain_m=0.0,
        pressure_bar=100.0,
        temperature_c=27.0,
    )
    wide_pipe = pressure_drop_bar(
        mass_flow_kg_s=mass_flow_kg_s_from_tonnes_year(40_000.0),
        diameter_in=10.0,
        length_km=20.0,
        elevation_gain_m=0.0,
        pressure_bar=100.0,
        temperature_c=27.0,
    )
    assert high_flow > low_flow
    assert wide_pipe < high_flow


def test_segment_hydraulic_capacity_curves_are_ordered() -> None:
    segment = RouteSegment(
        id="A_B",
        from_node="A",
        to_node="B",
        geometry=[Coordinate(latitude=0.0, longitude=0.0), Coordinate(latitude=0.0, longitude=0.1)],
        elevation_m=[0.0, 10.0],
        length_km=10.0,
        min_slope=0.0,
        max_slope=0.001,
        route_cost=10_000.0,
        terrain_sha256="TEST",
        method="astar_srtm",
    )
    curve = segment_hydraulics(
        segment,
        diameters_in=[6.0, 10.0],
        pressure_bar=100.0,
        temperature_c=27.0,
        max_velocity_m_s=5.0,
        roughness_m=45e-6,
    )
    assert curve.diameters[10.0].capacity_tonnes_per_year > curve.diameters[6.0].capacity_tonnes_per_year
    assert curve.diameters[10.0].drop_bar_per_tonne_year < curve.diameters[6.0].drop_bar_per_tonne_year
