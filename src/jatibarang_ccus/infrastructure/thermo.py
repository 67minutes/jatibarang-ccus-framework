from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math
import threading
from typing import Literal

import CoolProp.CoolProp as CP


CO2 = "CO2"
BAR_TO_PA = 100_000.0
PSI_TO_BAR = 0.0689475729
DAY_TO_SECONDS = 86_400.0
YEAR_TO_SECONDS = 365.25 * DAY_TO_SECONDS
_STATE_LOCAL = threading.local()


@dataclass(frozen=True)
class CO2Properties:
    pressure_bar: float
    temperature_c: float
    density_kg_m3: float
    viscosity_pa_s: float
    enthalpy_j_kg: float
    entropy_j_kg_k: float


@dataclass(frozen=True)
class CompressionStageResult:
    pressure_in_bar: float
    pressure_out_bar: float
    temperature_in_c: float
    temperature_out_c: float
    actual_work_j_kg: float
    intercooler_duty_j_kg: float


def c_to_k(temperature_c: float) -> float:
    return float(temperature_c) + 273.15


def bar_to_pa(pressure_bar: float) -> float:
    return float(pressure_bar) * BAR_TO_PA


def psi_to_bar(pressure_psi: float) -> float:
    return float(pressure_psi) * PSI_TO_BAR


def _co2_state():
    state = getattr(_STATE_LOCAL, "state", None)
    if state is None:
        state = CP.AbstractState("HEOS", CO2)
        _STATE_LOCAL.state = state
    return state


@lru_cache(maxsize=65_536)
def _co2_properties_cached(pressure_bar: float, temperature_c: float) -> CO2Properties:
    pressure_pa = bar_to_pa(pressure_bar)
    temperature_k = c_to_k(temperature_c)
    state = _co2_state()
    state.update(CP.PT_INPUTS, pressure_pa, temperature_k)
    return CO2Properties(
        pressure_bar=float(pressure_bar),
        temperature_c=float(temperature_c),
        density_kg_m3=float(state.rhomass()),
        viscosity_pa_s=float(state.viscosity()),
        enthalpy_j_kg=float(state.hmass()),
        entropy_j_kg_k=float(state.smass()),
    )


def co2_properties(pressure_bar: float, temperature_c: float) -> CO2Properties:
    # Rounding stabilizes cache keys without affecting screening-scale results.
    return _co2_properties_cached(round(float(pressure_bar), 8), round(float(temperature_c), 8))


@lru_cache(maxsize=65_536)
def _co2_properties_ph_cached(pressure_bar: float, enthalpy_j_kg: float) -> CO2Properties:
    pressure_pa = bar_to_pa(pressure_bar)
    state = _co2_state()
    state.update(CP.HmassP_INPUTS, float(enthalpy_j_kg), pressure_pa)
    return CO2Properties(
        pressure_bar=float(pressure_bar),
        temperature_c=float(state.T() - 273.15),
        density_kg_m3=float(state.rhomass()),
        viscosity_pa_s=float(state.viscosity()),
        enthalpy_j_kg=float(state.hmass()),
        entropy_j_kg_k=float(state.smass()),
    )


def co2_properties_ph(pressure_bar: float, enthalpy_j_kg: float) -> CO2Properties:
    return _co2_properties_ph_cached(round(float(pressure_bar), 8), round(float(enthalpy_j_kg), 4))


def mass_flow_kg_s_from_tonnes_year(tonnes_per_year: float) -> float:
    return float(tonnes_per_year) * 1_000.0 / YEAR_TO_SECONDS


def tonnes_year_from_kg_s(kg_s: float) -> float:
    return float(kg_s) * YEAR_TO_SECONDS / 1_000.0


def mass_flow_kg_s_from_m3_day(rate_m3_day: float, pressure_bar: float, temperature_c: float) -> float:
    density = co2_properties(pressure_bar, temperature_c).density_kg_m3
    return float(rate_m3_day) * density / DAY_TO_SECONDS


def pipe_area_m2(diameter_in: float) -> float:
    diameter_m = float(diameter_in) * 0.0254
    return math.pi * diameter_m * diameter_m / 4.0


def pipe_velocity_m_s(mass_flow_kg_s: float, diameter_in: float, pressure_bar: float, temperature_c: float) -> float:
    props = co2_properties(pressure_bar, temperature_c)
    return float(mass_flow_kg_s) / max(props.density_kg_m3 * pipe_area_m2(diameter_in), 1e-12)


