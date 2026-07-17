from __future__ import annotations

import math

from jatibarang_ccus.infrastructure.facility import evaluate_facility_portfolio
from jatibarang_ccus.infrastructure.thermo import mass_flow_kg_s_from_m3_day

from .helpers import COST_BASIS, DESIGN_BASIS, request, well_load


def evaluate(*wells):
    return evaluate_facility_portfolio(request(*wells), DESIGN_BASIS, COST_BASIS)


def test_standard_volume_uses_standard_not_delivery_density() -> None:
    standard = mass_flow_kg_s_from_m3_day(9_000.0, pressure_bar=1.01325, temperature_c=15.0)
    dense = mass_flow_kg_s_from_m3_day(9_000.0, pressure_bar=100.0, temperature_c=27.0)
    assert math.isclose(standard, 0.19498435003298595, rel_tol=1e-9)
    assert dense > standard * 100
    result = evaluate(well_load()).well_results[0]
    pump = next(item for item in result.equipment if item.equipment_type == "injection_pump")
    assert math.isclose(pump.specifications["fresh_co2_peak_mass_flow_kg_s"], standard, rel_tol=1e-6)
    assert result.calibration_status == "validated"


def test_fresh_stream_is_pumped_once_and_only_recycle_stream_is_compressed() -> None:
    result = evaluate(well_load()).well_results[0]
    compressor = next(item for item in result.equipment if item.equipment_type == "recycle_compressor")
    pump = next(item for item in result.equipment if item.equipment_type == "injection_pump")
    assert result.compression_power_kw > 0
    assert result.pump_power_kw > 0
    assert compressor.specifications["mass_flow_basis"] == "recovered_produced_co2_only"
    assert pump.specifications["pressure_rise_bar"] == 37.895146
    assert pump.specifications["mass_flow_basis"] == "fresh_plus_recovered_recycle"


def test_delivery_at_or_above_wellhead_pressure_has_zero_pump_duty() -> None:
    result = evaluate(well_load(delivery_pressure_bar=140.0)).well_results[0]
    pump = next(item for item in result.equipment if item.equipment_type == "injection_pump")
    assert result.pump_power_kw == 0
    assert pump.duty_train_count == pump.installed_train_count == 0


def test_recycle_disabled_has_no_compressor_duty() -> None:
    result = evaluate(
        well_load(recycle_enabled=False, recycle_recovery_fraction=0.0)
    ).well_results[0]
    compressor = next(item for item in result.equipment if item.equipment_type == "recycle_compressor")
    assert result.compression_power_kw == 0
    assert compressor.duty_train_count == compressor.installed_train_count == 0


def test_outside_calibration_pressure_is_flagged_not_silently_validated() -> None:
    result = evaluate(well_load(delivery_pressure_bar=130.0))
    assert result.validation_status == "outside_calibration_envelope"
    assert "delivery_pressure_bar" in result.well_results[0].calibration_flags
