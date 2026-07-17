from __future__ import annotations

from jatibarang_ccus.infrastructure.facility import benchmark_facility_portfolio, evaluate_facility_portfolio

from .helpers import COST_BASIS, DESIGN_BASIS, request, well_load


def evaluate(*wells):
    return evaluate_facility_portfolio(request(*wells), DESIGN_BASIS, COST_BASIS)


def equipment(result, equipment_type: str):
    return next(item for item in result.well_results[0].equipment if item.equipment_type == equipment_type)


def test_fixed_flowsheet_returns_every_auditable_equipment_class() -> None:
    result = evaluate(well_load())
    types = {item.equipment_type for item in result.well_results[0].equipment}
    assert types == {
        "injection_pump",
        "recycle_compressor",
        "intercooler",
        "dehydration",
        "three_phase_separator",
        "balance_of_plant",
    }


def test_separator_size_increases_with_gas_and_liquid_load() -> None:
    low = evaluate(well_load(peak_produced_gas_std_m3_day=4_500.0, peak_produced_liquid_m3_day=50.0))
    high = evaluate(well_load(peak_produced_gas_std_m3_day=7_300.0, peak_produced_liquid_m3_day=100.0))
    low_separator = equipment(low, "three_phase_separator")
    high_separator = equipment(high, "three_phase_separator")
    assert high_separator.duty_value > low_separator.duty_value
    assert high_separator.specifications["diameter_m"] >= low_separator.specifications["diameter_m"]
    assert high_separator.specifications["length_m"] >= low_separator.specifications["length_m"]


def test_throughput_increases_power_capex_and_opex() -> None:
    low = evaluate(well_load(injection_rate_std_m3_day=8_000.0, fresh_co2_peak_mass_flow_kg_s=0.17331942225154306))
    high = evaluate(well_load(injection_rate_std_m3_day=10_000.0, fresh_co2_peak_mass_flow_kg_s=0.21664927781442883))
    assert high.well_results[0].pump_power_kw > low.well_results[0].pump_power_kw
    assert high.total_capex_usd > low.total_capex_usd
    assert high.total_annual_opex_usd > low.total_annual_opex_usd


def test_rotating_equipment_reports_n_plus_one_train_counts() -> None:
    result = evaluate(well_load())
    assert equipment(result, "injection_pump").duty_train_count == 1
    assert equipment(result, "injection_pump").installed_train_count == 2
    assert equipment(result, "recycle_compressor").duty_train_count == 1
    assert equipment(result, "recycle_compressor").installed_train_count == 2


def test_injection_and_production_energy_use_separate_hours() -> None:
    result = evaluate(well_load(injection_operating_hours_per_year=100.0, production_operating_hours_per_year=200.0))
    pump = equipment(result, "injection_pump")
    compressor = equipment(result, "recycle_compressor")
    assert pump.operating_hours_per_year == 100.0
    assert compressor.operating_hours_per_year == 200.0


def test_warm_eight_well_p95_runtime_meets_screening_budget() -> None:
    wells = [well_load(candidate_id=f"W{index:02d}") for index in range(1, 9)]
    p95_seconds = benchmark_facility_portfolio(
        request(*wells),
        DESIGN_BASIS,
        COST_BASIS,
        repeats=12,
    )
    assert p95_seconds <= 0.5
