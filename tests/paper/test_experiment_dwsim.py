from __future__ import annotations

import json

from jatibarang_ccus.paper.experiment.dwsim_confirm import (
    BASE_CASES_PATH,
    _density,
    build_dwsim_case_document,
    select_throughput_cases,
    total_design_mass_flow_kg_s,
)


def _plan(index: int, rate: float) -> dict:
    plan = {
        "plan_id": f"plan-{index}",
        "schedule": {"injection_rate_m3_day": rate},
        "delivery_pressure_bar": 80.0 + index,
        "produced_co2_mole_fraction": 0.65,
        "prediction_summary": {
            "peak_produced_gas_std_m3_day": 4000.0 + 100.0 * index
        },
    }
    combined = _recomputed_total(plan)
    plan["facility"] = {
        "equipment": [
            {
                "equipment_type": "injection_pump",
                "specifications": {
                    "combined_peak_mass_flow_kg_s": combined,
                },
            }
        ]
    }
    return plan


def _recomputed_total(plan: dict) -> float:
    # Build the fixture from the same locked physical inputs, then verify that
    # the production helper treats the facility result as authoritative.
    fixed = json.loads(
        BASE_CASES_PATH.read_text(encoding="utf-8")
    )["fixed"]
    fresh = (
        plan["schedule"]["injection_rate_m3_day"]
        * _density(
            pressure_bar=fixed["injection_reference_pressure_bar"],
            temperature_c=fixed["injection_reference_temperature_c"],
        )
        / 86_400.0
    )
    recycled = (
        plan["prediction_summary"]["peak_produced_gas_std_m3_day"]
        * plan["produced_co2_mole_fraction"]
        * _density(
            pressure_bar=fixed["produced_gas_reference_pressure_bar"],
            temperature_c=fixed["produced_gas_reference_temperature_c"],
        )
        / 86_400.0
        * fixed["recycle_recovery_fraction"]
    )
    return fresh + recycled


def test_dwsim_selection_is_minimum_third_and_maximum_with_fresh_cases() -> None:
    plans = [_plan(index, 8000.0 + index * 500.0) for index in range(5)]
    selected = select_throughput_cases(plans)

    assert [item[0] for item in selected] == [
        "minimum",
        "median",
        "maximum",
    ]
    assert [item[1]["plan_id"] for item in selected] == [
        "plan-0",
        "plan-2",
        "plan-4",
    ]
    document = build_dwsim_case_document(selected)
    assert document["expected_case_count"] == 3
    assert len(document["cases"]) == 3
    assert all(
        case["produced_co2_mole_fraction"] == 0.65
        for case in document["cases"]
    )
    assert total_design_mass_flow_kg_s(plans[0]) == (
        plans[0]["facility"]["equipment"][0]["specifications"][
            "combined_peak_mass_flow_kg_s"
        ]
    )
