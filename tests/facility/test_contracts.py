from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from jatibarang_ccus.contracts import (
    FacilityEquipmentItem,
    FacilityPortfolioRequest,
    FacilityPortfolioResult,
    FacilityProvenance,
    FacilitySurfaceLossLedger,
    FacilityWellLoad,
    FacilityWellResult,
)
from jatibarang_ccus.infrastructure.facility_costs import (
    installed_equipment_capex,
    load_cost_basis,
    load_design_basis,
    load_validation_cases,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def provenance(source_class: str = "engineering_assumption") -> list[FacilityProvenance]:
    return [FacilityProvenance(source_class=source_class, source_id="test-basis")]


def well_load(candidate_id: str = "W01") -> FacilityWellLoad:
    return FacilityWellLoad(
        candidate_id=candidate_id,
        injection_rate_std_m3_day=9_000.0,
        injection_reference_pressure_bar=1.01325,
        injection_reference_temperature_c=15.0,
        fresh_co2_peak_mass_flow_kg_s=0.19498435003298595,
        annual_injected_co2_tonnes=20_000.0,
        delivery_pressure_bar=100.0,
        delivery_temperature_c=27.0,
        wellhead_injection_pressure_bar=137.895146,
        peak_produced_gas_std_m3_day=5_500.0,
        produced_gas_reference_pressure_bar=1.01325,
        produced_gas_reference_temperature_c=15.0,
        produced_co2_mole_fraction=0.65,
        peak_produced_liquid_m3_day=75.0,
        water_cut_fraction=0.35,
        separator_pressure_bar=10.0,
        separator_temperature_c=35.0,
        injection_operating_hours_per_year=1_080.0,
        production_operating_hours_per_year=4_560.0,
        recycle_enabled=True,
        recycle_recovery_fraction=0.95,
        provenance=provenance(),
    )


def request(*wells: FacilityWellLoad) -> FacilityPortfolioRequest:
    return FacilityPortfolioRequest(
        portfolio_id="PORT-TEST",
        cost_case="base",
        design_basis_version="1.0",
        cost_basis_version="1.0",
        wells=list(wells) or [well_load()],
        provenance=provenance(),
    )


def result_payload() -> FacilityPortfolioResult:
    item = FacilityEquipmentItem(
        equipment_id="W01-PUMP",
        candidate_id="W01",
        equipment_type="injection_pump",
        duty_value=10.0,
        duty_unit="kW",
        power_kw=10.0,
        duty_train_count=1,
        installed_train_count=2,
        capex_usd=100_000.0,
        annual_opex_usd=10_000.0,
        calculation_method="test",
        provenance=provenance("engineering_correlation"),
    )
    losses = FacilitySurfaceLossLedger(
        fresh_co2_handled_tonnes_per_year=20_000.0,
        recycle_co2_handled_tonnes_per_year=1_000.0,
        conditioning_purge_tonnes_per_year=10.0,
        recycle_non_recovery_tonnes_per_year=50.0,
        fugitive_tonnes_per_year=4.0,
        atmospheric_emissions_tonnes_per_year=64.0,
        net_storage_debit_tonnes_per_year=14.0,
        net_storage_debit_fraction=0.0007,
        produced_back_co2_tonnes_per_year=1_052.631578947,
        reconciliation_residual_tonnes_per_year=0.0,
    )
    well = FacilityWellResult(
        candidate_id="W01",
        input_fingerprint="TEST",
        equipment=[item],
        compression_power_kw=0.0,
        pump_power_kw=10.0,
        total_power_kw=10.0,
        separator_capacity_m3_day=5_500.0,
        capex_usd=100_000.0,
        annual_opex_usd=10_000.0,
        surface_loss_tonnes_per_year=14.0,
        surface_loss_fraction=0.0007,
        loss_ledger=losses,
        reconciliation_passed=True,
        calibration_status="unvalidated",
        provenance=provenance(),
    )
    return FacilityPortfolioResult(
        portfolio_id="PORT-TEST",
        design_basis_version="1.0",
        cost_basis_version="1.0",
        calibration_version="unvalidated",
        validation_status="unvalidated",
        well_results=[well],
        total_capex_usd=100_000.0,
        total_annual_opex_usd=10_000.0,
        total_surface_loss_tonnes_per_year=14.0,
        reconciliation_passed=True,
        provenance=provenance(),
    )


def test_request_and_result_validate_against_frozen_json_schema() -> None:
    schema = json.loads(
        (REPO_ROOT / "specs/003-facility-model/contracts/facility-model.schema.json").read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema)
    validator.validate(request(well_load()).model_dump(mode="json"))
    validator.validate(result_payload().model_dump(mode="json"))


def test_portfolio_rejects_duplicate_well_ids() -> None:
    with pytest.raises(ValidationError, match="unique"):
        request(well_load("W01"), well_load("W01"))


def test_well_contract_rejects_delivery_below_dense_phase_floor() -> None:
    payload = well_load().model_dump()
    payload["delivery_pressure_bar"] = 79.9
    with pytest.raises(ValidationError):
        FacilityWellLoad.model_validate(payload)


def test_result_contract_rejects_unreconciled_payload() -> None:
    payload = result_payload().model_dump()
    payload["reconciliation_passed"] = False
    with pytest.raises(ValidationError):
        FacilityPortfolioResult.model_validate(payload)


def test_basis_documents_are_versioned_hashed_and_complete() -> None:
    design = load_design_basis(REPO_ROOT / "data/jatibarang/facility_design_basis.json")
    costs = load_cost_basis(REPO_ROOT / "data/jatibarang/facility_cost_basis.json")
    cases = load_validation_cases(REPO_ROOT / "data/jatibarang/facility_validation_cases.json")
    assert design.version == costs.version == cases.version == "1.0.0"
    assert len(design.sha256) == len(costs.sha256) == len(cases.sha256) == 64
    assert len(cases.payload["cases"]) == 8


def test_cost_cases_are_monotonic_for_the_same_equipment_duty() -> None:
    costs = load_cost_basis(REPO_ROOT / "data/jatibarang/facility_cost_basis.json")
    values = [
        installed_equipment_capex(
            "injection_pump",
            100.0,
            duty_train_count=1,
            installed_train_count=2,
            cost_basis=costs,
            cost_case=case,
        )
        for case in ("low", "base", "high")
    ]
    assert values[0] < values[1] < values[2]
