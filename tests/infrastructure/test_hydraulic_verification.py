from __future__ import annotations

from jatibarang_ccus.contracts import Coordinate, RouteSegment
from jatibarang_ccus.infrastructure.hydraulics import (
    booster_power_kw,
    integrate_route_profile,
    segment_hydraulics,
)


def _segment(elevations: list[float]) -> RouteSegment:
    return RouteSegment(
        id="A_B",
        from_node="A",
        to_node="B",
        geometry=[Coordinate(latitude=0.0, longitude=0.0), Coordinate(latitude=0.0, longitude=0.09)],
        elevation_m=elevations,
        length_km=10.0,
        min_slope=min(0.0, (elevations[-1] - elevations[0]) / 10_000.0),
        max_slope=max(0.0, (elevations[-1] - elevations[0]) / 10_000.0),
        route_cost=10_000.0,
        terrain_sha256="TEST",
    )


def test_downhill_static_pressure_can_recover_while_head_drops() -> None:
    profile = integrate_route_profile(
        _segment([100.0, 0.0]),
        mass_flow_kg_s=20.0,
        diameter_in=10.0,
        inlet_pressure_bar=110.0,
        temperature_c=27.0,
        roughness_m=45e-6,
        max_step_m=100.0,
    )
    assert profile[-1].pressure_bar > profile[0].pressure_bar
    assert profile[-1].hydraulic_head_bar < profile[0].hydraulic_head_bar
    assert max(point.distance_km for point in profile) > 9.0


def test_piecewise_curve_has_peak_flow_breakpoints_and_is_monotone() -> None:
    result = segment_hydraulics(
        _segment([0.0, 10.0]),
        diameters_in=[6.0],
        pressure_anchors_bar=[80.0, 100.0, 120.0],
        temperature_c=27.0,
        min_velocity_m_s=1.0,
        max_velocity_m_s=5.0,
        breakpoint_fractions=[0.0, 0.25, 0.5, 0.75, 1.0],
        roughness_m=45e-6,
        max_step_m=100.0,
        maop_by_diameter={6.0: 160.0},
    )
    curve = result.diameters[6.0]
    assert len(curve.flow_breakpoints_kg_s) == 6
    assert curve.minimum_flow_kg_s > 0
    assert curve.maximum_flow_kg_s > curve.minimum_flow_kg_s
    assert curve.pressure_drop_breakpoints_bar == sorted(curve.pressure_drop_breakpoints_bar)


def test_booster_power_scales_with_flow_and_lift() -> None:
    base = booster_power_kw(mass_flow_kg_s=10.0, lift_bar=10.0, pressure_bar=90.0, temperature_c=27.0, efficiency=0.78)
    assert booster_power_kw(mass_flow_kg_s=20.0, lift_bar=10.0, pressure_bar=90.0, temperature_c=27.0, efficiency=0.78) > base
    assert booster_power_kw(mass_flow_kg_s=10.0, lift_bar=20.0, pressure_bar=90.0, temperature_c=27.0, efficiency=0.78) > base
