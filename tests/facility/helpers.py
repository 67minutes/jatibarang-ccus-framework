from __future__ import annotations

from pathlib import Path

from jatibarang_ccus.contracts import FacilityPortfolioRequest, FacilityProvenance, FacilityWellLoad


REPO_ROOT = Path(__file__).resolve().parents[2]
DESIGN_BASIS = REPO_ROOT / "data/jatibarang/facility_design_basis.json"
COST_BASIS = REPO_ROOT / "data/jatibarang/facility_cost_basis.json"
VALIDATION_CASES = REPO_ROOT / "data/jatibarang/facility_validation_cases.json"


def provenance(source_class: str = "engineering_assumption") -> list[FacilityProvenance]:
    return [FacilityProvenance(source_class=source_class, source_id="test-basis")]


def well_load(candidate_id: str = "W01", **updates: object) -> FacilityWellLoad:
    payload: dict[str, object] = {
        "candidate_id": candidate_id,
        "injection_rate_std_m3_day": 9_000.0,
        "injection_reference_pressure_bar": 1.01325,
        "injection_reference_temperature_c": 15.0,
        "fresh_co2_peak_mass_flow_kg_s": 0.19498435003298595,
        "annual_injected_co2_tonnes": 20_000.0,
        "delivery_pressure_bar": 100.0,
        "delivery_temperature_c": 27.0,
        "wellhead_injection_pressure_bar": 137.895146,
        "peak_produced_gas_std_m3_day": 5_500.0,
        "produced_gas_reference_pressure_bar": 1.01325,
        "produced_gas_reference_temperature_c": 15.0,
        "produced_co2_mole_fraction": 0.65,
        "peak_produced_liquid_m3_day": 75.0,
        "water_cut_fraction": 0.35,
        "separator_pressure_bar": 10.0,
        "separator_temperature_c": 35.0,
        "injection_operating_hours_per_year": 1_080.0,
        "production_operating_hours_per_year": 4_560.0,
        "recycle_enabled": True,
        "recycle_recovery_fraction": 0.95,
        "provenance": provenance(),
    }
    payload.update(updates)
    return FacilityWellLoad.model_validate(payload)


def request(*wells: FacilityWellLoad, cost_case: str = "base") -> FacilityPortfolioRequest:
    return FacilityPortfolioRequest(
        portfolio_id="PORT-TEST",
        cost_case=cost_case,
        design_basis_version="1.0.0",
        cost_basis_version="1.0.0",
        wells=list(wells) or [well_load()],
        provenance=provenance(),
    )
