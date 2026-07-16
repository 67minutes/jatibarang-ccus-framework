from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from jatibarang_ccus.contracts import PressureProfilePoint, RouteSegment
from jatibarang_ccus.infrastructure.thermo import (
    BAR_TO_PA,
    co2_properties,
    friction_factor,
    mass_flow_kg_s_from_tonnes_year,
    pipe_area_m2,
    tonnes_year_from_kg_s,
)


GRAVITY_M_S2 = 9.80665


@dataclass(frozen=True)
class DiameterHydraulic:
    diameter_in: float
    maop_bar: float
    capacity_tonnes_per_year: float
    drop_bar_at_capacity: float
    drop_bar_per_tonne_year: float
    minimum_flow_kg_s: float
    maximum_flow_kg_s: float
    flow_breakpoints_kg_s: list[float]
    pressure_drop_breakpoints_bar: list[float]


@dataclass(frozen=True)
class SegmentHydraulics:
    segment_id: str
    length_km: float
    elevation_gain_m: float
    diameters: dict[float, DiameterHydraulic]


def _coordinate_distance_m(first, second) -> float:
    lat_mid = math.radians((first.latitude + second.latitude) / 2.0)
    dx = (second.longitude - first.longitude) * 111_320.0 * math.cos(lat_mid)
    dy = (second.latitude - first.latitude) * 110_574.0
    return math.hypot(dx, dy)


def _hydraulic_head_bar(pressure_bar: float, elevation_m: float, reference_density_kg_m3: float) -> float:
    return pressure_bar + reference_density_kg_m3 * GRAVITY_M_S2 * elevation_m / BAR_TO_PA


def integrate_route_profile(
    segment: RouteSegment,
    *,
    mass_flow_kg_s: float,
    diameter_in: float,
    inlet_pressure_bar: float,
    temperature_c: float,
    roughness_m: float,
    max_step_m: float,
    property_pressure_floor_bar: float = 80.0,
    reverse: bool = False,
) -> list[PressureProfilePoint]:
    geometry = list(reversed(segment.geometry)) if reverse else segment.geometry
    elevations = list(reversed(segment.elevation_m)) if reverse else segment.elevation_m
    pressure = float(inlet_pressure_bar)
    distance_m = 0.0
    reference_density = co2_properties(max(pressure, property_pressure_floor_bar), temperature_c).density_kg_m3
    area = pipe_area_m2(diameter_in)
    current_props = co2_properties(max(pressure, property_pressure_floor_bar), temperature_c)
    first_velocity = mass_flow_kg_s / max(current_props.density_kg_m3 * area, 1e-12)
    profile = [
        PressureProfilePoint(
            distance_km=0.0,
            elevation_m=float(elevations[0]),
            pressure_bar=pressure,
            hydraulic_head_bar=_hydraulic_head_bar(pressure, float(elevations[0]), reference_density),
            density_kg_m3=current_props.density_kg_m3,
            velocity_m_s=max(0.0, first_velocity),
        )
    ]
    diameter_m = float(diameter_in) * 0.0254
    for first, second, elevation_a, elevation_b in zip(geometry, geometry[1:], elevations, elevations[1:]):
        edge_length = _coordinate_distance_m(first, second)
        steps = max(1, int(math.ceil(edge_length / max(float(max_step_m), 1.0))))
        step_length = edge_length / steps
        step_dz = (float(elevation_b) - float(elevation_a)) / steps
        for step in range(1, steps + 1):
            props = current_props
            velocity = mass_flow_kg_s / max(props.density_kg_m3 * area, 1e-12) if mass_flow_kg_s > 0 else 0.0
            reynolds = props.density_kg_m3 * velocity * diameter_m / max(props.viscosity_pa_s, 1e-12)
            friction = friction_factor(reynolds, roughness_m, diameter_m)
            friction_pa = friction * (step_length / diameter_m) * props.density_kg_m3 * velocity * velocity / 2.0
            elevation_pa = props.density_kg_m3 * GRAVITY_M_S2 * step_dz
            pressure -= (friction_pa + elevation_pa) / BAR_TO_PA
            distance_m += step_length
            current_elevation = float(elevation_a) + step * step_dz
            next_props = co2_properties(max(pressure, property_pressure_floor_bar), temperature_c)
            current_props = next_props
            next_velocity = mass_flow_kg_s / max(next_props.density_kg_m3 * area, 1e-12) if mass_flow_kg_s > 0 else 0.0
            profile.append(
                PressureProfilePoint(
                    distance_km=distance_m / 1_000.0,
                    elevation_m=current_elevation,
                    pressure_bar=pressure,
                    hydraulic_head_bar=_hydraulic_head_bar(pressure, current_elevation, reference_density),
                    density_kg_m3=next_props.density_kg_m3,
                    velocity_m_s=max(0.0, next_velocity),
                )
            )
    return profile


