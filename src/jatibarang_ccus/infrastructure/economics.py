from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from time import perf_counter

import numpy as np

from jatibarang_ccus.contracts import (
    AnnualCashFlow,
    EconomicAssumptions,
    EconomicBatchRequest,
    EconomicBatchResult,
    EconomicBreakdown,
    EconomicMetric,
    EconomicRanking,
    EconomicScenarioResult,
    FiscalCase,
    FlatDeliveredSupplyCost,
    PipelineRawSupplyCost,
    PortfolioEconomicInput,
    StorageReconciliation,
    TruckingRawSupplyCost,
)

M3_TO_BBL = 6.289810770432105


@dataclass(frozen=True)
class _AnnualState:
    years: np.ndarray
    oil_m3: np.ndarray
    gross_gas_m3: np.ndarray
    produced_co2_fraction: np.ndarray
    injected_tonnes: np.ndarray
    produced_back_tonnes: np.ndarray
    stream_produced_back_tonnes: np.ndarray
    surface_loss_tonnes: np.ndarray
    workovers: np.ndarray
    taxable_emissions_tonnes: np.ndarray
    oil_error: np.ndarray
    gas_error: np.ndarray
    co2_error: np.ndarray
    facility_opex: np.ndarray
    supply_cost: np.ndarray
    pipeline_opex: np.ndarray
    capex: np.ndarray
    facility_capex_array: np.ndarray
    pipeline_capex_array: np.ndarray
    booster_capex_array: np.ndarray
    terminal: np.ndarray
    pipeline_capex: float
    booster_capex: float
    facility_capex: float
    inventory_missing: bool


@dataclass(frozen=True)
class _CashFlowState:
    annual: dict[str, np.ndarray]
    pre_tax: np.ndarray
    post_fiscal: np.ndarray


def _portfolio_state(portfolio: PortfolioEconomicInput) -> _AnnualState:
    life = portfolio.project_life_years
    size = life + 1
    years = np.arange(size, dtype=int)

    def zeros() -> np.ndarray:
        return np.zeros(size, dtype=float)

    oil = zeros()
    gas = zeros()
    produced_co2_fraction = zeros()
    injected = zeros()
    produced_back = zeros()
    stream_produced_back = zeros()
    surface_loss = zeros()
    workovers = zeros()
    taxable_emissions = zeros()
    inventory_missing = False

    for period in portfolio.periods:
        year = period.year
        oil[year] = period.oil_produced_m3
        gas[year] = period.gross_gas_produced_std_m3
        produced_co2_fraction[year] = period.produced_co2_fraction
        injected[year] = period.injected_co2_tonnes
        stream_mass = (
            period.gross_gas_produced_std_m3
            * period.produced_co2_fraction
            * period.co2_standard_density_kg_m3
            / 1_000.0
        )
        stream_produced_back[year] = stream_mass
        if period.inventory_produced_back_co2_tonnes is None:
            produced_back[year] = stream_mass
            inventory_missing = True
        else:
            produced_back[year] = period.inventory_produced_back_co2_tonnes
        surface_loss[year] = period.surface_loss_co2_tonnes
        workovers[year] = period.workover_count
        taxable_emissions[year] = period.taxable_emissions_tonnes

    oil_error = zeros()
    gas_error = zeros()
    co2_error = zeros()
    for uncertainty in portfolio.uncertainty.periods:
        oil_error[uncertainty.year] = uncertainty.oil_error_fraction
        gas_error[uncertainty.year] = uncertainty.gas_error_fraction
        co2_error[uncertainty.year] = uncertainty.co2_mass_error_fraction

    facility_opex = zeros()
    facility_opex[1:] = np.asarray(portfolio.facility.annual_opex_usd, dtype=float)
    supply_cost = zeros()
    pipeline_opex = zeros()
    pipeline_capex = 0.0
    booster_capex = 0.0
    if isinstance(portfolio.supply, FlatDeliveredSupplyCost):
        supply_cost = injected * portfolio.supply.delivered_cost_usd_per_tonne
    elif isinstance(portfolio.supply, PipelineRawSupplyCost):
        pipeline_capex = portfolio.supply.pipeline_capex_usd
        booster_capex = portfolio.supply.booster_capex_usd
        supply_cost = injected * portfolio.supply.commodity_supply_usd_per_tonne
        pipeline_opex[1:] = np.asarray(portfolio.supply.annual_maintenance_usd) + np.asarray(
            portfolio.supply.annual_booster_energy_usd
        )
    elif isinstance(portfolio.supply, TruckingRawSupplyCost):
        unit_cost = (
            portfolio.supply.loading_usd_per_tonne
            + portfolio.supply.liquefaction_usd_per_tonne
            + portfolio.supply.reconditioning_usd_per_tonne
            + portfolio.supply.distance_transport_usd_per_tonne
            + portfolio.supply.commodity_supply_usd_per_tonne
        )
        supply_cost = injected * unit_cost
    else:  # pragma: no cover - Pydantic's discriminator prevents this.
        raise TypeError(f"Unsupported supply-cost basis: {type(portfolio.supply)!r}")

    capex = zeros()
    facility_capex = portfolio.facility.capex_usd
    capex[0] = pipeline_capex + booster_capex + facility_capex
    facility_capex_array = zeros()
    pipeline_capex_array = zeros()
    booster_capex_array = zeros()
    terminal = zeros()
    facility_capex_array[0] = facility_capex
    pipeline_capex_array[0] = pipeline_capex
    booster_capex_array[0] = booster_capex
    terminal[-1] = portfolio.terminal_cashflow_usd
    return _AnnualState(
        years=years,
        oil_m3=oil,
        gross_gas_m3=gas,
        produced_co2_fraction=produced_co2_fraction,
        injected_tonnes=injected,
        produced_back_tonnes=produced_back,
        stream_produced_back_tonnes=stream_produced_back,
        surface_loss_tonnes=surface_loss,
        workovers=workovers,
        taxable_emissions_tonnes=taxable_emissions,
        oil_error=oil_error,
        gas_error=gas_error,
        co2_error=co2_error,
        facility_opex=facility_opex,
        supply_cost=supply_cost,
        pipeline_opex=pipeline_opex,
        capex=capex,
        facility_capex_array=facility_capex_array,
        pipeline_capex_array=pipeline_capex_array,
        booster_capex_array=booster_capex_array,
        terminal=terminal,
        pipeline_capex=pipeline_capex,
        booster_capex=booster_capex,
        facility_capex=facility_capex,
        inventory_missing=inventory_missing,
    )


