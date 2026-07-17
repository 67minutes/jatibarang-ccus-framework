from __future__ import annotations

import pytest

from jatibarang_ccus.contracts import (
    AnnualEconomicPeriod,
    FacilityEquipmentItem,
    FacilityWellResult,
    NetworkCostBreakdown,
    PipelineDesignResult,
)
from jatibarang_ccus.infrastructure.economic_adapters import (
    annualize_prediction,
    facility_for_well,
    pipeline_raw_supply,
)
from jatibarang_ccus.surrogate.schemas import PredictionResult


def test_surrogate_interval_crossing_calendar_year_is_prorated():
    prediction = PredictionResult.model_validate(
        {
            "scenario_id": "cross-year",
            "timeline": [
                {
                    "index": 0,
                    "dt_days": 10,
                    "elapsed_days": 370,
                    "stage": "inject",
                    "cycle": 1,
                    "origin": "surrogate",
                }
            ],
            "production": {
                "delta_oil_m3": [100],
                "delta_gas_m3": [200],
                "cumulative_oil_m3": [100],
                "cumulative_gas_m3": [200],
            },
            "inventory": {
                "status": "available",
                "co2_inventory_tonnes": [90],
                "injected_co2_tonnes": [100],
                "produced_back_co2_tonnes": [10],
                "reconciliation_residual_tonnes": [0],
                "method": "test",
                "caveat": "none",
            },
            "plume": {
                "maximum_z_co2_area_m2": 0,
                "maximum_gas_area_m2": 0,
                "influence_radius_m": 0,
                "z_co2_threshold": 0.01,
                "gas_saturation_threshold": 0.01,
            },
            "extrapolation_flags": [],
            "confidence": {
                "band": "test",
                "horizon_steps": 1,
                "metrics": {},
                "extended_horizon": False,
                "low_confidence_reasons": [],
            },
            "provenance": {},
        }
    )
    periods = annualize_prediction(
        prediction,
        project_life_years=2,
        produced_co2_fraction=0.5,
        co2_density_kg_m3=2,
    )
    assert [item.oil_produced_m3 for item in periods] == pytest.approx([50, 50])
    assert [item.injected_co2_tonnes for item in periods] == pytest.approx([50, 50])
    assert [item.inventory_produced_back_co2_tonnes for item in periods] == pytest.approx([5, 5])
    assert [item.injection_hours for item in periods] == pytest.approx([120, 120])


def test_pipeline_adapter_uses_only_raw_cost_components(provenance):
    costs = NetworkCostBreakdown(
        cost_case="base",
        cost_year=2025,
        pipeline_capex_usd=1_000,
        booster_capex_usd=200,
        annual_maintenance_usd=30,
        annual_booster_energy_usd=20,
        annual_opex_usd=50,
        commodity_supply_usd_per_tonne=8,
        present_value_lifecycle_cost_usd=99_999,
        levelized_transport_usd_per_tonne=999,
        levelized_delivered_usd_per_tonne=1_007,
    )
    pipeline = PipelineDesignResult.model_construct(
        costs=costs,
        source_annual_flows_tonnes={"S": 1_000},
        route_provenance={"fingerprint": "test"},
    )
    periods = [
        AnnualEconomicPeriod(
            year=1,
            injection_hours=100,
            injected_co2_tonnes=50,
            inventory_produced_back_co2_tonnes=0,
        ),
        AnnualEconomicPeriod(year=2, inventory_produced_back_co2_tonnes=0),
    ]
    supply = pipeline_raw_supply(pipeline, periods, 2, allocation_fraction=0.25)
    assert supply.pipeline_capex_usd == 250
    assert supply.booster_capex_usd == 50
    assert supply.annual_maintenance_usd == [7.5, 0]
    assert supply.annual_booster_energy_usd == [1, 0]
    assert not hasattr(supply, "levelized_delivered_usd_per_tonne")


def test_facility_energy_uses_modeled_hours_and_maintenance_active_year(provenance):
    equipment = FacilityEquipmentItem.model_construct(
        equipment_type="injection_pump",
        operating_hours_per_year=100,
        annual_energy_cost_usd=100,
        annual_maintenance_usd=10,
    )
    facility = FacilityWellResult.model_construct(
        candidate_id="W1",
        capex_usd=500,
        equipment=[equipment],
    )
    periods = [
        AnnualEconomicPeriod(
            year=1,
            injection_hours=50,
            inventory_produced_back_co2_tonnes=0,
        ),
        AnnualEconomicPeriod(year=2, inventory_produced_back_co2_tonnes=0),
    ]
    adapted = facility_for_well(facility, periods, 2)
    assert adapted.capex_usd == 500
    assert adapted.annual_opex_usd == [60, 0]