def _integrate_outlet_pressure(
    segment: RouteSegment,
    *,
    mass_flow_kg_s: float,
    diameter_in: float,
    inlet_pressure_bar: float,
    temperature_c: float,
    roughness_m: float,
    max_step_m: float,
    property_pressure_floor_bar: float,
) -> float:
    """Fast local-state integration for curve generation without profile objects."""

    pressure = float(inlet_pressure_bar)
    diameter_m = float(diameter_in) * 0.0254
    area = pipe_area_m2(diameter_in)
    props = co2_properties(max(pressure, property_pressure_floor_bar), temperature_c)
    for first, second, elevation_a, elevation_b in zip(
        segment.geometry,
        segment.geometry[1:],
        segment.elevation_m,
        segment.elevation_m[1:],
    ):
        edge_length = _coordinate_distance_m(first, second)
        steps = max(1, int(math.ceil(edge_length / max(float(max_step_m), 1.0))))
        step_length = edge_length / steps
        step_dz = (float(elevation_b) - float(elevation_a)) / steps
        for _ in range(steps):
            velocity = mass_flow_kg_s / max(props.density_kg_m3 * area, 1e-12) if mass_flow_kg_s > 0 else 0.0
            reynolds = props.density_kg_m3 * velocity * diameter_m / max(props.viscosity_pa_s, 1e-12)
            friction = friction_factor(reynolds, roughness_m, diameter_m)
            friction_pa = friction * (step_length / diameter_m) * props.density_kg_m3 * velocity * velocity / 2.0
            elevation_pa = props.density_kg_m3 * GRAVITY_M_S2 * step_dz
            pressure -= (friction_pa + elevation_pa) / BAR_TO_PA
            props = co2_properties(max(pressure, property_pressure_floor_bar), temperature_c)
    return pressure


def booster_power_kw(
    *,
    mass_flow_kg_s: float,
    lift_bar: float,
    pressure_bar: float,
    temperature_c: float,
    efficiency: float,
) -> float:
    density = co2_properties(pressure_bar, temperature_c).density_kg_m3
    hydraulic_watts = float(mass_flow_kg_s) * float(lift_bar) * BAR_TO_PA / max(density, 1e-12)
    return hydraulic_watts / max(float(efficiency), 1e-6) / 1_000.0


def _diameter_flow_kg_s(
    *, diameter_in: float, pressure_bar: float, temperature_c: float, velocity_m_s: float
) -> float:
    props = co2_properties(pressure_bar, temperature_c)
    return props.density_kg_m3 * pipe_area_m2(diameter_in) * velocity_m_s