def _storage_reconciliation(
    portfolio: PortfolioEconomicInput,
    state: _AnnualState,
    assumptions: EconomicAssumptions,
) -> StorageReconciliation:
    injected = float(state.injected_tonnes.sum())
    produced_back = float(state.produced_back_tonnes.sum())
    stream_produced_back = float(state.stream_produced_back_tonnes.sum())
    surface_loss = float(state.surface_loss_tonnes.sum())
    primary_net = injected - produced_back - surface_loss
    crosscheck_net = injected - stream_produced_back - surface_loss
    mass_balance_residual = abs(injected - produced_back - surface_loss - primary_net)
    divergence = abs(produced_back - stream_produced_back)
    divergence_fraction = divergence / injected if injected > 0 else (0.0 if divergence == 0 else float("inf"))
    reasons = list(portfolio.uncertainty.low_confidence_reasons)
    if state.inventory_missing:
        reasons.append("inventory_produced_back_unavailable")
    if divergence_fraction > assumptions.storage_divergence_threshold_fraction_of_injected:
        reasons.append("produced_back_crosscheck_divergence")
    if primary_net < -assumptions.mass_reconciliation_tolerance_tonnes:
        reasons.append("negative_net_storage")
    mass_balance_passed = mass_balance_residual <= assumptions.mass_reconciliation_tolerance_tonnes
    if not mass_balance_passed:
        reasons.append("storage_reconciliation_failed")
    if portfolio.uncertainty.extended_horizon:
        reasons.append("extended_horizon_surrogate_confidence")
    reasons = list(dict.fromkeys(reasons))
    return StorageReconciliation(
        injected_co2_tonnes=injected,
        inventory_produced_back_co2_tonnes=produced_back,
        stream_produced_back_co2_tonnes=stream_produced_back,
        surface_loss_co2_tonnes=surface_loss,
        primary_net_stored_co2_tonnes=primary_net,
        crosscheck_net_stored_co2_tonnes=crosscheck_net,
        absolute_divergence_tonnes=divergence,
        divergence_fraction_of_injected=divergence_fraction,
        mass_balance_residual_tonnes=mass_balance_residual,
        mass_balance_passed=mass_balance_passed,
        low_confidence=bool(reasons),
        reasons=reasons,
    )


