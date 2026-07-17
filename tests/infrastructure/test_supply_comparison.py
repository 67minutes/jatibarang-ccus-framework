from __future__ import annotations

import json
from pathlib import Path

import pytest

from jatibarang_ccus.contracts import SupplyComparisonRequest
from jatibarang_ccus.infrastructure.costs import annuity_present_value_factor, load_cost_basis, pipe_capex_usd
from jatibarang_ccus.infrastructure.supply import compare_supply_scenarios


NETWORK_TEST = Path(__file__).with_name("test_pipeline_network.py")


def _network_request():
    namespace: dict[str, object] = {}
    exec(compile(NETWORK_TEST.read_text(encoding="utf-8"), str(NETWORK_TEST), "exec"), namespace)
    return namespace["_request"]()


def test_cost_basis_has_monotonic_cases_and_reconciled_escalation() -> None:
    basis = load_cost_basis("data/jatibarang/pipeline_cost_basis.json")
    coefficients = [basis["cases"][name]["pipe_usd_per_inch_m"] for name in ("low", "base", "high")]
    assert coefficients == sorted(coefficients)
    capex = [pipe_capex_usd(diameter_in=8.0, length_km=20.0, case=basis["cases"][name]) for name in ("low", "base", "high")]
    assert capex == sorted(capex)
    assert annuity_present_value_factor(0.0, 8) == 8.0
    assert basis["pipeline_source"]["escalation_factor_2018_to_2025"] > 1.0
    assert basis["pipeline_source"]["source_year"] == 2025
    assert basis["trucking_source"]["source_year"] == 2025
    assert "pipeline_capex_usd" in basis["equations"]
    assert len(basis["citations"]) >= 2


@pytest.mark.parametrize("case", ["low", "base", "high"])
def test_supply_comparison_uses_common_accounting_basis(case: str) -> None:
    request = _network_request().model_copy(update={"cost_case": case})
    result = compare_supply_scenarios(SupplyComparisonRequest(pipeline_request=request, trucking_distance_km=70.0))
    assert result.pipeline.domain_status == "accepted"
    assert {item.mode for item in result.alternatives} == {"pipeline", "trucking"}
    assert all(item.accounting_basis == "raw_cashflows_levelized_display_only" for item in result.alternatives)
    assert result.trucking.liquefaction_cost_usd_per_tonne > 0
    assert result.trucking.reconditioning_cost_usd_per_tonne > 0


def test_supply_cost_cases_are_monotonic() -> None:
    values = []
    for case in ("low", "base", "high"):
        request = _network_request().model_copy(update={"cost_case": case})
        result = compare_supply_scenarios(SupplyComparisonRequest(pipeline_request=request, trucking_distance_km=70.0))
        values.append((result.pipeline.costs.levelized_delivered_usd_per_tonne, result.trucking.levelized_delivered_usd_per_tonne))
    assert [item[0] for item in values] == sorted(item[0] for item in values)
    assert [item[1] for item in values] == sorted(item[1] for item in values)
