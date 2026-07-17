from __future__ import annotations

import pytest

from jatibarang_ccus.contracts import AnnualEconomicPeriod, FiscalCase
from jatibarang_ccus.infrastructure.economics import evaluate_economic_batch

from .conftest import make_portfolio, make_request


def test_storage_primary_crosscheck_and_threshold_boundary(assumptions, provenance):
    # Stream produced-back = 10, matching the inventory estimate exactly.
    period = AnnualEconomicPeriod(
        year=1,
        gross_gas_produced_std_m3=5_000,
        produced_co2_fraction=1,
        co2_standard_density_kg_m3=2,
        injected_co2_tonnes=100,
        inventory_produced_back_co2_tonnes=10,
        surface_loss_co2_tonnes=1,
    )
    result = evaluate_economic_batch(
        make_request([make_portfolio(provenance, periods=[period])], assumptions, provenance)
    ).results[0]
    assert result.storage.primary_net_stored_co2_tonnes == 89
    assert result.storage.crosscheck_net_stored_co2_tonnes == 89
    assert result.storage.mass_balance_residual_tonnes <= 1e-6
    assert result.storage.mass_balance_passed
    assert not result.storage.low_confidence


def test_storage_divergence_flags_only_above_versioned_threshold(assumptions, provenance):
    at_boundary = AnnualEconomicPeriod(
        year=1,
        injected_co2_tonnes=100,
        inventory_produced_back_co2_tonnes=15,
    )
    above_boundary = at_boundary.model_copy(
        update={"inventory_produced_back_co2_tonnes": 15.0001}
    )
    portfolios = [
        make_portfolio(provenance, portfolio_id="boundary", periods=[at_boundary]),
        make_portfolio(provenance, portfolio_id="above", periods=[above_boundary]),
    ]
    results = evaluate_economic_batch(make_request(portfolios, assumptions, provenance)).results
    boundary = next(item for item in results if item.portfolio_id == "boundary")
    above = next(item for item in results if item.portfolio_id == "above")
    assert not boundary.storage.low_confidence
    assert "produced_back_crosscheck_divergence" in above.confidence_reasons


def test_missing_inventory_is_allowed_only_for_preliminary_and_flagged(assumptions, provenance):
    period = AnnualEconomicPeriod(
        year=1,
        injected_co2_tonnes=100,
        inventory_produced_back_co2_tonnes=None,
    )
    portfolio = make_portfolio(
        provenance,
        periods=[period],
        evaluation_stage="preliminary",
    )
    result = evaluate_economic_batch(make_request([portfolio], assumptions, provenance)).results[0]
    assert result.low_confidence
    assert "inventory_produced_back_unavailable" in result.confidence_reasons


def test_negative_and_zero_storage_receive_no_credit(assumptions, provenance):
    period = AnnualEconomicPeriod(
        year=1,
        injected_co2_tonnes=10,
        inventory_produced_back_co2_tonnes=12,
    )
    result = evaluate_economic_batch(
        make_request([make_portfolio(provenance, periods=[period])], assumptions, provenance)
    ).results[-1]
    assert result.breakdown.carbon_revenue_usd == 0
    assert result.break_even_carbon_price.status == "zero_storage"
    assert "negative_net_storage" in result.confidence_reasons


def test_fiscal_boundaries_and_carbon_tax_switch(assumptions, provenance):
    period = AnnualEconomicPeriod(
        year=1,
        oil_produced_m3=10,
        injected_co2_tonnes=10,
        inventory_produced_back_co2_tonnes=0,
        taxable_emissions_tonnes=5,
    )
    portfolio = make_portfolio(provenance, periods=[period], capex=0, delivered_cost=0)
    cases = [
        FiscalCase(case_id="pre", mode="pre_tax", provenance=provenance),
        FiscalCase(
            case_id="gross100",
            mode="gross_split",
            government_take_fraction=1,
            carbon_revenue_tax_fraction=1,
            carbon_tax_enabled=True,
            carbon_tax_usd_per_tonne=2,
            provenance=provenance,
        ),
        FiscalCase(
            case_id="recovery",
            mode="cost_recovery",
            government_take_fraction=0.4,
            cost_recovery_ceiling_fraction=0.5,
            provenance=provenance,
        ),
    ]
    results = evaluate_economic_batch(
        make_request([portfolio], assumptions, provenance, cases)
    ).results
    gross = next(item for item in results if item.fiscal_case_id == "gross100")
    recovery = next(item for item in results if item.fiscal_case_id == "recovery")
    assert gross.annual_cashflows[1].carbon_tax_usd == 10
    assert gross.npv_usd < 0
    assert recovery.annual_cashflows[1].cost_recovery_usd >= 0


def test_cost_recovery_ceiling_and_carryforward_pool(assumptions, provenance):
    assumptions = assumptions.model_copy(
        update={
            "oil_price_usd_per_bbl": 1.0,
            "lifting_cost_usd_per_bbl": 0.0,
            "gas_price_usd_per_mmbtu": 0.0,
            "mrv_cost_usd_per_tonne": 0.0,
        }
    )
    periods = [
        AnnualEconomicPeriod(
            year=year,
            oil_produced_m3=100 / 6.289810770432105,
            inventory_produced_back_co2_tonnes=0,
        )
        for year in (1, 2)
    ]
    portfolio = make_portfolio(
        provenance,
        project_life=2,
        periods=periods,
        capex=300,
        delivered_cost=0,
        oil_error=0,
        co2_error=0,
    )
    fiscal = FiscalCase(
        case_id="recovery",
        mode="cost_recovery",
        government_take_fraction=0.4,
        cost_recovery_ceiling_fraction=0.5,
        provenance=provenance,
    )
    result = evaluate_economic_batch(
        make_request([portfolio], assumptions, provenance, [fiscal])
    ).results[0]
    assert result.annual_cashflows[1].cost_recovery_usd == pytest.approx(50)
    assert result.annual_cashflows[2].cost_recovery_usd == pytest.approx(50)


