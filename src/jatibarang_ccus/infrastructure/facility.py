from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any

import numpy as np

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
    BasisDocument,
    annual_opex,
    balance_of_plant_capex,
    installed_equipment_capex,
    load_cost_basis,
    load_design_basis,
    train_counts,
)
from jatibarang_ccus.infrastructure.thermo import (
    DAY_TO_SECONDS,
    compression_stage_result,
    co2_phase,
    co2_properties,
    co2_properties_ph,
    mass_flow_kg_s_from_m3_day,
    psi_to_bar,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DESIGN_BASIS = REPO_ROOT / "data/jatibarang/facility_design_basis.json"
DEFAULT_COST_BASIS = REPO_ROOT / "data/jatibarang/facility_cost_basis.json"


def _input_fingerprint(well: FacilityWellLoad) -> str:
    encoded = json.dumps(well.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest().upper()


def _basis_provenance(
    source_class: str,
    source_id: str,
    *,
    notes: str,
    metadata: dict[str, Any] | None = None,
) -> FacilityProvenance:
    return FacilityProvenance(
        source_class=source_class,
        source_id=source_id,
        notes=notes,
        metadata=metadata or {},
    )


def _calibration_flags(well: FacilityWellLoad, design: dict[str, Any]) -> list[str]:
    envelope = design["calibration_envelope"]
    values = {
        "injection_rate_std_m3_day": well.injection_rate_std_m3_day,
        "delivery_pressure_bar": well.delivery_pressure_bar,
        "peak_produced_gas_std_m3_day": well.peak_produced_gas_std_m3_day,
        "produced_co2_mole_fraction": well.produced_co2_mole_fraction,
    }
    return [
        name
        for name, value in values.items()
        if float(value) < float(envelope[name][0]) or float(value) > float(envelope[name][1])
    ]


def _validate_standard_mass_flow(well: FacilityWellLoad) -> float:
    expected = mass_flow_kg_s_from_m3_day(
        well.injection_rate_std_m3_day,
        pressure_bar=well.injection_reference_pressure_bar,
        temperature_c=well.injection_reference_temperature_c,
    )
    relative_error = abs(expected - well.fresh_co2_peak_mass_flow_kg_s) / max(expected, 1e-12)
    if relative_error > 0.02:
        raise ValueError(
            f"{well.candidate_id}: fresh CO2 peak flow is inconsistent with the declared standard-volume basis "
            f"({relative_error:.2%} relative error)."
        )
    return expected


def _compression_duties(
    well: FacilityWellLoad,
    *,
    recycle_mass_flow_kg_s: float,
    design: dict[str, Any],
) -> tuple[float, float, list[dict[str, float]]]:
    compression = design["recycle_compression"]
    stages = int(compression["stages"])
    if recycle_mass_flow_kg_s <= 0 or well.delivery_pressure_bar <= well.separator_pressure_bar:
        return 0.0, 0.0, []

    pressure_ratio = (well.delivery_pressure_bar / well.separator_pressure_bar) ** (1.0 / stages)
    pressure_drop = float(compression["intercooler_pressure_drop_bar_per_stage"])
    stage_inlet = well.separator_pressure_bar
    stage_inlet_temperature = well.separator_temperature_c
    total_work_j_kg = 0.0
    total_cooling_j_kg = 0.0
    records: list[dict[str, float]] = []
    for index in range(stages):
        after_cooler_pressure = well.separator_pressure_bar * pressure_ratio ** (index + 1)
        compressor_outlet = after_cooler_pressure + (pressure_drop if index < stages - 1 else 0.0)
        cooler_outlet_temperature = (
            float(compression["final_recycle_cooler_outlet_temperature_c"])
            if index == stages - 1
            else float(compression["intercooler_outlet_temperature_c"])
        )
        stage = compression_stage_result(
            stage_inlet,
            compressor_outlet,
            stage_inlet_temperature,
            efficiency=float(compression["isentropic_efficiency"]),
            intercooler_outlet_temperature_c=cooler_outlet_temperature,
        )
        total_work_j_kg += stage.actual_work_j_kg
        total_cooling_j_kg += stage.intercooler_duty_j_kg
        records.append(
            {
                "stage": float(index + 1),
                "pressure_in_bar": stage.pressure_in_bar,
                "compressor_pressure_out_bar": stage.pressure_out_bar,
                "after_cooler_pressure_bar": after_cooler_pressure,
                "temperature_in_c": stage.temperature_in_c,
                "temperature_out_c": stage.temperature_out_c,
                "cooler_outlet_temperature_c": cooler_outlet_temperature,
                "work_j_kg": stage.actual_work_j_kg,
                "cooling_j_kg": stage.intercooler_duty_j_kg,
            }
        )
        stage_inlet = after_cooler_pressure
        stage_inlet_temperature = cooler_outlet_temperature
    return (
        recycle_mass_flow_kg_s * total_work_j_kg / 1_000.0,
        recycle_mass_flow_kg_s * total_cooling_j_kg / 1_000.0,
        records,
    )


def _separator_size(well: FacilityWellLoad, design: dict[str, Any]) -> dict[str, float | str]:
    separator = design["separator"]
    standard_mass_flow = mass_flow_kg_s_from_m3_day(
        well.peak_produced_gas_std_m3_day,
        pressure_bar=well.produced_gas_reference_pressure_bar,
        temperature_c=well.produced_gas_reference_temperature_c,
    )
    gas_properties = co2_properties(well.separator_pressure_bar, well.separator_temperature_c)
    actual_gas_m3_s = standard_mass_flow / max(gas_properties.density_kg_m3, 1e-12)
    assumed_liquid_density_kg_m3 = 800.0
    allowable_velocity_m_s = float(separator["souders_brown_k_m_s"]) * math.sqrt(
        max(assumed_liquid_density_kg_m3 - gas_properties.density_kg_m3, 1e-12)
        / gas_properties.density_kg_m3
    )
    gas_area_m2 = (
        actual_gas_m3_s * float(separator["gas_design_margin"]) / max(allowable_velocity_m_s, 1e-12)
    )
    gas_diameter_m = math.sqrt(4.0 * gas_area_m2 / math.pi)

    oil_rate_m3_s = well.peak_produced_liquid_m3_day * (1.0 - well.water_cut_fraction) / DAY_TO_SECONDS
    water_rate_m3_s = well.peak_produced_liquid_m3_day * well.water_cut_fraction / DAY_TO_SECONDS
    liquid_holdup_m3 = float(separator["liquid_design_margin"]) * (
        oil_rate_m3_s * float(separator["oil_residence_minutes"]) * 60.0
        + water_rate_m3_s * float(separator["water_residence_minutes"]) * 60.0
    )
    length_to_diameter = float(separator["target_length_to_diameter"])
    liquid_diameter_m = (4.0 * liquid_holdup_m3 / max(math.pi * length_to_diameter, 1e-12)) ** (1.0 / 3.0)
    diameter_m = max(float(separator["minimum_diameter_m"]), gas_diameter_m, liquid_diameter_m)
    length_m = length_to_diameter * diameter_m
    vessel_volume_m3 = math.pi * diameter_m * diameter_m * length_m / 4.0
    return {
        "diameter_m": diameter_m,
        "length_m": length_m,
        "vessel_volume_m3": vessel_volume_m3,
        "gas_actual_m3_s": actual_gas_m3_s,
        "gas_density_kg_m3": gas_properties.density_kg_m3,
        "allowable_gas_velocity_m_s": allowable_velocity_m_s,
        "liquid_holdup_m3": liquid_holdup_m3,
        "property_basis": "pure_CO2_conservative_screening_proxy",
    }


def _equipment_item(
    *,
    well: FacilityWellLoad,
    equipment_type: str,
    suffix: str,
    duty: float,
    duty_unit: str,
    power_kw: float,
    heat_duty_kw: float,
    operating_hours_per_year: float,
    maximum_per_train: float,
    spare_trains: int,
    cost_basis: BasisDocument,
    cost_case: str,
    calculation_method: str,
    specifications: dict[str, Any],
) -> FacilityEquipmentItem:
    active, installed = train_counts(duty, maximum_per_train=maximum_per_train, spare_trains=spare_trains)
    capex = installed_equipment_capex(
        equipment_type,
        duty,
        duty_train_count=active,
        installed_train_count=installed,
        cost_basis=cost_basis,
        cost_case=cost_case,
    )
    energy, maintenance, opex = annual_opex(
        power_kw=power_kw,
        operating_hours_per_year=operating_hours_per_year,
        capex_usd=capex,
        cost_basis=cost_basis,
        cost_case=cost_case,
    )
    return FacilityEquipmentItem(
        equipment_id=f"{well.candidate_id}-{suffix}",
        candidate_id=well.candidate_id,
        equipment_type=equipment_type,
        duty_value=float(duty),
        duty_unit=duty_unit,
        power_kw=float(power_kw),
        heat_duty_kw=float(heat_duty_kw),
        operating_hours_per_year=float(operating_hours_per_year),
        duty_train_count=active,
        installed_train_count=installed,
        capex_usd=float(capex),
        annual_energy_cost_usd=float(energy),
        annual_maintenance_usd=float(maintenance),
        annual_opex_usd=float(opex),
        calculation_method=calculation_method,
        specifications=specifications,
        provenance=[
            _basis_provenance(
                "engineering_correlation",
                f"facility-cost-basis-{cost_basis.version}",
                notes="Screening correlation; not a vendor quote or FEED estimate.",
                metadata={"sha256": cost_basis.sha256, "cost_case": cost_case},
            )
        ],
    )


def _loss_ledger(
    well: FacilityWellLoad,
    *,
    recycle_mass_flow_kg_s: float,
    produced_co2_mass_flow_kg_s: float,
    design: dict[str, Any],
) -> FacilitySurfaceLossLedger:
    losses = design["surface_losses"]
    produced_back = produced_co2_mass_flow_kg_s * well.production_operating_hours_per_year * 3_600.0 / 1_000.0
    recycled = recycle_mass_flow_kg_s * well.production_operating_hours_per_year * 3_600.0 / 1_000.0
    recycle_non_recovery = max(0.0, produced_back - recycled)
    conditioning_purge = well.annual_injected_co2_tonnes * float(losses["fresh_conditioning_purge_fraction"])
    fresh_fugitives = well.annual_injected_co2_tonnes * float(losses["fresh_fugitive_fraction"])
    recycle_fugitives = recycled * float(losses["recycle_fugitive_fraction"])
    atmospheric = conditioning_purge + fresh_fugitives + recycle_non_recovery + recycle_fugitives

    # Produced-back CO2 is already removed in Module 4's reservoir balance. Only
    # fresh-stream handling losses are an additional net-storage debit.
    net_storage_debit = conditioning_purge + fresh_fugitives
    debit_fraction = net_storage_debit / max(well.annual_injected_co2_tonnes, 1e-12)
    if debit_fraction > float(losses["maximum_net_storage_debit_fraction"]):
        raise ValueError(f"{well.candidate_id}: net-storage surface loss exceeds its configured maximum.")
    residual = abs(produced_back - recycled - recycle_non_recovery)
    return FacilitySurfaceLossLedger(
        fresh_co2_handled_tonnes_per_year=well.annual_injected_co2_tonnes,
        recycle_co2_handled_tonnes_per_year=recycled,
        conditioning_purge_tonnes_per_year=conditioning_purge,
        recycle_non_recovery_tonnes_per_year=recycle_non_recovery,
        fugitive_tonnes_per_year=fresh_fugitives + recycle_fugitives,
        atmospheric_emissions_tonnes_per_year=atmospheric,
        net_storage_debit_tonnes_per_year=net_storage_debit,
        net_storage_debit_fraction=debit_fraction,
        produced_back_co2_tonnes_per_year=produced_back,
        reconciliation_residual_tonnes_per_year=residual,
    )


def _evaluate_well(
    well: FacilityWellLoad,
    *,
    design_basis: BasisDocument,
    cost_basis: BasisDocument,
    cost_case: str,
) -> FacilityWellResult:
    design = design_basis.payload
    fresh_mass_flow = _validate_standard_mass_flow(well)
    produced_co2_mass_flow = mass_flow_kg_s_from_m3_day(
        well.peak_produced_gas_std_m3_day * well.produced_co2_mole_fraction,
        pressure_bar=well.produced_gas_reference_pressure_bar,
        temperature_c=well.produced_gas_reference_temperature_c,
    )
    recycle_mass_flow = produced_co2_mass_flow * well.recycle_recovery_fraction if well.recycle_enabled else 0.0

    compression_power_kw, cooling_duty_kw, stage_records = _compression_duties(
        well,
        recycle_mass_flow_kg_s=recycle_mass_flow,
        design=design,
    )
    fresh_delivery_properties = co2_properties(well.delivery_pressure_bar, well.delivery_temperature_c)
    pressure_rise_bar = round(
        max(0.0, well.wellhead_injection_pressure_bar - well.delivery_pressure_bar),
        9,
    )
    combined_pump_mass_flow = fresh_mass_flow + recycle_mass_flow
    recycle_delivery_properties = co2_properties(
        well.delivery_pressure_bar,
        float(design["recycle_compression"]["final_recycle_cooler_outlet_temperature_c"]),
    )
    mixed_suction_enthalpy = (
        fresh_mass_flow * fresh_delivery_properties.enthalpy_j_kg
        + recycle_mass_flow * recycle_delivery_properties.enthalpy_j_kg
    ) / max(combined_pump_mass_flow, 1e-12)
    delivery_properties = co2_properties_ph(well.delivery_pressure_bar, mixed_suction_enthalpy)
    pump_power_kw = (
        combined_pump_mass_flow
        / max(delivery_properties.density_kg_m3, 1e-12)
        * pressure_rise_bar
        * 100_000.0
        / float(design["injection_pump"]["efficiency"])
        / 1_000.0
    )

    separator = _separator_size(well, design)
    dehydration_duty = recycle_mass_flow
    dehydration_heat_kw = recycle_mass_flow * float(design["dehydration"]["heat_duty_kw_per_kg_s_recycle"])

    pump_item = _equipment_item(
        well=well,
        equipment_type="injection_pump",
        suffix="PUMP",
        duty=pump_power_kw,
        duty_unit="kW",
        power_kw=pump_power_kw,
        heat_duty_kw=0.0,
        operating_hours_per_year=well.injection_operating_hours_per_year,
        maximum_per_train=float(design["injection_pump"]["max_power_per_train_kw"]),
        spare_trains=int(design["injection_pump"]["spare_trains"]),
        cost_basis=cost_basis,
        cost_case=cost_case,
        calculation_method="CoolProp density and Q*dP/efficiency",
        specifications={
            "fresh_co2_peak_mass_flow_kg_s": fresh_mass_flow,
            "recycle_co2_peak_mass_flow_kg_s": recycle_mass_flow,
            "combined_peak_mass_flow_kg_s": combined_pump_mass_flow,
            "pressure_rise_bar": pressure_rise_bar,
            "suction_pressure_bar": well.delivery_pressure_bar,
            "discharge_pressure_bar": max(well.delivery_pressure_bar, well.wellhead_injection_pressure_bar),
            "suction_density_kg_m3": delivery_properties.density_kg_m3,
            "suction_temperature_c": delivery_properties.temperature_c,
            "suction_phase": co2_phase(well.delivery_pressure_bar, delivery_properties.temperature_c),
            "mass_flow_basis": "fresh_plus_recovered_recycle",
        },
    )
    compressor_item = _equipment_item(
        well=well,
        equipment_type="recycle_compressor",
        suffix="COMP",
        duty=compression_power_kw,
        duty_unit="kW",
        power_kw=compression_power_kw,
        heat_duty_kw=0.0,
        operating_hours_per_year=well.production_operating_hours_per_year,
        maximum_per_train=float(design["recycle_compression"]["compressor_max_power_per_train_kw"]),
        spare_trains=int(design["recycle_compression"]["spare_trains"]),
        cost_basis=cost_basis,
        cost_case=cost_case,
        calculation_method="CoolProp stage enthalpy differences with isentropic efficiency",
        specifications={
            "mass_flow_basis": "recovered_produced_co2_only",
            "recycle_co2_peak_mass_flow_kg_s": recycle_mass_flow,
            "stage_count": int(design["recycle_compression"]["stages"]),
            "stages": stage_records,
        },
    )
    cooler_item = _equipment_item(
        well=well,
        equipment_type="intercooler",
        suffix="COOL",
        duty=cooling_duty_kw,
        duty_unit="kW",
        power_kw=0.0,
        heat_duty_kw=cooling_duty_kw,
        operating_hours_per_year=well.production_operating_hours_per_year,
        maximum_per_train=500.0,
        spare_trains=int(design["recycle_compression"]["spare_trains"]),
        cost_basis=cost_basis,
        cost_case=cost_case,
        calculation_method="CoolProp post-compression to intercooler-outlet enthalpy difference",
        specifications={
            "intercooler_outlet_temperature_c": design["recycle_compression"]["intercooler_outlet_temperature_c"],
            "final_recycle_cooler_outlet_temperature_c": design["recycle_compression"][
                "final_recycle_cooler_outlet_temperature_c"
            ],
        },
    )
    dehydration_item = _equipment_item(
        well=well,
        equipment_type="dehydration",
        suffix="DEHY",
        duty=dehydration_duty,
        duty_unit="kg/s recycle CO2",
        power_kw=dehydration_heat_kw,
        heat_duty_kw=dehydration_heat_kw,
        operating_hours_per_year=well.production_operating_hours_per_year,
        maximum_per_train=float(design["dehydration"]["max_recycle_kg_s_per_train"]),
        spare_trains=int(design["dehydration"]["spare_trains"]),
        cost_basis=cost_basis,
        cost_case=cost_case,
        calculation_method="recycle-throughput dehydration package correlation",
        specifications={"outlet_water_target_ppmv": design["dehydration"]["outlet_water_target_ppmv"]},
    )
    separator_item = _equipment_item(
        well=well,
        equipment_type="three_phase_separator",
        suffix="SEP",
        duty=float(separator["vessel_volume_m3"]),
        duty_unit="m3 vessel volume",
        power_kw=0.0,
        heat_duty_kw=0.0,
        operating_hours_per_year=well.production_operating_hours_per_year,
        maximum_per_train=50.0,
        spare_trains=int(design["separator"]["spare_trains"]),
        cost_basis=cost_basis,
        cost_case=cost_case,
        calculation_method="Souders-Brown gas capacity plus liquid residence-time volume",
        specifications=separator,
    )

    direct_items = [pump_item, compressor_item, cooler_item, dehydration_item, separator_item]
    direct_capex = sum(item.capex_usd for item in direct_items)
    bop_capex = balance_of_plant_capex(direct_capex, cost_basis=cost_basis, cost_case=cost_case)
    _, bop_maintenance, bop_opex = annual_opex(
        power_kw=0.0,
        operating_hours_per_year=0.0,
        capex_usd=bop_capex,
        cost_basis=cost_basis,
        cost_case=cost_case,
    )
    bop_item = FacilityEquipmentItem(
        equipment_id=f"{well.candidate_id}-BOP",
        candidate_id=well.candidate_id,
        equipment_type="balance_of_plant",
        duty_value=direct_capex,
        duty_unit="USD direct installed equipment",
        duty_train_count=1 if direct_capex > 0 else 0,
        installed_train_count=1 if direct_capex > 0 else 0,
        capex_usd=bop_capex,
        annual_maintenance_usd=bop_maintenance,
        annual_opex_usd=bop_opex,
        calculation_method="fraction of direct installed equipment CAPEX",
        specifications={
            "balance_of_plant_fraction": cost_basis.payload["cases"][cost_case]["balance_of_plant_fraction"]
        },
        provenance=[
            _basis_provenance(
                "engineering_correlation",
                f"facility-cost-basis-{cost_basis.version}",
                notes="Screening balance-of-plant factor.",
                metadata={"sha256": cost_basis.sha256, "cost_case": cost_case},
            )
        ],
    )
    equipment = [*direct_items, bop_item]
    loss_ledger = _loss_ledger(
        well,
        recycle_mass_flow_kg_s=recycle_mass_flow,
        produced_co2_mass_flow_kg_s=produced_co2_mass_flow,
        design=design,
    )
    flags = _calibration_flags(well, design)
    calibration_evidence = design.get("calibration_evidence", {})
    calibration_status = (
        "outside_calibration_envelope"
        if flags
        else (
            "validated"
            if calibration_evidence.get("engineering_validation_verdict") == "PASS"
            else "unvalidated"
        )
    )
    return FacilityWellResult(
        candidate_id=well.candidate_id,
        input_fingerprint=_input_fingerprint(well),
        equipment=equipment,
        compression_power_kw=compression_power_kw,
        pump_power_kw=pump_power_kw,
        total_power_kw=compression_power_kw + pump_power_kw,
        separator_capacity_m3_day=well.peak_produced_gas_std_m3_day,
        capex_usd=sum(item.capex_usd for item in equipment),
        annual_opex_usd=sum(item.annual_opex_usd for item in equipment),
        surface_loss_tonnes_per_year=loss_ledger.net_storage_debit_tonnes_per_year,
        surface_loss_fraction=loss_ledger.net_storage_debit_fraction,
        loss_ledger=loss_ledger,
        reconciliation_passed=True,
        calibration_status=calibration_status,
        calibration_flags=flags,
        provenance=[
            *well.provenance,
            _basis_provenance(
                "engineering_assumption",
                f"facility-design-basis-{design_basis.version}",
                notes="Dedicated well-pad skid design basis.",
                metadata={"sha256": design_basis.sha256},
            ),
        ],
    )


def evaluate_facility_portfolio(
    request: FacilityPortfolioRequest,
    design_basis_path: Path | str = DEFAULT_DESIGN_BASIS,
    cost_basis_path: Path | str = DEFAULT_COST_BASIS,
) -> FacilityPortfolioResult:
    design_basis = load_design_basis(design_basis_path)
    cost_basis = load_cost_basis(cost_basis_path)
    if request.design_basis_version != design_basis.version:
        raise ValueError(
            f"Design basis version mismatch: request={request.design_basis_version}, file={design_basis.version}."
        )
    if request.cost_basis_version != cost_basis.version:
        raise ValueError(f"Cost basis version mismatch: request={request.cost_basis_version}, file={cost_basis.version}.")

    well_results = [
        _evaluate_well(
            well,
            design_basis=design_basis,
            cost_basis=cost_basis,
            cost_case=request.cost_case,
        )
        for well in request.wells
    ]
    outside = any(well.calibration_status == "outside_calibration_envelope" for well in well_results)
    calibration_evidence = design_basis.payload.get("calibration_evidence", {})
    validated = calibration_evidence.get("engineering_validation_verdict") == "PASS"
    return FacilityPortfolioResult(
        portfolio_id=request.portfolio_id,
        design_basis_version=design_basis.version,
        cost_basis_version=cost_basis.version,
        calibration_version=str(calibration_evidence.get("version", "unvalidated")),
        validation_status=(
            "outside_calibration_envelope" if outside else ("validated" if validated else "unvalidated")
        ),
        well_results=well_results,
        total_capex_usd=sum(well.capex_usd for well in well_results),
        total_annual_opex_usd=sum(well.annual_opex_usd for well in well_results),
        total_surface_loss_tonnes_per_year=sum(well.surface_loss_tonnes_per_year for well in well_results),
        reconciliation_passed=True,
        evidence_manifest=str(calibration_evidence.get("manifest_path", "")),
        provenance=[
            *request.provenance,
            _basis_provenance(
                "engineering_correlation",
                "feature003-runtime-v1",
                notes="CoolProp runtime facility model; DWSIM validation status is reported separately.",
                metadata={"design_sha256": design_basis.sha256, "cost_sha256": cost_basis.sha256},
            ),
        ],
    )


def benchmark_facility_portfolio(
    request: FacilityPortfolioRequest,
    design_basis_path: Path | str = DEFAULT_DESIGN_BASIS,
    cost_basis_path: Path | str = DEFAULT_COST_BASIS,
    *,
    repeats: int = 20,
) -> float:
    evaluate_facility_portfolio(request, design_basis_path, cost_basis_path)
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        evaluate_facility_portfolio(request, design_basis_path, cost_basis_path)
        samples.append(time.perf_counter() - start)
    return float(np.percentile(np.asarray(samples, dtype=float), 95))


def facility_input_from_screened_value(
    *,
    candidate_id: str,
    parameters: dict[str, float | int],
    injected_co2_tonnes: float,
    stored_co2_tonnes: float,
    delivery_pressure_bar: float,
    peak_produced_gas_m3_day: float,
    produced_co2_fraction: float,
    assumptions: dict[str, Any],
    well_count: int | None = None,
) -> FacilityWellLoad:
    del stored_co2_tonnes, well_count
    cycles = int(parameters.get("cycles", 3))
    production_days = float(parameters.get("production_days", 190.0))
    injection_rate = float(parameters["injection_rate_m3_day"])
    reference_pressure = 1.01325
    reference_temperature = 15.0
    facility_assumptions = assumptions.get("facility", {})
    pipeline_assumptions = assumptions.get("pipeline", {})
    return FacilityWellLoad(
        candidate_id=candidate_id,
        injection_rate_std_m3_day=injection_rate,
        injection_reference_pressure_bar=reference_pressure,
        injection_reference_temperature_c=reference_temperature,
        fresh_co2_peak_mass_flow_kg_s=mass_flow_kg_s_from_m3_day(
            injection_rate,
            pressure_bar=reference_pressure,
            temperature_c=reference_temperature,
        ),
        annual_injected_co2_tonnes=float(injected_co2_tonnes),
        delivery_pressure_bar=max(80.0, float(delivery_pressure_bar)),
        delivery_temperature_c=float(pipeline_assumptions.get("ground_temperature_c", 27.0)),
        wellhead_injection_pressure_bar=psi_to_bar(float(facility_assumptions.get("injection_pressure_psi", 2_000.0))),
        peak_produced_gas_std_m3_day=float(peak_produced_gas_m3_day),
        produced_gas_reference_pressure_bar=reference_pressure,
        produced_gas_reference_temperature_c=reference_temperature,
        produced_co2_mole_fraction=float(produced_co2_fraction),
        peak_produced_liquid_m3_day=float(facility_assumptions.get("peak_produced_liquid_m3_day", 75.0)),
        water_cut_fraction=float(facility_assumptions.get("water_cut_fraction", 0.35)),
        separator_pressure_bar=float(facility_assumptions.get("separator_pressure_bar", 10.0)),
        separator_temperature_c=float(facility_assumptions.get("separator_temperature_c", 35.0)),
        injection_operating_hours_per_year=min(8_760.0, cycles * 45.0 * 24.0),
        production_operating_hours_per_year=min(8_760.0, cycles * production_days * 24.0),
        recycle_enabled=True,
        recycle_recovery_fraction=float(facility_assumptions.get("recycle_recovery_fraction", 0.95)),
        provenance=[
            _basis_provenance(
                "engineering_assumption",
                "phase1-feature003-compatibility-adapter",
                notes="Temporary analytic Phase 1 adapter; Feature 005 will supply real surrogate loads.",
            )
        ],
    )


def evaluate_facility(inputs: FacilityWellLoad, assumptions: dict[str, Any] | None = None) -> FacilityWellResult:
    del assumptions
    request = FacilityPortfolioRequest(
        portfolio_id=f"legacy-{inputs.candidate_id}",
        cost_case="base",
        design_basis_version="1.0.0",
        cost_basis_version="1.0.0",
        wells=[inputs],
        provenance=inputs.provenance,
    )
    return evaluate_facility_portfolio(request).well_results[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Feature 003 CoolProp facility calculation.")
    parser.add_argument("--design-basis", type=Path, default=DEFAULT_DESIGN_BASIS)
    parser.add_argument("--cost-basis", type=Path, default=DEFAULT_COST_BASIS)
    args = parser.parse_args()
    well = FacilityWellLoad(
        candidate_id="smoke",
        injection_rate_std_m3_day=9_000.0,
        injection_reference_pressure_bar=1.01325,
        injection_reference_temperature_c=15.0,
        fresh_co2_peak_mass_flow_kg_s=mass_flow_kg_s_from_m3_day(9_000.0, 1.01325, 15.0),
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
        provenance=[
            _basis_provenance("engineering_assumption", "facility-smoke", notes="CLI smoke input")
        ],
    )
    request = FacilityPortfolioRequest(
        portfolio_id="facility-smoke",
        cost_case="base",
        design_basis_version="1.0.0",
        cost_basis_version="1.0.0",
        wells=[well],
        provenance=well.provenance,
    )
    print(json.dumps(evaluate_facility_portfolio(request, args.design_basis, args.cost_basis).model_dump(), indent=2))


if __name__ == "__main__":
    main()
