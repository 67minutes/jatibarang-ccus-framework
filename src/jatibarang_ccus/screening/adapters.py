from __future__ import annotations

from typing import Iterable

import numpy as np
from pyproj import Geod

from jatibarang_ccus.contracts import (
    Coordinate,
    FacilityProvenance,
    FacilityWellLoad,
    PipelineWellDemand,
)
from jatibarang_ccus.infrastructure.economic_adapters import annualize_prediction
from jatibarang_ccus.infrastructure.thermo import mass_flow_kg_s_from_m3_day, psi_to_bar
from jatibarang_ccus.surrogate.schemas import OperatingSchedule, PredictionResult

from .schemas import InterferencePair, InterferenceReport


STANDARD_PRESSURE_BAR = 1.01325
STANDARD_TEMPERATURE_C = 15.0


def prediction_source_class(prediction: PredictionResult) -> str:
    value = str(prediction.provenance.get("source_class", "surrogate_prediction"))
    return "mrst_truth" if value in {"mrst", "mrst_truth"} else "surrogate_prediction"


def discounted_supply_cost(annual_cashflows: Iterable, discount_rate: float) -> float:
    return float(
        sum(
            float(row.supply_cost_usd) / ((1.0 + discount_rate) ** int(row.year))
            for row in annual_cashflows
        )
    )


def pipeline_demand_from_prediction(
    prediction: PredictionResult,
    *,
    schedule: OperatingSchedule,
    location: Coordinate,
    pre_logistics_value_usd: float,
    project_life_years: int,
    produced_co2_fraction: float,
    candidate_id: str | None = None,
) -> PipelineWellDemand:
    periods = annualize_prediction(
        prediction,
        project_life_years=project_life_years,
        produced_co2_fraction=produced_co2_fraction,
    )
    identifier = candidate_id or prediction.scenario_id.split("-", 1)[0]
    return PipelineWellDemand(
        candidate_id=identifier,
        location=location,
        annual_demand_tonnes=max(period.injected_co2_tonnes for period in periods),
        peak_mass_flow_kg_s=mass_flow_kg_s_from_m3_day(
            schedule.injection_rate_m3_day,
            STANDARD_PRESSURE_BAR,
            STANDARD_TEMPERATURE_C,
        ),
        pre_logistics_value_usd=pre_logistics_value_usd,
        influence_radius_m=max(prediction.plume.influence_radius_m, 1e-6),
        provenance={
            "source_class": prediction_source_class(prediction),
            "scenario_id": prediction.scenario_id,
            "annualization": "maximum_calendar_year_injection",
            "peak_sizing_basis": "standard_state_schedule_injection_rate",
        },
    )


def peak_produced_gas_std_m3_day(prediction: PredictionResult) -> float:
    rates = [
        float(delta) / float(step.dt_days)
        for step, delta in zip(prediction.timeline, prediction.production.delta_gas_m3, strict=True)
        if step.stage == "produce" and step.dt_days > 0
    ]
    return max(rates, default=0.0)


def facility_well_from_prediction(
    prediction: PredictionResult,
    *,
    candidate_id: str,
    schedule: OperatingSchedule,
    delivery_pressure_bar: float,
    produced_co2_fraction: float,
    project_life_years: int,
    assumptions: dict,
) -> FacilityWellLoad:
    periods = annualize_prediction(
        prediction,
        project_life_years=project_life_years,
        produced_co2_fraction=produced_co2_fraction,
    )
    facility = assumptions.get("facility", {})
    pipeline = assumptions.get("pipeline", {})
    return FacilityWellLoad(
        candidate_id=candidate_id,
        injection_rate_std_m3_day=schedule.injection_rate_m3_day,
        injection_reference_pressure_bar=STANDARD_PRESSURE_BAR,
        injection_reference_temperature_c=STANDARD_TEMPERATURE_C,
        fresh_co2_peak_mass_flow_kg_s=mass_flow_kg_s_from_m3_day(
            schedule.injection_rate_m3_day,
            STANDARD_PRESSURE_BAR,
            STANDARD_TEMPERATURE_C,
        ),
        annual_injected_co2_tonnes=max(period.injected_co2_tonnes for period in periods),
        delivery_pressure_bar=max(80.0, delivery_pressure_bar),
        delivery_temperature_c=float(pipeline.get("ground_temperature_c", 27.0)),
        wellhead_injection_pressure_bar=psi_to_bar(float(facility.get("injection_pressure_psi", 2000.0))),
        peak_produced_gas_std_m3_day=peak_produced_gas_std_m3_day(prediction),
        produced_gas_reference_pressure_bar=STANDARD_PRESSURE_BAR,
        produced_gas_reference_temperature_c=STANDARD_TEMPERATURE_C,
        produced_co2_mole_fraction=produced_co2_fraction,
        peak_produced_liquid_m3_day=float(facility.get("peak_produced_liquid_m3_day", 75.0)),
        water_cut_fraction=float(facility.get("water_cut_fraction", 0.35)),
        separator_pressure_bar=float(facility.get("separator_pressure_bar", 10.0)),
        separator_temperature_c=float(facility.get("separator_temperature_c", 35.0)),
        injection_operating_hours_per_year=max(period.injection_hours for period in periods),
        production_operating_hours_per_year=max(period.production_hours for period in periods),
        recycle_enabled=True,
        recycle_recovery_fraction=float(facility.get("recycle_recovery_fraction", 0.95)),
        provenance=[
            FacilityProvenance(
                source_class=prediction_source_class(prediction),
                source_id=prediction.scenario_id,
                notes=(
                    "Offline MRST truth adapted through the shared Feature 005 facility path."
                    if prediction_source_class(prediction) == "mrst_truth"
                    else "Real Feature 001 production and injection load adapted by Feature 005."
                ),
                metadata={"produced_co2_fraction_source": "explicit_screening_assumption"},
            )
        ],
    )


def interference_report(
    *,
    well_ids: list[str],
    locations: dict[str, Coordinate],
    influence_radii_m: dict[str, float],
) -> InterferenceReport:
    geod = Geod(ellps="WGS84")
    ordered = list(well_ids)
    matrix = [[False for _ in ordered] for _ in ordered]
    pairs: list[InterferencePair] = []
    for first_index, first in enumerate(ordered):
        for second_index in range(first_index + 1, len(ordered)):
            second = ordered[second_index]
            first_location = locations[first]
            second_location = locations[second]
            _az1, _az2, distance = geod.inv(
                first_location.longitude,
                first_location.latitude,
                second_location.longitude,
                second_location.latitude,
            )
            radius_sum = influence_radii_m[first] + influence_radii_m[second]
            overlap = float(distance) < radius_sum
            matrix[first_index][second_index] = overlap
            matrix[second_index][first_index] = overlap
            if overlap:
                pairs.append(
                    InterferencePair(
                        first_well_id=first,
                        second_well_id=second,
                        distance_m=float(distance),
                        radius_sum_m=radius_sum,
                        overlap=True,
                        recommendations=[
                            "increase_spacing",
                            "stagger_timing",
                            "validate_with_full_simulation",
                        ],
                    )
                )
    return InterferenceReport(well_ids=ordered, matrix=matrix, flagged_pairs=pairs)