def test_pre_tax_mode_carbon_switch_charges_only_explicit_emissions(assumptions, provenance):
    period = AnnualEconomicPeriod(
        year=1,
        oil_produced_m3=1,
        inventory_produced_back_co2_tonnes=0,
        taxable_emissions_tonnes=3,
    )
    portfolio = make_portfolio(provenance, periods=[period], capex=0, delivered_cost=0)
    cases = [
        FiscalCase(case_id="off", mode="pre_tax", provenance=provenance),
        FiscalCase(
            case_id="on",
            mode="pre_tax",
            carbon_tax_enabled=True,
            carbon_tax_usd_per_tonne=5,
            provenance=provenance,
        ),
    ]
    results = evaluate_economic_batch(
        make_request([portfolio], assumptions, provenance, cases)
    ).results
    off = next(item for item in results if item.fiscal_case_id == "off")
    on = next(item for item in results if item.fiscal_case_id == "on")
    assert off.npv_usd - on.npv_usd == pytest.approx(15 / 1.1)
    assert off.pre_tax_npv_usd == pytest.approx(on.pre_tax_npv_usd)


def test_known_irr_fractional_payback_and_break_evens(assumptions, provenance):
    assumptions = assumptions.model_copy(
        update={
            "discount_rate": 0.0,
            "oil_price_usd_per_bbl": 100 / 6.289810770432105,
            "lifting_cost_usd_per_bbl": 0,
            "gas_price_usd_per_mmbtu": 0,
            "mrv_cost_usd_per_tonne": 0,
        }
    )
    periods = [
        AnnualEconomicPeriod(
            year=1,
            oil_produced_m3=0.6,
            inventory_produced_back_co2_tonnes=0,
        ),
        AnnualEconomicPeriod(
            year=2,
            oil_produced_m3=0.6,
            inventory_produced_back_co2_tonnes=0,
        ),
    ]
    portfolio = make_portfolio(
        provenance,
        project_life=2,
        periods=periods,
        capex=100,
        delivered_cost=0,
        oil_error=0,
        co2_error=0,
    )
    result = evaluate_economic_batch(make_request([portfolio], assumptions, provenance)).results[0]
    assert result.irr.status == "computed"
    assert result.irr.value == pytest.approx(0.130662, rel=1e-4)
    assert result.discounted_payback.value == pytest.approx(1 + 40 / 60)
    assert result.break_even_oil_price.status == "computed"


def test_multiple_and_no_root_irr_statuses(assumptions, provenance):
    assumptions = assumptions.model_copy(
        update={
            "oil_price_usd_per_bbl": 1.0,
            "lifting_cost_usd_per_bbl": 0.0,
            "gas_price_usd_per_mmbtu": 0.0,
            "mrv_cost_usd_per_tonne": 0.0,
        }
    )

    def cashflow_portfolio(portfolio_id, year1, year2, year2_opex=0):
        return make_portfolio(
            provenance,
            portfolio_id=portfolio_id,
            project_life=2,
            periods=[
                AnnualEconomicPeriod(
                    year=1,
                    oil_produced_m3=year1 / 6.289810770432105,
                    inventory_produced_back_co2_tonnes=0,
                ),
                AnnualEconomicPeriod(
                    year=2,
                    oil_produced_m3=year2 / 6.289810770432105,
                    inventory_produced_back_co2_tonnes=0,
                ),
            ],
            capex=100,
            opex=[0, year2_opex],
            delivered_cost=0,
            oil_error=0,
            co2_error=0,
        )

    multiple = cashflow_portfolio("multiple", 230, 0, 132)
    no_root = cashflow_portfolio("no_root", 0, 0, 10)
    results = evaluate_economic_batch(
        make_request([multiple, no_root], assumptions, provenance)
    ).results
    assert next(item for item in results if item.portfolio_id == "multiple").irr.status == "multiple_roots"
    assert next(item for item in results if item.portfolio_id == "no_root").irr.status == "no_root"


def test_break_even_already_profitable_and_not_bracketed_statuses(assumptions, provenance):
    profitable = make_portfolio(provenance, portfolio_id="profitable", capex=0, delivered_cost=0)
    unbracketed = make_portfolio(
        provenance,
        portfolio_id="unbracketed",
        capex=1_000_000_000,
        delivered_cost=0,
    )
    results = evaluate_economic_batch(
        make_request([profitable, unbracketed], assumptions, provenance)
    ).results
    profitable_result = next(item for item in results if item.portfolio_id == "profitable")
    unbracketed_result = next(item for item in results if item.portfolio_id == "unbracketed")
    assert profitable_result.break_even_carbon_price.status == "already_profitable"
    assert unbracketed_result.break_even_carbon_price.status == "not_bracketed"
    assert unbracketed_result.break_even_oil_price.status == "not_bracketed"


def test_uncertainty_can_change_ranking_and_order_is_deterministic(assumptions, provenance):
    p1 = make_portfolio(provenance, portfolio_id="A", capex=10_000, oil_error=0.5)
    p2 = make_portfolio(provenance, portfolio_id="B", capex=12_000, oil_error=0.0)
    batch = evaluate_economic_batch(make_request([p1, p2], assumptions, provenance))
    assert batch.scenario_count == 8
    assert [ranking.carbon_price_scenario_id for ranking in batch.rankings] == ["C1", "C2", "C3", "C4"]
    assert any(not ranking.stable_across_bounds for ranking in batch.rankings)
