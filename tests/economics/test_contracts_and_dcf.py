from __future__ import annotations

import pytest
from pydantic import ValidationError

from jatibarang_ccus.contracts import (
    AnnualEconomicPeriod,
    FacilityEconomicInput,
    PipelineRawSupplyCost,
    PortfolioEconomicInput,
    TruckingRawSupplyCost,
)
from jatibarang_ccus.infrastructure.economics import M3_TO_BBL, evaluate_economic_batch

from .conftest import make_portfolio, make_request


def test_requires_four_carbon_prices(assumptions, provenance):
    request = make_request([make_portfolio(provenance)], assumptions, provenance).model_dump()
    request["carbon_prices"] = request["carbon_prices"][:3]
    with pytest.raises(ValidationError):
        from jatibarang_ccus.contracts import EconomicBatchRequest

        EconomicBatchRequest.model_validate(request)


def test_rejects_levelized_field_mixed_with_raw_supply(assumptions, provenance):
    portfolio = make_portfolio(provenance).model_dump()
    portfolio["supply"] = {
        "kind": "pipeline_raw",
        "pipeline_capex_usd": 1,
        "booster_capex_usd": 2,
        "annual_maintenance_usd": [0, 0, 0],
        "annual_booster_energy_usd": [0, 0, 0],
        "commodity_supply_usd_per_tonne": 3,
        "levelized_delivered_usd_per_tonne": 99,
        "provenance": [item.model_dump() for item in provenance],
    }
    with pytest.raises(ValidationError):
        PortfolioEconomicInput.model_validate(portfolio)


def test_year_zero_capex_annuity_and_terminal_discounting(assumptions, provenance):
    assumptions = assumptions.model_copy(update={"discount_rate": 0.0, "oil_price_usd_per_bbl": 0.0})
    period = AnnualEconomicPeriod(
        year=1,
        injected_co2_tonnes=0,
        inventory_produced_back_co2_tonnes=0,
    )
    portfolio = make_portfolio(
        provenance,
        periods=[period],
        capex=100,
        opex=[10, 10, 10],
        delivered_cost=0,
        terminal=25,
    )
    result = evaluate_economic_batch(make_request([portfolio], assumptions, provenance)).results[0]
    assert result.npv_usd == pytest.approx(-105.0)
    assert result.annual_cashflows[0].capex_usd == 100
    assert result.annual_cashflows[-1].terminal_cashflow_usd == 25


def test_profile_ends_without_implicit_campaign_repeat(assumptions, provenance):
    portfolio = make_portfolio(provenance, project_life=4, opex=[0, 0, 0, 0])
    result = evaluate_economic_batch(make_request([portfolio], assumptions, provenance)).results[0]
    assert result.annual_cashflows[1].oil_revenue_usd > 0
    assert all(row.oil_revenue_usd == 0 for row in result.annual_cashflows[2:])
    assert all(row.supply_cost_usd == 0 for row in result.annual_cashflows[2:])


def test_oil_and_hydrocarbon_gas_revenue_excludes_co2(assumptions, provenance):
    result = evaluate_economic_batch(
        make_request([make_portfolio(provenance)], assumptions, provenance)
    ).results[0]
    year = result.annual_cashflows[1]
    assert year.oil_revenue_usd == pytest.approx(100 * M3_TO_BBL * 70)
    assert year.gas_revenue_usd == pytest.approx(1_000 * 0.8 * 0.0353 * 5)


def test_accounting_reconciles_to_cent(assumptions, provenance):
    batch = evaluate_economic_batch(make_request([make_portfolio(provenance)], assumptions, provenance))
    assert batch.accounting_verdict == "PASS"
    assert all(item.accounting_reconciliation_usd <= 0.01 for item in batch.results)


def test_pipeline_and_facility_ownership_components_enter_once(assumptions, provenance):
    portfolio = make_portfolio(provenance, capex=200, opex=[20, 0, 0]).model_copy(
        update={
            "supply": PipelineRawSupplyCost(
                pipeline_capex_usd=100,
                booster_capex_usd=50,
                annual_maintenance_usd=[10, 0, 0],
                annual_booster_energy_usd=[5, 0, 0],
                commodity_supply_usd_per_tonne=2,
                provenance=provenance,
            )
        }
    )
    result = evaluate_economic_batch(make_request([portfolio], assumptions, provenance)).results[0]
    assert result.annual_cashflows[0].capex_usd == 350
    assert result.annual_cashflows[1].supply_cost_usd == 200
    assert result.annual_cashflows[1].pipeline_opex_usd == 15
    assert result.annual_cashflows[1].facility_opex_usd == 20
    assert result.breakdown.pipeline_capex_usd == 100
    assert result.breakdown.booster_capex_usd == 50
    assert result.breakdown.facility_capex_usd == 200


def test_trucking_raw_components_are_summed_without_levelized_cost(assumptions, provenance):
    portfolio = make_portfolio(provenance, capex=0).model_copy(
        update={
            "supply": TruckingRawSupplyCost(
                loading_usd_per_tonne=1,
                liquefaction_usd_per_tonne=2,
                reconditioning_usd_per_tonne=3,
                distance_transport_usd_per_tonne=4,
                commodity_supply_usd_per_tonne=5,
                provenance=provenance,
            ),
            "facility": FacilityEconomicInput(
                capex_usd=0,
                annual_opex_usd=[0, 0, 0],
                provenance=provenance,
            ),
        }
    )
    result = evaluate_economic_batch(make_request([portfolio], assumptions, provenance)).results[0]
    assert result.annual_cashflows[1].supply_cost_usd == 1_500


def test_certification_mrv_lifting_and_workover_components(assumptions, provenance):
    result = evaluate_economic_batch(
        make_request([make_portfolio(provenance)], assumptions, provenance)
    ).results[1]
    assert result.annual_cashflows[1].carbon_revenue_usd == pytest.approx(89 * 0.9 * 20)
    assert result.annual_cashflows[1].lifting_cost_usd == pytest.approx(100 * M3_TO_BBL * 10)
    assert result.annual_cashflows[1].mrv_cost_usd == 89
    assert result.annual_cashflows[1].workover_cost_usd == 100


def test_batch_and_single_portfolio_evaluation_have_parity(assumptions, provenance):
    portfolios = [
        make_portfolio(provenance, portfolio_id="P1"),
        make_portfolio(provenance, portfolio_id="P2", capex=2_000),
    ]
    batch_request = make_request(portfolios, assumptions, provenance)
    batch = evaluate_economic_batch(batch_request)
    for portfolio in portfolios:
        scalar = evaluate_economic_batch(
            batch_request.model_copy(update={"portfolios": [portfolio]})
        )
        batch_values = [
            (item.carbon_price_scenario_id, item.fiscal_case_id, item.npv_usd)
            for item in batch.results
            if item.portfolio_id == portfolio.portfolio_id
        ]
        scalar_values = [
            (item.carbon_price_scenario_id, item.fiscal_case_id, item.npv_usd)
            for item in scalar.results
        ]
        assert batch_values == scalar_values