def friction_factor(reynolds: float, roughness_m: float, diameter_m: float) -> float:
    if reynolds <= 0:
        return 0.0
    if reynolds < 2_300.0:
        return 64.0 / reynolds
    rel_roughness = roughness_m / max(diameter_m, 1e-12)
    return 0.25 / (math.log10(rel_roughness / 3.7 + 5.74 / (reynolds**0.9)) ** 2)


def pressure_drop_bar(
    *,
    mass_flow_kg_s: float,
    diameter_in: float,
    length_km: float,
    elevation_gain_m: float,
    pressure_bar: float,
    temperature_c: float,
    roughness_m: float = 45e-6,
) -> float:
    if mass_flow_kg_s <= 0 or length_km <= 0:
        hydrostatic = co2_properties(pressure_bar, temperature_c).density_kg_m3 * 9.80665 * elevation_gain_m
        return max(0.0, hydrostatic / BAR_TO_PA)

    props = co2_properties(pressure_bar, temperature_c)
    diameter_m = float(diameter_in) * 0.0254
    area = math.pi * diameter_m * diameter_m / 4.0
    velocity = mass_flow_kg_s / max(props.density_kg_m3 * area, 1e-12)
    reynolds = props.density_kg_m3 * velocity * diameter_m / max(props.viscosity_pa_s, 1e-12)
    friction = friction_factor(reynolds, roughness_m, diameter_m)
    length_m = float(length_km) * 1_000.0
    friction_pa = friction * (length_m / diameter_m) * props.density_kg_m3 * velocity * velocity / 2.0
    elevation_pa = props.density_kg_m3 * 9.80665 * float(elevation_gain_m)
    return max(0.0, (friction_pa + elevation_pa) / BAR_TO_PA)


def isentropic_compression_work_j_kg(
    pressure_in_bar: float,
    pressure_out_bar: float,
    temperature_in_c: float,
    *,
    efficiency: float,
) -> float:
    if pressure_out_bar <= pressure_in_bar:
        return 0.0
    p1 = bar_to_pa(pressure_in_bar)
    p2 = bar_to_pa(pressure_out_bar)
    t1 = c_to_k(temperature_in_c)
    h1 = float(CP.PropsSI("H", "P", p1, "T", t1, CO2))
    s1 = float(CP.PropsSI("S", "P", p1, "T", t1, CO2))
    h2s = float(CP.PropsSI("H", "P", p2, "S", s1, CO2))
    return max(0.0, (h2s - h1) / max(float(efficiency), 1e-6))


def compression_stage_result(
    pressure_in_bar: float,
    pressure_out_bar: float,
    temperature_in_c: float,
    *,
    efficiency: float,
    intercooler_outlet_temperature_c: float,
) -> CompressionStageResult:
    if pressure_out_bar <= pressure_in_bar:
        return CompressionStageResult(
            pressure_in_bar=float(pressure_in_bar),
            pressure_out_bar=float(pressure_out_bar),
            temperature_in_c=float(temperature_in_c),
            temperature_out_c=float(temperature_in_c),
            actual_work_j_kg=0.0,
            intercooler_duty_j_kg=0.0,
        )
    p1 = bar_to_pa(pressure_in_bar)
    p2 = bar_to_pa(pressure_out_bar)
    t1 = c_to_k(temperature_in_c)
    h1 = float(CP.PropsSI("H", "P", p1, "T", t1, CO2))
    s1 = float(CP.PropsSI("S", "P", p1, "T", t1, CO2))
    h2s = float(CP.PropsSI("H", "P", p2, "S", s1, CO2))
    actual_work = max(0.0, (h2s - h1) / max(float(efficiency), 1e-6))
    h2 = h1 + actual_work
    t2 = float(CP.PropsSI("T", "P", p2, "H", h2, CO2))
    h_cooled = float(CP.PropsSI("H", "P", p2, "T", c_to_k(intercooler_outlet_temperature_c), CO2))
    return CompressionStageResult(
        pressure_in_bar=float(pressure_in_bar),
        pressure_out_bar=float(pressure_out_bar),
        temperature_in_c=float(temperature_in_c),
        temperature_out_c=t2 - 273.15,
        actual_work_j_kg=actual_work,
        intercooler_duty_j_kg=max(0.0, h2 - h_cooled),
    )


def co2_phase(pressure_bar: float, temperature_c: float) -> str:
    return str(CP.PhaseSI("P", bar_to_pa(pressure_bar), "T", c_to_k(temperature_c), CO2))


def phase_label(pressure_bar: float, temperature_c: float) -> Literal["dense_or_supercritical", "gas_or_two_phase_risk"]:
    if pressure_bar >= 80.0:
        return "dense_or_supercritical"
    return "gas_or_two_phase_risk"
