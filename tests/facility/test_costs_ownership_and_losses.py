from __future__ import annotations

import pytest

from jatibarang_ccus.infrastructure.facility import evaluate_facility_portfolio

from .helpers import COST_BASIS, DESIGN_BASIS, request, well_load


def evaluate(*wells, cost_case: str = "base"):
    return evaluate_facility_portfolio(
        request(*wells, cost_case=cost_case),
        DESIGN_BASIS,
        COST_BASIS,
    )


def test_cost_cases_are_monotonic_and_every_item_has_a_basis() -> None:
    low = evaluate(well_load(), cost_case="low")
    base = evaluate(well_load(), cost_case="base")
    high = evaluate(well_load(), cost_case="high")
    assert low.total_capex_usd < base.total_capex_usd < high.total_capex_usd
    assert low.total_annual_opex_usd < base.total_annual_opex_usd < high.total_annual_opex_usd
    assert all(item.provenance for item in base.well_results[0].equipment)


def test_equipment_reconciles_exactly_to_wells_and_portfolio() -> None:
    result = evaluate(well_load("W01"), well_load("W02"))
    assert result.total_capex_usd == pytest.approx(sum(well.capex_usd for well in result.well_results))
    assert result.total_annual_opex_usd == pytest.approx(
        sum(well.annual_opex_usd for well in result.well_results)
    )
    for well in result.well_results:
        assert well.capex_usd == pytest.approx(sum(item.capex_usd for item in well.equipment))
        assert well.annual_opex_usd == pytest.approx(sum(item.annual_opex_usd for item in well.equipment))


def test_identical_dedicated_skids_are_costed_once_per_selected_well() -> None:
    one = evaluate(well_load("W01"))
    two = evaluate(well_load("W01"), well_load("W02"))
    assert two.total_capex_usd == pytest.approx(2.0 * one.total_capex_usd)
    assert two.total_annual_opex_usd == pytest.approx(2.0 * one.total_annual_opex_usd)
    for well in two.well_results:
        assert all(item.candidate_id == well.candidate_id for item in well.equipment)
        assert all(item.ownership_scope == "dedicated_well_pad" for item in well.equipment)


def test_surface_ledger_keeps_produced_back_co2_out_of_the_storage_debit() -> None:
    well = evaluate(well_load()).well_results[0]
    ledger = well.loss_ledger
    fresh_fugitives = ledger.fugitive_tonnes_per_year - (
        ledger.recycle_co2_handled_tonnes_per_year * 0.0005
    )
    expected_debit = ledger.conditioning_purge_tonnes_per_year + fresh_fugitives
    assert ledger.net_storage_debit_tonnes_per_year == pytest.approx(expected_debit)
    assert ledger.produced_back_co2_tonnes_per_year > ledger.net_storage_debit_tonnes_per_year
    assert ledger.atmospheric_emissions_tonnes_per_year > ledger.net_storage_debit_tonnes_per_year
    assert ledger.reconciliation_residual_tonnes_per_year <= 1e-9


def test_disabled_recycle_reports_zero_recycle_handling_without_erasing_produced_back() -> None:
    ledger = evaluate(
        well_load(recycle_enabled=False, recycle_recovery_fraction=0.0)
    ).well_results[0].loss_ledger
    assert ledger.recycle_co2_handled_tonnes_per_year == 0.0
    assert ledger.produced_back_co2_tonnes_per_year > 0.0
    assert ledger.recycle_non_recovery_tonnes_per_year == pytest.approx(
        ledger.produced_back_co2_tonnes_per_year
    )