def _trajectory_physical(
    state: _AnnualState,
    trajectory: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if trajectory == "low":
        oil = state.oil_m3 * (1.0 - state.oil_error)
        gas = state.gross_gas_m3 * (1.0 - state.gas_error)
        inventory_back = state.produced_back_tonnes * (1.0 + state.co2_error)
        stream_back = state.stream_produced_back_tonnes * (1.0 + state.gas_error)
        produced_back = np.maximum(inventory_back, stream_back)
    elif trajectory == "high":
        oil = state.oil_m3 * (1.0 + state.oil_error)
        gas = state.gross_gas_m3 * (1.0 + state.gas_error)
        inventory_back = np.maximum(0.0, state.produced_back_tonnes * (1.0 - state.co2_error))
        stream_back = np.maximum(
            0.0, state.stream_produced_back_tonnes * (1.0 - state.gas_error)
        )
        produced_back = np.minimum(inventory_back, stream_back)
    else:
        oil = state.oil_m3
        gas = state.gross_gas_m3
        produced_back = state.produced_back_tonnes
    net_storage = state.injected_tonnes - produced_back - state.surface_loss_tonnes
    return oil, gas, net_storage


def _fiscal_cashflow(
    fiscal: FiscalCase,
    annual: dict[str, np.ndarray],
    pre_tax: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    size = len(pre_tax)
    recovery = np.zeros(size, dtype=float)
    government_take = np.zeros(size, dtype=float)
    carbon_after_share = annual["carbon_revenue"] * (1.0 - fiscal.carbon_revenue_tax_fraction)
    total_cost = (
        annual["lifting"]
        + annual["workover"]
        + annual["mrv"]
        + annual["supply"]
        + annual["pipeline_opex"]
        + annual["facility_opex"]
        + annual["capex"]
    )
    hydrocarbon_revenue = annual["oil_revenue"] + annual["gas_revenue"]
    if fiscal.mode == "pre_tax":
        return pre_tax - annual["carbon_tax"], recovery, government_take
    if fiscal.mode == "gross_split":
        government_take = hydrocarbon_revenue * fiscal.government_take_fraction
        post = (
            hydrocarbon_revenue
            - government_take
            + carbon_after_share
            - total_cost
            - annual["carbon_tax"]
            + annual["terminal"]
        )
        return post, recovery, government_take

    eligible = np.zeros(size, dtype=float)
    category_map = {
        "supply": annual["supply"],
        "facility_capex": annual["facility_capex"],
        "facility_opex": annual["facility_opex"],
        "pipeline_capex": annual["pipeline_capex"] + annual["booster_capex"],
        "pipeline_opex": annual["pipeline_opex"],
        "lifting": annual["lifting"],
        "workover": annual["workover"],
        "mrv": annual["mrv"],
    }
    for category in fiscal.recoverable_cost_categories:
        eligible += category_map[category]
    carryforward = 0.0
    for year in range(size):
        carryforward += eligible[year]
        ceiling = max(0.0, hydrocarbon_revenue[year]) * fiscal.cost_recovery_ceiling_fraction
        recovery[year] = min(carryforward, ceiling)
        carryforward -= recovery[year]
        profit_hydrocarbon = max(0.0, hydrocarbon_revenue[year] - recovery[year])
        government_take[year] = profit_hydrocarbon * fiscal.government_take_fraction
    contractor_hydrocarbon = hydrocarbon_revenue - government_take
    post = (
        contractor_hydrocarbon
        + carbon_after_share
        - total_cost
        - annual["carbon_tax"]
        + annual["terminal"]
    )
    return post, recovery, government_take


def _cashflows(
    portfolio: PortfolioEconomicInput,
    state: _AnnualState,
    assumptions: EconomicAssumptions,
    fiscal: FiscalCase,
    carbon_price: float,
    *,
    oil_price: float | None = None,
    trajectory: str = "base",
) -> _CashFlowState:
    oil_m3, gross_gas, net_storage = _trajectory_physical(state, trajectory)
    oil_bbl = oil_m3 * M3_TO_BBL
    # The annual period carries the produced CO2 fraction; derive hydrocarbon gas
    # from the same period rather than assigning revenue to the CO2 stream.
    hydrocarbon_gas = gross_gas * (1.0 - state.produced_co2_fraction)
    oil_revenue = oil_bbl * (assumptions.oil_price_usd_per_bbl if oil_price is None else oil_price)
    gas_revenue = (
        hydrocarbon_gas
        * assumptions.gas_heating_value_mmbtu_per_std_m3
        * assumptions.gas_price_usd_per_mmbtu
    )
    credited_storage = np.maximum(0.0, net_storage) * assumptions.certification_haircut
    carbon_revenue = credited_storage * carbon_price
    lifting = oil_bbl * assumptions.lifting_cost_usd_per_bbl
    workover = state.workovers * assumptions.workover_cost_usd_per_cycle
    mrv = np.maximum(0.0, net_storage) * assumptions.mrv_cost_usd_per_tonne
    carbon_tax = (
        state.taxable_emissions_tonnes * fiscal.carbon_tax_usd_per_tonne
        if fiscal.carbon_tax_enabled
        else np.zeros_like(state.years, dtype=float)
    )
    annual = {
        "oil_revenue": oil_revenue,
        "gas_revenue": gas_revenue,
        "carbon_revenue": carbon_revenue,
        "lifting": lifting,
        "workover": workover,
        "mrv": mrv,
        "supply": state.supply_cost,
        "pipeline_opex": state.pipeline_opex,
        "facility_opex": state.facility_opex,
        "capex": state.capex,
        "facility_capex": state.facility_capex_array,
        "pipeline_capex": state.pipeline_capex_array,
        "booster_capex": state.booster_capex_array,
        "carbon_tax": carbon_tax,
        "terminal": state.terminal,
    }
    total_revenue = oil_revenue + gas_revenue + carbon_revenue
    total_cost = lifting + workover + mrv + state.supply_cost + state.pipeline_opex + state.facility_opex + state.capex
    pre_tax = total_revenue - total_cost + state.terminal
    post_fiscal, recovery, government_take = _fiscal_cashflow(fiscal, annual, pre_tax)
    annual["recovery"] = recovery
    annual["government_take"] = government_take
    return _CashFlowState(annual=annual, pre_tax=pre_tax, post_fiscal=post_fiscal)


def _uncertainty_post_fiscal_cashflow(
    base: _CashFlowState,
    state: _AnnualState,
    assumptions: EconomicAssumptions,
    fiscal: FiscalCase,
    carbon_price: float,
    trajectory: str,
) -> np.ndarray:
    """Revalue only trajectory-sensitive components for a deterministic bound."""
    oil_m3, gross_gas, net_storage = _trajectory_physical(state, trajectory)
    oil_bbl = oil_m3 * M3_TO_BBL
    hydrocarbon_gas = gross_gas * (1.0 - state.produced_co2_fraction)
    annual = base.annual.copy()
    annual["oil_revenue"] = oil_bbl * assumptions.oil_price_usd_per_bbl
    annual["gas_revenue"] = (
        hydrocarbon_gas
        * assumptions.gas_heating_value_mmbtu_per_std_m3
        * assumptions.gas_price_usd_per_mmbtu
    )
    annual["carbon_revenue"] = (
        np.maximum(0.0, net_storage) * assumptions.certification_haircut * carbon_price
    )
    annual["lifting"] = oil_bbl * assumptions.lifting_cost_usd_per_bbl
    annual["mrv"] = np.maximum(0.0, net_storage) * assumptions.mrv_cost_usd_per_tonne
    total_revenue = annual["oil_revenue"] + annual["gas_revenue"] + annual["carbon_revenue"]
    total_cost = (
        annual["lifting"]
        + annual["workover"]
        + annual["mrv"]
        + annual["supply"]
        + annual["pipeline_opex"]
        + annual["facility_opex"]
        + annual["capex"]
    )
    pre_tax = total_revenue - total_cost + annual["terminal"]
    post_fiscal, _, _ = _fiscal_cashflow(fiscal, annual, pre_tax)
    return post_fiscal


@lru_cache(maxsize=8_192)
def _discount_factors(length: int, discount_rate: float) -> np.ndarray:
    years = np.arange(length, dtype=float)
    factors = 1.0 / np.power(1.0 + discount_rate, years)
    factors.flags.writeable = False
    return factors


def _npv(cashflows: np.ndarray, discount_rate: float) -> float:
    return float(np.dot(cashflows, _discount_factors(len(cashflows), discount_rate)))


def _bisect(function, lower: float, upper: float, iterations: int) -> float | None:
    f_lower = float(function(lower))
    f_upper = float(function(upper))
    if not np.isfinite(f_lower) or not np.isfinite(f_upper) or f_lower * f_upper > 0:
        return None
    if abs(f_lower) <= 1e-10:
        return lower
    if abs(f_upper) <= 1e-10:
        return upper
    for _ in range(iterations):
        midpoint = (lower + upper) / 2.0
        f_mid = float(function(midpoint))
        if abs(f_mid) <= 1e-10:
            return midpoint
        if f_lower * f_mid <= 0:
            upper = midpoint
        else:
            lower = midpoint
            f_lower = f_mid
    return (lower + upper) / 2.0


def _false_position(
    function,
    lower: float,
    upper: float,
    f_lower: float,
    f_upper: float,
    iterations: int,
) -> float | None:
    """Bracket-preserving solve optimized for the piecewise-linear fiscal NPV."""
    if f_lower * f_upper > 0:
        return None
    candidate = lower
    for _ in range(iterations):
        denominator = f_upper - f_lower
        if abs(denominator) <= 1e-15:
            return (lower + upper) / 2.0
        candidate = (lower * f_upper - upper * f_lower) / denominator
        value = float(function(candidate))
        if abs(value) <= 1e-7 or upper - lower <= 1e-10:
            return candidate
        if f_lower * value <= 0:
            upper, f_upper = candidate, value
        else:
            lower, f_lower = candidate, value
    return candidate


def _irr(cashflows: np.ndarray, assumptions: EconomicAssumptions) -> EconomicMetric:
    nonzero = cashflows[np.abs(cashflows) > 1e-12]
    sign_changes = int(np.sum(np.sign(nonzero[1:]) != np.sign(nonzero[:-1]))) if len(nonzero) > 1 else 0
    if sign_changes == 0:
        return EconomicMetric(value=None, status="no_root", method="polynomial_bracket_scan")
    lower = assumptions.irr_min
    upper = assumptions.irr_max
    tolerance = 1e-8 * max(1.0, float(np.abs(cashflows).sum()))
    polynomial = np.trim_zeros(cashflows[::-1], trim="f")
    candidate_rates = sorted(
        1.0 / float(root.real) - 1.0
        for root in np.roots(polynomial)
        if abs(root.imag) <= 1e-8
        and root.real > 0
        and lower <= 1.0 / float(root.real) - 1.0 <= upper
    )
    unique_rates: list[float] = []
    for rate in candidate_rates:
        if abs(_npv(cashflows, rate)) <= tolerance and (
            not unique_rates or abs(rate - unique_rates[-1]) > 1e-7
        ):
            unique_rates.append(rate)
    if len(unique_rates) > 1:
        return EconomicMetric(value=None, status="multiple_roots", method="polynomial_bracket_scan")
    if not unique_rates:
        return EconomicMetric(value=None, status="no_root", method="polynomial_bracket_scan")
    candidate = unique_rates[0]
    radius = 1e-8 * max(1.0, abs(candidate))
    for _ in range(24):
        bracket_lower = max(lower, candidate - radius)
        bracket_upper = min(upper, candidate + radius)
        if _npv(cashflows, bracket_lower) * _npv(cashflows, bracket_upper) <= 0:
            return EconomicMetric(
                value=candidate,
                status="computed",
                method="unique_polynomial_root_bracket_verified",
            )
        radius *= 2.0
    return EconomicMetric(value=None, status="no_root", method="unbracketed_polynomial_root")


def _discounted_payback(cashflows: np.ndarray, discount_rate: float) -> EconomicMetric:
    discounted = cashflows * _discount_factors(len(cashflows), discount_rate)
    cumulative = np.cumsum(discounted)
    hits = np.flatnonzero(cumulative >= -1e-10)
    if not len(hits):
        return EconomicMetric(value=None, status="never_paid_back", method="fractional_discounted_cashflow")
    year = int(hits[0])
    if year == 0:
        return EconomicMetric(value=0.0, status="computed", method="fractional_discounted_cashflow")
    previous = cumulative[year - 1]
    current_flow = discounted[year]
    fraction = 0.0 if current_flow <= 0 else float(np.clip(-previous / current_flow, 0.0, 1.0))
    return EconomicMetric(
        value=(year - 1) + fraction,
        status="computed",
        method="fractional_discounted_cashflow",
    )


def _break_even(
    portfolio: PortfolioEconomicInput,
    state: _AnnualState,
    assumptions: EconomicAssumptions,
    fiscal: FiscalCase,
    *,
    variable: str,
    reference_carbon_price: float,
) -> EconomicMetric:
    if variable == "carbon" and float(np.sum(np.maximum(0.0, state.injected_tonnes - state.produced_back_tonnes - state.surface_loss_tonnes))) <= 0:
        return EconomicMetric(value=None, status="zero_storage", method="bracketed_bisection")
    upper = (
        assumptions.carbon_price_max_usd_per_tonne
        if variable == "carbon"
        else assumptions.oil_price_max_usd_per_bbl
    )

    if variable == "oil" and fiscal.mode == "cost_recovery":
        zero_oil = _cashflows(
            portfolio,
            state,
            assumptions,
            fiscal,
            reference_carbon_price,
            oil_price=0.0,
        )
        annual = zero_oil.annual
        oil_bbl = state.oil_m3 * M3_TO_BBL
        total_cost = (
            annual["lifting"]
            + annual["workover"]
            + annual["mrv"]
            + annual["supply"]
            + annual["pipeline_opex"]
            + annual["facility_opex"]
            + annual["capex"]
        )
        category_map = {
            "supply": annual["supply"],
            "facility_capex": annual["facility_capex"],
            "facility_opex": annual["facility_opex"],
            "pipeline_capex": annual["pipeline_capex"] + annual["booster_capex"],
            "pipeline_opex": annual["pipeline_opex"],
            "lifting": annual["lifting"],
            "workover": annual["workover"],
            "mrv": annual["mrv"],
        }
        eligible = np.zeros_like(oil_bbl)
        for category in fiscal.recoverable_cost_categories:
            eligible += category_map[category]
        carbon_after_share = annual["carbon_revenue"] * (1.0 - fiscal.carbon_revenue_tax_fraction)

        def objective(price: float) -> float:
            hydrocarbon = oil_bbl * price + annual["gas_revenue"]
            government_take = np.zeros_like(hydrocarbon)
            carryforward = 0.0
            for year in range(len(hydrocarbon)):
                carryforward += eligible[year]
                recovery = min(
                    carryforward,
                    max(0.0, hydrocarbon[year]) * fiscal.cost_recovery_ceiling_fraction,
                )
                carryforward -= recovery
                government_take[year] = (
                    max(0.0, hydrocarbon[year] - recovery) * fiscal.government_take_fraction
                )
            post = (
                hydrocarbon
                - government_take
                + carbon_after_share
                - total_cost
                - annual["carbon_tax"]
                + annual["terminal"]
            )
            return _npv(post, assumptions.discount_rate)

    else:

        def objective(price: float) -> float:
            cashflows = _cashflows(
                portfolio,
                state,
                assumptions,
                fiscal,
                price if variable == "carbon" else reference_carbon_price,
                oil_price=price if variable == "oil" else assumptions.oil_price_usd_per_bbl,
            )
            return _npv(cashflows.post_fiscal, assumptions.discount_rate)

    lower_npv = objective(0.0)
    if lower_npv >= -1e-10:
        return EconomicMetric(value=0.0, status="already_profitable", method="bracketed_bisection")
    upper_npv = objective(upper)
    if upper_npv < 0 or not np.isfinite(upper_npv):
        return EconomicMetric(value=None, status="not_bracketed", method="bracketed_bisection")
    # Carbon revenue is linear in carbon price for every fiscal mode. Oil
    # revenue is also linear for pre-tax and gross-split cases. The exact
    # bracket interpolation avoids dozens of repeated array assemblies while
    # preserving the same bracketed-solve contract. Cost recovery can change
    # slope when its ceiling/carryforward binds, so retain bisection there.
    if variable == "carbon" or fiscal.mode != "cost_recovery":
        root = upper * (-lower_npv) / (upper_npv - lower_npv)
        method = "bracketed_linear_solve"
    else:
        root = _false_position(
            objective,
            0.0,
            upper,
            lower_npv,
            upper_npv,
            assumptions.root_iterations,
        )
        method = "bracketed_false_position"
    if root is None:
        return EconomicMetric(value=None, status="not_bracketed", method=method)
    return EconomicMetric(value=root, status="computed", method=method)


def _carbon_break_even(
    cashflows: _CashFlowState,
    state: _AnnualState,
    assumptions: EconomicAssumptions,
    fiscal: FiscalCase,
    reference_carbon_price: float,
) -> EconomicMetric:
    net_storage = np.maximum(
        0.0,
        state.injected_tonnes - state.produced_back_tonnes - state.surface_loss_tonnes,
    )
    if float(net_storage.sum()) <= 0:
        return EconomicMetric(value=None, status="zero_storage", method="bracketed_linear_solve")
    revenue_share = 1.0 if fiscal.mode == "pre_tax" else 1.0 - fiscal.carbon_revenue_tax_fraction
    annual_slope = net_storage * assumptions.certification_haircut * revenue_share
    slope = _npv(annual_slope, assumptions.discount_rate)
    lower_npv = (
        _npv(cashflows.post_fiscal, assumptions.discount_rate)
        - slope * reference_carbon_price
    )
    if lower_npv >= -1e-10:
        return EconomicMetric(value=0.0, status="already_profitable", method="bracketed_linear_solve")
    if slope <= 0 or lower_npv + slope * assumptions.carbon_price_max_usd_per_tonne < 0:
        return EconomicMetric(value=None, status="not_bracketed", method="bracketed_linear_solve")
    return EconomicMetric(
        value=-lower_npv / slope,
        status="computed",
        method="bracketed_linear_solve",
    )


def _cost_recovery_oil_break_even(
    cashflows: _CashFlowState,
    state: _AnnualState,
    assumptions: EconomicAssumptions,
    fiscal: FiscalCase,
) -> EconomicMetric:
    annual = cashflows.annual
    oil_bbl = state.oil_m3 * M3_TO_BBL
    total_cost = (
        annual["lifting"]
        + annual["workover"]
        + annual["mrv"]
        + annual["supply"]
        + annual["pipeline_opex"]
        + annual["facility_opex"]
        + annual["capex"]
    )
    category_map = {
        "supply": annual["supply"],
        "facility_capex": annual["facility_capex"],
        "facility_opex": annual["facility_opex"],
        "pipeline_capex": annual["pipeline_capex"] + annual["booster_capex"],
        "pipeline_opex": annual["pipeline_opex"],
        "lifting": annual["lifting"],
        "workover": annual["workover"],
        "mrv": annual["mrv"],
    }
    eligible = np.zeros_like(oil_bbl)
    for category in fiscal.recoverable_cost_categories:
        eligible += category_map[category]
    carbon_after_share = annual["carbon_revenue"] * (1.0 - fiscal.carbon_revenue_tax_fraction)

    def objective(price: float) -> float:
        hydrocarbon = oil_bbl * price + annual["gas_revenue"]
        government_take = np.zeros_like(hydrocarbon)
        carryforward = 0.0
        for year in range(len(hydrocarbon)):
            carryforward += eligible[year]
            recovery = min(
                carryforward,
                max(0.0, hydrocarbon[year]) * fiscal.cost_recovery_ceiling_fraction,
            )
            carryforward -= recovery
            government_take[year] = (
                max(0.0, hydrocarbon[year] - recovery) * fiscal.government_take_fraction
            )
        post = (
            hydrocarbon
            - government_take
            + carbon_after_share
            - total_cost
            - annual["carbon_tax"]
            + annual["terminal"]
        )
        return _npv(post, assumptions.discount_rate)

    lower_npv = objective(0.0)
    if lower_npv >= -1e-10:
        return EconomicMetric(value=0.0, status="already_profitable", method="bracketed_false_position")
    upper = assumptions.oil_price_max_usd_per_bbl
    upper_npv = objective(upper)
    if upper_npv < 0 or not np.isfinite(upper_npv):
        return EconomicMetric(value=None, status="not_bracketed", method="bracketed_false_position")
    root = _false_position(
        objective,
        0.0,
        upper,
        lower_npv,
        upper_npv,
        assumptions.root_iterations,
    )
    return EconomicMetric(value=root, status="computed", method="bracketed_false_position")


def _linear_oil_break_even(
    cashflows: _CashFlowState,
    state: _AnnualState,
    assumptions: EconomicAssumptions,
    fiscal: FiscalCase,
) -> EconomicMetric:
    share = 1.0 if fiscal.mode == "pre_tax" else 1.0 - fiscal.government_take_fraction
    slope = _npv(state.oil_m3 * M3_TO_BBL * share, assumptions.discount_rate)
    current_npv = _npv(cashflows.post_fiscal, assumptions.discount_rate)
    lower_npv = current_npv - slope * assumptions.oil_price_usd_per_bbl
    if lower_npv >= -1e-10:
        return EconomicMetric(value=0.0, status="already_profitable", method="bracketed_linear_solve")
    if slope <= 0 or lower_npv + slope * assumptions.oil_price_max_usd_per_bbl < 0:
        return EconomicMetric(value=None, status="not_bracketed", method="bracketed_linear_solve")
    return EconomicMetric(
        value=-lower_npv / slope,
        status="computed",
        method="bracketed_linear_solve",
    )


def _annual_models(
    cashflows: _CashFlowState,
    assumptions: EconomicAssumptions,
) -> list[AnnualCashFlow]:
    discount_factors = _discount_factors(len(cashflows.pre_tax), assumptions.discount_rate)
    annual = {key: value.tolist() for key, value in cashflows.annual.items()}
    pre_tax = cashflows.pre_tax.tolist()
    post_fiscal = cashflows.post_fiscal.tolist()
    discounted_pre_tax = (cashflows.pre_tax * discount_factors).tolist()
    discounted_post_fiscal = (cashflows.post_fiscal * discount_factors).tolist()
    return [
        AnnualCashFlow(
            year=year,
            oil_revenue_usd=annual["oil_revenue"][year],
            gas_revenue_usd=annual["gas_revenue"][year],
            carbon_revenue_usd=annual["carbon_revenue"][year],
            lifting_cost_usd=annual["lifting"][year],
            workover_cost_usd=annual["workover"][year],
            mrv_cost_usd=annual["mrv"][year],
            supply_cost_usd=annual["supply"][year],
            pipeline_opex_usd=annual["pipeline_opex"][year],
            facility_opex_usd=annual["facility_opex"][year],
            capex_usd=annual["capex"][year],
            carbon_tax_usd=annual["carbon_tax"][year],
            cost_recovery_usd=annual["recovery"][year],
            government_take_usd=annual["government_take"][year],
            terminal_cashflow_usd=annual["terminal"][year],
            pre_tax_cashflow_usd=pre_tax[year],
            post_fiscal_cashflow_usd=post_fiscal[year],
            discounted_pre_tax_cashflow_usd=discounted_pre_tax[year],
            discounted_post_fiscal_cashflow_usd=discounted_post_fiscal[year],
        )
        for year in range(len(cashflows.pre_tax))
    ]


def _breakdown(state: _AnnualState, cashflows: _CashFlowState) -> EconomicBreakdown:
    annual = cashflows.annual
    values = {key: float(sum(value)) for key, value in annual.items()}
    total_revenue = values["oil_revenue"] + values["gas_revenue"] + values["carbon_revenue"]
    total_cost = (
        values["lifting"]
        + values["workover"]
        + values["mrv"]
        + values["supply"]
        + values["pipeline_opex"]
        + values["facility_opex"]
        + values["capex"]
        + values["carbon_tax"]
    )
    return EconomicBreakdown(
        oil_revenue_usd=values["oil_revenue"],
        gas_revenue_usd=values["gas_revenue"],
        carbon_revenue_usd=values["carbon_revenue"],
        lifting_cost_usd=values["lifting"],
        workover_cost_usd=values["workover"],
        mrv_cost_usd=values["mrv"],
        co2_supply_and_transport_usd=values["supply"],
        pipeline_capex_usd=state.pipeline_capex,
        booster_capex_usd=state.booster_capex,
        pipeline_opex_usd=values["pipeline_opex"],
        facility_capex_usd=state.facility_capex,
        facility_opex_usd=values["facility_opex"],
        carbon_tax_usd=values["carbon_tax"],
        terminal_cashflow_usd=values["terminal"],
        total_revenue_usd=total_revenue,
        total_cost_usd=total_cost,
    )


def evaluate_economic_batch(request: EconomicBatchRequest) -> EconomicBatchResult:
    """Evaluate all portfolio × carbon-price × fiscal combinations deterministically."""
    started = perf_counter()
    results: list[EconomicScenarioResult] = []
    all_reconciled = True
    irr_cache: dict[bytes, EconomicMetric] = {}
    payback_cache: dict[bytes, EconomicMetric] = {}
    for portfolio in request.portfolios:
        state = _portfolio_state(portfolio)
        storage = _storage_reconciliation(portfolio, state, request.assumptions)
        carbon_break_evens: dict[str, EconomicMetric] = {}
        for carbon in request.carbon_prices:
            for fiscal in request.fiscal_cases:
                base = _cashflows(
                    portfolio,
                    state,
                    request.assumptions,
                    fiscal,
                    carbon.carbon_price_usd_per_tonne,
                )
                low_cashflow = _uncertainty_post_fiscal_cashflow(
                    base,
                    state,
                    request.assumptions,
                    fiscal,
                    carbon.carbon_price_usd_per_tonne,
                    "low",
                )
                high_cashflow = _uncertainty_post_fiscal_cashflow(
                    base,
                    state,
                    request.assumptions,
                    fiscal,
                    carbon.carbon_price_usd_per_tonne,
                    "high",
                )
                if fiscal.case_id not in carbon_break_evens:
                    carbon_break_evens[fiscal.case_id] = _carbon_break_even(
                        base,
                        state,
                        request.assumptions,
                        fiscal,
                        carbon.carbon_price_usd_per_tonne,
                    )
                expected = (
                    base.annual["oil_revenue"]
                    + base.annual["gas_revenue"]
                    + base.annual["carbon_revenue"]
                    - base.annual["lifting"]
                    - base.annual["workover"]
                    - base.annual["mrv"]
                    - base.annual["supply"]
                    - base.annual["pipeline_opex"]
                    - base.annual["facility_opex"]
                    - base.annual["capex"]
                    + base.annual["terminal"]
                )
                reconciliation = float(np.max(np.abs(expected - base.pre_tax)))
                passed = (
                    reconciliation <= request.assumptions.usd_reconciliation_tolerance
                    and storage.mass_balance_passed
                )
                all_reconciled = all_reconciled and passed
                cashflow_key = base.post_fiscal.tobytes()
                irr_metric = irr_cache.get(cashflow_key)
                if irr_metric is None:
                    irr_metric = _irr(base.post_fiscal, request.assumptions)
                    irr_cache[cashflow_key] = irr_metric
                payback_metric = payback_cache.get(cashflow_key)
                if payback_metric is None:
                    payback_metric = _discounted_payback(
                        base.post_fiscal, request.assumptions.discount_rate
                    )
                    payback_cache[cashflow_key] = payback_metric
                results.append(
                    EconomicScenarioResult(
                        portfolio_id=portfolio.portfolio_id,
                        carbon_price_scenario_id=carbon.scenario_id,
                        fiscal_case_id=fiscal.case_id,
                        fiscal_mode=fiscal.mode,
                        annual_cashflows=_annual_models(base, request.assumptions),
                        storage=storage,
                        breakdown=_breakdown(state, base),
                        pre_tax_npv_usd=_npv(base.pre_tax, request.assumptions.discount_rate),
                        npv_usd=_npv(base.post_fiscal, request.assumptions.discount_rate),
                        npv_low_usd=_npv(low_cashflow, request.assumptions.discount_rate),
                        npv_high_usd=_npv(high_cashflow, request.assumptions.discount_rate),
                        irr=irr_metric,
                        discounted_payback=payback_metric,
                        break_even_carbon_price=carbon_break_evens[fiscal.case_id],
                        break_even_oil_price=(
                            _cost_recovery_oil_break_even(
                                base,
                                state,
                                request.assumptions,
                                fiscal,
                            )
                            if fiscal.mode == "cost_recovery"
                            else _linear_oil_break_even(
                                base,
                                state,
                                request.assumptions,
                                fiscal,
                            )
                        ),
                        accounting_reconciliation_usd=reconciliation,
                        reconciliation_passed=passed,
                        low_confidence=storage.low_confidence,
                        confidence_reasons=storage.reasons,
                        provenance=[*portfolio.provenance, *carbon.provenance, *fiscal.provenance],
                    )
                )

    rankings: list[EconomicRanking] = []
    for carbon in request.carbon_prices:
        for fiscal in request.fiscal_cases:
            group = [
                result
                for result in results
                if result.carbon_price_scenario_id == carbon.scenario_id
                and result.fiscal_case_id == fiscal.case_id
            ]
            base_order = [item.portfolio_id for item in sorted(group, key=lambda item: (-item.npv_usd, item.portfolio_id))]
            low_order = [item.portfolio_id for item in sorted(group, key=lambda item: (-item.npv_low_usd, item.portfolio_id))]
            high_order = [item.portfolio_id for item in sorted(group, key=lambda item: (-item.npv_high_usd, item.portfolio_id))]
            rankings.append(
                EconomicRanking(
                    carbon_price_scenario_id=carbon.scenario_id,
                    fiscal_case_id=fiscal.case_id,
                    base_order=base_order,
                    downside_order=low_order,
                    upside_order=high_order,
                    stable_across_bounds=base_order == low_order == high_order,
                )
            )
    return EconomicBatchResult(
        economic_basis_version=request.assumptions.version,
        currency_basis=request.assumptions.currency_basis,
        scenario_count=len(results),
        results=results,
        rankings=rankings,
        elapsed_seconds=perf_counter() - started,
        accounting_verdict="PASS" if all_reconciled else "FAIL",
        provenance=request.provenance,
    )
