from __future__ import annotations

import numpy as np
import CoolProp.CoolProp as CP
import pytest

from jatibarang_ccus.surrogate.metadata import confidence_for_horizon
from jatibarang_ccus.surrogate import postprocessing
from jatibarang_ccus.surrogate.postprocessing import (
    build_prediction_result,
    co2_density_kg_m3,
    plume_summary,
    reservoir_inventory_tonnes,
)
from jatibarang_ccus.surrogate.preprocessing import compile_request
from jatibarang_ccus.surrogate.runner import load_surrogate

from .helpers import request_from_mrst


def test_uniform_inventory_has_analytic_value() -> None:
    porosity = np.full((64, 64), 0.2)
    gas = np.full((2, 64, 64), 0.5)
    z_co2 = np.full((2, 64, 64), 0.25)
    density = np.full((2, 64, 64), 100.0)
    inventory = reservoir_inventory_tonnes(porosity, gas, z_co2, density, cell_volume_m3=10.0)
    expected = 64 * 64 * 10.0 * 0.2 * 0.5 * 0.25 * 100.0 / 1000.0
    np.testing.assert_allclose(inventory, [expected, expected])


def test_plume_area_and_influence_radius_use_locked_thresholds() -> None:
    gas = np.zeros((1, 64, 64), dtype=np.float32)
    z_co2 = np.zeros_like(gas)
    completion = np.zeros((64, 64), dtype=np.float32)
    completion[10, 10] = 1.0
    gas[0, 10, 10:13] = 0.01
    z_co2[0, 10, 10:13] = 0.02

    result = plume_summary(gas, z_co2, completion, cell_area_m2=25.0)
    assert result.maximum_z_co2_area_m2 == 75.0
    assert result.maximum_gas_area_m2 == 75.0
    assert result.influence_radius_m == 10.0


def test_confidence_marks_extended_horizon() -> None:
    band, extended = confidence_for_horizon(40)
    assert band.name == "last_24"
    assert extended is True

    band, extended = confidence_for_horizon(10)
    assert band.name == "t_plus_10"
    assert extended is False


def test_injection_mass_and_inventory_reconciliation_are_unit_consistent() -> None:
    runner = load_surrogate()
    compiled = compile_request(request_from_mrst(), runner.checkpoint["stats"])
    prediction = runner.predict_compiled(compiled, max_forecast_steps=1)
    result = build_prediction_result(compiled, prediction, runner, include_fields=False)
    assert result.inventory.status == "available"

    reference_density = CP.PropsSI(
        "D",
        "P",
        compiled.injection_reference_pressure_bar * 1e5,
        "T",
        compiled.injection_reference_temperature_c + 273.15,
        "CO2",
    )
    expected_first_injected = compiled.injection_rate_m3_day * compiled.dt_days[0] * reference_density / 1000.0
    assert result.inventory.injected_co2_tonnes[0] == pytest.approx(expected_first_injected)

    initial_density = co2_density_kg_m3(compiled.initial_pressure_bar, compiled.reservoir_temperature_c)
    initial_inventory = reservoir_inventory_tonnes(
        compiled.porosity,
        compiled.initial_gas_saturation,
        compiled.initial_z_co2,
        initial_density,
        compiled.cell_volume_m3,
    )[0]
    inventory = np.asarray(result.inventory.co2_inventory_tonnes, dtype=float)
    injected = np.asarray(result.inventory.injected_co2_tonnes, dtype=float)
    produced_back = np.asarray(result.inventory.produced_back_co2_tonnes, dtype=float)
    residual = np.asarray(result.inventory.reconciliation_residual_tonnes, dtype=float)
    np.testing.assert_allclose(initial_inventory + injected - produced_back - inventory, residual, atol=1e-9)


def test_inventory_failure_is_isolated_as_low_confidence(monkeypatch) -> None:
    runner = load_surrogate()
    compiled = compile_request(request_from_mrst(), runner.checkpoint["stats"])
    prediction = runner.predict_compiled(compiled, max_forecast_steps=1)

    def fail_density(*_args, **_kwargs):
        raise RuntimeError("synthetic density failure")

    monkeypatch.setattr(postprocessing, "co2_density_kg_m3", fail_density)
    result = build_prediction_result(compiled, prediction, runner, include_fields=False)
    assert result.inventory.status == "unavailable"
    assert all(value is None for value in result.inventory.co2_inventory_tonnes)
    assert "CO2 inventory calculation is unavailable" in result.confidence.low_confidence_reasons
