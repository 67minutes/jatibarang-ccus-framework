from __future__ import annotations

import pytest

from jatibarang_ccus.contracts import (
    AnnualEconomicPeriod,
    AnnualUncertainty,
    CarbonPriceScenario,
    EconomicAssumptions,
    EconomicBatchRequest,
    EconomicProvenance,
    EconomicUncertaintyProfile,
    FacilityEconomicInput,
    FiscalCase,
    FlatDeliveredSupplyCost,
    PortfolioEconomicInput,
)


@pytest.fixture
def provenance() -> list[EconomicProvenance]:
    return [EconomicProvenance(source_class="engineering_assumption", source_id="test")]


@pytest.fixture
def assumptions() -> EconomicAssumptions:
    return EconomicAssumptions(
        version="test-1",
        currency_basis="constant_test_usd",
        discount_rate=0.1,
        oil_price_usd_per_bbl=70.0,
        gas_price_usd_per_mmbtu=5.0,
        gas_heating_value_mmbtu_per_std_m3=0.0353,
        lifting_cost_usd_per_bbl=10.0,
        workover_cost_usd_per_cycle=100.0,
        mrv_cost_usd_per_tonne=1.0,
        certification_haircut=0.9,
        storage_divergence_threshold_fraction_of_injected=0.15,
        carbon_price_max_usd_per_tonne=1_000.0,
        oil_price_max_usd_per_bbl=500.0,
        root_iterations=60,
    )


def make_portfolio(
    provenance: list[EconomicProvenance],
    *,
    portfolio_id: str = "P1",
    project_life: int = 3,
    periods: list[AnnualEconomicPeriod] | None = None,
    capex: float = 1_000.0,
    opex: list[float] | None = None,
    delivered_cost: float = 2.0,
    terminal: float = 0.0,
    oil_error: float = 0.1,
    co2_error: float = 0.1,
    evaluation_stage: str = "final",
) -> PortfolioEconomicInput:
    periods = periods or [
        AnnualEconomicPeriod(
            year=1,
            injection_hours=100,
            production_hours=100,
            oil_produced_m3=100,
            gross_gas_produced_std_m3=1_000,
            produced_co2_fraction=0.2,
            co2_standard_density_kg_m3=2.0,
            injected_co2_tonnes=100,
            inventory_produced_back_co2_tonnes=10,
            surface_loss_co2_tonnes=1,
            workover_count=1,
        )
    ]
    return PortfolioEconomicInput(
        portfolio_id=portfolio_id,
        evaluation_stage=evaluation_stage,
        project_life_years=project_life,
        periods=periods,
        supply=FlatDeliveredSupplyCost(
            delivered_cost_usd_per_tonne=delivered_cost,
            provenance=provenance,
        ),
        facility=FacilityEconomicInput(
            capex_usd=capex,
            annual_opex_usd=opex or [0.0] * project_life,
            provenance=provenance,
        ),
        uncertainty=EconomicUncertaintyProfile(
            periods=[
                AnnualUncertainty(
                    year=period.year,
                    oil_error_fraction=oil_error,
                    gas_error_fraction=oil_error,
                    co2_mass_error_fraction=co2_error,
                )
                for period in periods
            ],
            provenance=provenance,
        ),
        terminal_cashflow_usd=terminal,
        provenance=provenance,
    )


def make_request(
    portfolios: list[PortfolioEconomicInput],
    assumptions: EconomicAssumptions,
    provenance: list[EconomicProvenance],
    fiscal_cases: list[FiscalCase] | None = None,
) -> EconomicBatchRequest:
    return EconomicBatchRequest(
        portfolios=portfolios,
        carbon_prices=[
            CarbonPriceScenario(
                scenario_id=f"C{index}",
                carbon_price_usd_per_tonne=price,
                source_type="economic_assumption",
                provenance=provenance,
            )
            for index, price in enumerate([0.0, 20.0, 40.0, 50.0], start=1)
        ],
        fiscal_cases=fiscal_cases
        or [FiscalCase(case_id="pre", mode="pre_tax", provenance=provenance)],
        assumptions=assumptions,
        provenance=provenance,
    )