def segment_hydraulics(
    segment: RouteSegment,
    *,
    diameters_in: list[float],
    pressure_anchors_bar: list[float] | None = None,
    pressure_bar: float | None = None,
    temperature_c: float,
    min_velocity_m_s: float = 0.0,
    max_velocity_m_s: float,
    breakpoint_fractions: list[float] | None = None,
    roughness_m: float,
    max_step_m: float = 100.0,
    maop_by_diameter: dict[float, float] | None = None,
) -> SegmentHydraulics:
    anchors = pressure_anchors_bar or [float(pressure_bar if pressure_bar is not None else 100.0)]
    fractions = sorted(set(float(value) for value in (breakpoint_fractions or [0.0, 0.25, 0.5, 0.75, 1.0])))
    curves: dict[float, DiameterHydraulic] = {}
    for diameter in diameters_in:
        # Capacity must obey the velocity ceiling at the lowest allowed density;
        # minimum active flow must obey the velocity floor at the highest density.
        anchor_capacities = [
            _diameter_flow_kg_s(
                diameter_in=float(diameter), pressure_bar=anchor, temperature_c=temperature_c, velocity_m_s=max_velocity_m_s
            )
            for anchor in anchors
        ]
        anchor_minimums = [
            _diameter_flow_kg_s(
                diameter_in=float(diameter), pressure_bar=anchor, temperature_c=temperature_c, velocity_m_s=min_velocity_m_s
            )
            for anchor in anchors
        ]
        maximum_flow = min(anchor_capacities)
        minimum_flow = max(anchor_minimums)
        flows = [maximum_flow * fraction for fraction in fractions]
        if min_velocity_m_s > 0 and all(abs(value - minimum_flow) > 1e-9 for value in flows):
            flows.append(minimum_flow)
            flows.sort()
        drops: list[float] = []
        for flow in flows:
            anchor_drops = []
            for anchor in anchors:
                outlet_pressure = _integrate_outlet_pressure(
                    segment,
                    mass_flow_kg_s=flow,
                    diameter_in=float(diameter),
                    inlet_pressure_bar=float(anchor),
                    temperature_c=temperature_c,
                    roughness_m=roughness_m,
                    max_step_m=max_step_m,
                    property_pressure_floor_bar=min(80.0, min(anchors)),
                )
                anchor_drops.append(float(anchor) - outlet_pressure)
            drops.append(max(anchor_drops))
        # A conservative loss envelope must not decrease as flow rises.
        monotone: list[float] = []
        for value in drops:
            monotone.append(max(value, monotone[-1] if monotone else value))
        capacity_tonnes = tonnes_year_from_kg_s(maximum_flow)
        drop_capacity = monotone[-1]
        curves[float(diameter)] = DiameterHydraulic(
            diameter_in=float(diameter),
            maop_bar=float((maop_by_diameter or {}).get(float(diameter), max(anchors))),
            capacity_tonnes_per_year=capacity_tonnes,
            drop_bar_at_capacity=drop_capacity,
            drop_bar_per_tonne_year=drop_capacity / max(capacity_tonnes, 1e-9),
            minimum_flow_kg_s=minimum_flow,
            maximum_flow_kg_s=maximum_flow,
            flow_breakpoints_kg_s=flows,
            pressure_drop_breakpoints_bar=monotone,
        )
    return SegmentHydraulics(
        segment_id=segment.id,
        length_km=segment.length_km,
        elevation_gain_m=float(segment.elevation_m[-1] - segment.elevation_m[0]),
        diameters=curves,
    )


def precompute_hydraulics(*, segments: list[RouteSegment], assumptions: dict[str, Any]) -> dict[str, SegmentHydraulics]:
    pipe_rows = assumptions["pipe_diameters"]
    diameters = [float(item["diameter_in"]) for item in pipe_rows]
    maop = {float(item["diameter_in"]): float(item.get("maop_bar", assumptions["max_pressure_bar"])) for item in pipe_rows}
    anchor_overrides = assumptions.get("segment_pressure_anchors_bar", {})
    result: dict[str, SegmentHydraulics] = {}
    for segment in segments:
        base_segment_id = segment.id.removesuffix("__REVERSE")
        anchors = anchor_overrides.get(base_segment_id, assumptions.get("pressure_anchors_bar", [assumptions["reference_pressure_bar"]]))
        result[segment.id] = segment_hydraulics(
            segment,
            diameters_in=diameters,
            pressure_anchors_bar=[float(value) for value in anchors],
            pressure_bar=float(assumptions["reference_pressure_bar"]),
            temperature_c=float(assumptions["ground_temperature_c"]),
            min_velocity_m_s=float(assumptions.get("min_velocity_m_s", 0.0)),
            max_velocity_m_s=float(assumptions["max_velocity_m_s"]),
            breakpoint_fractions=[float(value) for value in assumptions.get("hydraulic_breakpoint_fractions", [0.0, 0.25, 0.5, 0.75, 1.0])],
            roughness_m=float(assumptions.get("pipe_roughness_m", 45e-6)),
            max_step_m=float(assumptions.get("hydraulic_curve_step_m", 300.0)),
            maop_by_diameter=maop,
        )
    return result


def dense_phase_ok(pressure_bar: float, assumptions: dict[str, Any]) -> bool:
    return float(pressure_bar) >= float(assumptions["dense_phase_min_pressure_bar"])
