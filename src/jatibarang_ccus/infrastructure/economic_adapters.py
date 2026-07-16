from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from CoolProp.CoolProp import PropsSI

from jatibarang_ccus.contracts import (
    AnnualEconomicPeriod,
    AnnualUncertainty,
    CarbonPriceScenario,
    EconomicAssumptions,
    EconomicProvenance,
    EconomicUncertaintyProfile,
    FacilityEconomicInput,
    FacilityPortfolioResult,
    FacilityWellResult,
    FiscalCase,
    PipelineDesignResult,
    PipelineRawSupplyCost,
    PortfolioEconomicInput,
    ScreenedWellValue,
    TruckingRawSupplyCost,
    TruckingSupplyResult,
)
from jatibarang_ccus.surrogate.config import REPO_ROOT
from jatibarang_ccus.surrogate.schemas import PredictionResult

DEFAULT_ECONOMIC_BASIS = REPO_ROOT / "data" / "jatibarang" / "economic_basis.json"
STANDARD_CO2_TEMPERATURE_K = 288.15
STANDARD_CO2_PRESSURE_PA = 101_325.0


def load_economic_basis(path: Path = DEFAULT_ECONOMIC_BASIS) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Economic basis is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def basis_provenance(basis: dict[str, Any]) -> list[EconomicProvenance]:
    return [
        EconomicProvenance(
            source_class="economic_assumption",
            source_id=f"economic-basis-{basis['version']}",
            notes=str(basis["status"]),
            metadata={"currency_basis": basis["currency_basis"]},
        )
    ]


def assumptions_from_basis(basis: dict[str, Any]) -> EconomicAssumptions:
    bounds = basis["root_bounds"]
    return EconomicAssumptions(
        version=basis["version"],
        currency_basis=basis["currency_basis"],
        discount_rate=basis["discount_rate"],
        oil_price_usd_per_bbl=basis["oil_price_usd_per_bbl"],
        gas_price_usd_per_mmbtu=basis["gas_price_usd_per_mmbtu"],
        gas_heating_value_mmbtu_per_std_m3=basis["gas_heating_value_mmbtu_per_std_m3"],
        lifting_cost_usd_per_bbl=basis["lifting_cost_usd_per_bbl"],
        workover_cost_usd_per_cycle=basis["workover_cost_usd_per_cycle"],
        mrv_cost_usd_per_tonne=basis["mrv_cost_usd_per_tonne"],
        certification_haircut=basis["certification_haircut"],
        storage_divergence_threshold_fraction_of_injected=basis[
            "storage_divergence_threshold_fraction_of_injected"
        ],
        usd_reconciliation_tolerance=basis["usd_reconciliation_tolerance"],
        mass_reconciliation_tolerance_tonnes=basis["mass_reconciliation_tolerance_tonnes"],
        irr_min=bounds["irr_min"],
        irr_max=bounds["irr_max"],
        carbon_price_max_usd_per_tonne=bounds["carbon_price_max_usd_per_tonne"],
        oil_price_max_usd_per_bbl=bounds["oil_price_max_usd_per_bbl"],
        root_iterations=bounds["iterations"],
    )


def carbon_prices_from_basis(basis: dict[str, Any]) -> list[CarbonPriceScenario]:
    output = []
    for scenario in basis["carbon_price_scenarios"]:
        source_class = (
            "market_observation" if scenario["source_type"] == "market_observation" else "economic_assumption"
        )
        output.append(
            CarbonPriceScenario(
                scenario_id=scenario["scenario_id"],
                carbon_price_usd_per_tonne=scenario["carbon_price_usd_per_tonne"],
                source_type=scenario["source_type"],
                provenance=[
                    EconomicProvenance(
                        source_class=source_class,
                        source_id=f"carbon-price-{scenario['scenario_id']}",
                        url=scenario.get("source_url", ""),
                        notes=scenario.get("notes", scenario.get("native_calculation", "")),
                        metadata={
                            key: value
                            for key, value in scenario.items()
                            if key
                            not in {
                                "scenario_id",
                                "carbon_price_usd_per_tonne",
                                "source_type",
                                "source_url",
                                "notes",
                            }
                        },
                    )
                ],
            )
        )
    return output


def fiscal_cases_from_basis(basis: dict[str, Any]) -> list[FiscalCase]:
    provenance = [
        EconomicProvenance(
            source_class="regulatory_source",
            source_id="parametric-fiscal-screening",
            notes="Screening sensitivity only; not an exact PSC replica.",
            metadata={"sources": basis["regulatory_sources"]},
        )
    ]
    return [FiscalCase(**case, provenance=provenance) for case in basis["fiscal_cases"]]


def standard_co2_density_kg_m3() -> float:
    """Return CoolProp CO2 density at the explicit 15 C, 1 atm standard state."""
    return float(
        PropsSI(
            "D",
            "T",
            STANDARD_CO2_TEMPERATURE_K,
            "P",
            STANDARD_CO2_PRESSURE_PA,
            "CO2",
        )
    )


def _allocate_interval(values: np.ndarray, start_day: float, duration_days: float, amount: float) -> None:
    if duration_days <= 0 or amount == 0:
        return
    end_day = start_day + duration_days
    cursor = start_day
    while cursor < end_day - 1e-12:
        year_index = int(cursor // 365.0)
        if year_index >= len(values):
            break
        year_end = (year_index + 1) * 365.0
        overlap = min(end_day, year_end) - cursor
        values[year_index] += amount * overlap / duration_days
        cursor += overlap


def annualize_prediction(
    prediction: PredictionResult,
    *,
    project_life_years: int,
    produced_co2_fraction: float,
    surface_loss_fraction: float = 0.0,
    co2_density_kg_m3: float | None = None,
) -> list[AnnualEconomicPeriod]:
    """Prorate Feature 001 interval outputs into calendar-year buckets."""
    if not 0 <= produced_co2_fraction <= 1:
        raise ValueError("Produced CO2 fraction must be between zero and one.")
    density = standard_co2_density_kg_m3() if co2_density_kg_m3 is None else co2_density_kg_m3
    arrays = {name: np.zeros(project_life_years, dtype=float) for name in (
        "injection_hours",
        "production_hours",
        "oil",
        "gas",
        "injected",
        "produced_back",
    )}
    inventory_available = prediction.inventory.status == "available"
    previous_injected = 0.0
    previous_produced_back = 0.0
    for index, step in enumerate(prediction.timeline):
        start = step.elapsed_days - step.dt_days
        _allocate_interval(
            arrays["injection_hours" if step.stage == "inject" else "production_hours"],
            start,
            step.dt_days,
            step.dt_days * 24.0 if step.stage in {"inject", "produce"} else 0.0,
        )
        _allocate_interval(arrays["oil"], start, step.dt_days, prediction.production.delta_oil_m3[index])
        _allocate_interval(arrays["gas"], start, step.dt_days, prediction.production.delta_gas_m3[index])
        cumulative_injected = prediction.inventory.injected_co2_tonnes[index]
        injected_delta = max(0.0, cumulative_injected - previous_injected)
        previous_injected = cumulative_injected
        _allocate_interval(arrays["injected"], start, step.dt_days, injected_delta)
        if inventory_available:
            cumulative_produced_back = prediction.inventory.produced_back_co2_tonnes[index]
            if cumulative_produced_back is not None:
                produced_back_delta = max(0.0, cumulative_produced_back - previous_produced_back)
                previous_produced_back = cumulative_produced_back
                _allocate_interval(arrays["produced_back"], start, step.dt_days, produced_back_delta)

    output = []
    for index in range(project_life_years):
        output.append(
            AnnualEconomicPeriod(
                year=index + 1,
                injection_hours=min(8_760.0, arrays["injection_hours"][index]),
                production_hours=min(8_760.0, arrays["production_hours"][index]),
                oil_produced_m3=arrays["oil"][index],
                gross_gas_produced_std_m3=arrays["gas"][index],
                produced_co2_fraction=produced_co2_fraction,
                co2_standard_density_kg_m3=density,
                injected_co2_tonnes=arrays["injected"][index],
                inventory_produced_back_co2_tonnes=(
                    arrays["produced_back"][index] if inventory_available else None
                ),
                surface_loss_co2_tonnes=arrays["injected"][index] * surface_loss_fraction,
                workover_count=0,
            )
        )
    return output


def uncertainty_from_prediction(
    prediction: PredictionResult,
    periods: list[AnnualEconomicPeriod],
    basis: dict[str, Any],
) -> EconomicUncertaintyProfile:
    defaults = basis["default_uncertainty"]
    co2_error = (
        defaults["extended_horizon_co2_mass_error_fraction"]
        if prediction.confidence.extended_horizon
        else defaults["co2_mass_error_fraction"]
    )
    reasons = list(prediction.confidence.low_confidence_reasons)
    residuals = [
        abs(float(value))
        for value in prediction.inventory.reconciliation_residual_tonnes
        if value is not None
    ]
    if residuals and max(residuals) > basis["mass_reconciliation_tolerance_tonnes"]:
        reasons.append("inventory_reconciliation_failed")
    return EconomicUncertaintyProfile(
        periods=[
            AnnualUncertainty(
                year=period.year,
                oil_error_fraction=defaults["oil_error_fraction"],
                gas_error_fraction=defaults["gas_error_fraction"],
                co2_mass_error_fraction=co2_error,
            )
            for period in periods
        ],
        extended_horizon=prediction.confidence.extended_horizon,
        low_confidence_reasons=list(dict.fromkeys(reasons)),
        provenance=[
            EconomicProvenance(
                source_class="surrogate_prediction",
                source_id=prediction.scenario_id,
                notes="Deterministic correlated low/base/high trajectories.",
                metadata=prediction.confidence.model_dump(),
            )
        ],
    )


def pipeline_raw_supply(
    pipeline: PipelineDesignResult,
    periods: list[AnnualEconomicPeriod],
    project_life_years: int,
    *,
    allocation_fraction: float = 1.0,
) -> PipelineRawSupplyCost:
    if not 0 <= allocation_fraction <= 1:
        raise ValueError("Pipeline allocation fraction must be between zero and one.")
    active = np.zeros(project_life_years, dtype=float)
    injection = np.zeros(project_life_years, dtype=float)
    for period in periods:
        injection[period.year - 1] = period.injected_co2_tonnes
        active[period.year - 1] = float(period.injection_hours > 0)
    design_mass = max(sum(pipeline.source_annual_flows_tonnes.values()), 1e-12)
    booster_energy_unit_cost = pipeline.costs.annual_booster_energy_usd / design_mass
    return PipelineRawSupplyCost(
        pipeline_capex_usd=pipeline.costs.pipeline_capex_usd * allocation_fraction,
        booster_capex_usd=pipeline.costs.booster_capex_usd * allocation_fraction,
        annual_maintenance_usd=(
            active * pipeline.costs.annual_maintenance_usd * allocation_fraction
        ).tolist(),
        annual_booster_energy_usd=(injection * booster_energy_unit_cost).tolist(),
        commodity_supply_usd_per_tonne=pipeline.costs.commodity_supply_usd_per_tonne,
        provenance=[
            EconomicProvenance(
                source_class="pipeline_result",
                source_id=f"pipeline-{pipeline.route_provenance.get('fingerprint', 'result')}",
                notes="Raw CAPEX, maintenance, booster energy, and commodity supply only.",
                metadata={"allocation_fraction": allocation_fraction},
            )
        ],
    )


def trucking_raw_supply(trucking: TruckingSupplyResult) -> TruckingRawSupplyCost:
    return TruckingRawSupplyCost(
        loading_usd_per_tonne=trucking.loading_cost_usd_per_tonne,
        liquefaction_usd_per_tonne=trucking.liquefaction_cost_usd_per_tonne,
        reconditioning_usd_per_tonne=trucking.reconditioning_cost_usd_per_tonne,
        distance_transport_usd_per_tonne=trucking.transport_cost_usd_per_tonne,
        commodity_supply_usd_per_tonne=trucking.commodity_supply_usd_per_tonne,
        provenance=[
            EconomicProvenance(
                source_class="pipeline_result",
                source_id=trucking.scenario_id,
                notes="Raw trucking cost components; levelized delivered cost excluded.",
            )
        ],
    )


def _facility_for_wells(
    wells: list[FacilityWellResult],
    periods: list[AnnualEconomicPeriod],
    project_life_years: int,
    source_id: str,
) -> FacilityEconomicInput:
    annual_opex = np.zeros(project_life_years, dtype=float)
    for well in wells:
        for equipment in well.equipment:
            for period in periods:
                if equipment.equipment_type == "injection_pump":
                    hours = period.injection_hours
                elif equipment.equipment_type == "balance_of_plant":
                    hours = max(period.injection_hours, period.production_hours)
                else:
                    hours = period.production_hours
                if hours <= 0:
                    continue
                energy_rate = (
                    equipment.annual_energy_cost_usd / equipment.operating_hours_per_year
                    if equipment.operating_hours_per_year > 0
                    else 0.0
                )
                annual_opex[period.year - 1] += energy_rate * hours + equipment.annual_maintenance_usd
    return FacilityEconomicInput(
        capex_usd=sum(well.capex_usd for well in wells),
        annual_opex_usd=annual_opex.tolist(),
        provenance=[
            EconomicProvenance(
                source_class="facility_result",
                source_id=source_id,
                notes="Energy allocated by modeled operating hours; maintenance by active asset-year.",
            )
        ],
    )


def facility_for_portfolio(
    facility: FacilityPortfolioResult,
    periods: list[AnnualEconomicPeriod],
    project_life_years: int,
) -> FacilityEconomicInput:
    return _facility_for_wells(
        facility.well_results,
        periods,
        project_life_years,
        facility.portfolio_id,
    )


def facility_for_well(
    facility: FacilityWellResult,
    periods: list[AnnualEconomicPeriod],
    project_life_years: int,
) -> FacilityEconomicInput:
    return _facility_for_wells([facility], periods, project_life_years, facility.candidate_id)


def apply_facility_surface_loss(
    periods: list[AnnualEconomicPeriod],
    facility: FacilityWellResult,
) -> list[AnnualEconomicPeriod]:
    fraction = facility.loss_ledger.net_storage_debit_fraction
    return [
        period.model_copy(
            update={"surface_loss_co2_tonnes": period.injected_co2_tonnes * fraction}
        )
        for period in periods
    ]


def annualize_screened_value(
    value: ScreenedWellValue,
    *,
    project_life_years: int,
    surface_loss_fraction: float,
) -> list[AnnualEconomicPeriod]:
    """Development-only adapter for the analytic Phase 1 screening proxy."""
    arrays = {name: np.zeros(project_life_years, dtype=float) for name in (
        "injection_hours",
        "production_hours",
        "oil",
        "gas",
        "injected",
        "produced_back",
        "workovers",
    )}
    cycles = int(value.parameters["cycles"])
    injection_days = 45.0
    soak_days = float(value.parameters["soak_days"])
    production_days = float(value.parameters["production_days"])
    cursor = 0.0
    produced_back_total = max(0.0, value.injected_co2_tonnes - value.stored_co2_tonnes)
    gas_total = value.peak_produced_gas_m3_day * production_days * 0.5 * cycles
    for _ in range(cycles):
        _allocate_interval(arrays["injection_hours"], cursor, injection_days, injection_days * 24.0)
        _allocate_interval(arrays["injected"], cursor, injection_days, value.injected_co2_tonnes / cycles)
        _allocate_interval(arrays["workovers"], cursor, injection_days, 1.0)
        cursor += injection_days + soak_days
        _allocate_interval(arrays["production_hours"], cursor, production_days, production_days * 24.0)
        _allocate_interval(
            arrays["oil"], cursor, production_days, value.oil_bbl / 6.289810770432105 / cycles
        )
        _allocate_interval(arrays["gas"], cursor, production_days, gas_total / cycles)
        _allocate_interval(
            arrays["produced_back"], cursor, production_days, produced_back_total / cycles
        )
        cursor += production_days
    density = standard_co2_density_kg_m3()
    return [
        AnnualEconomicPeriod(
            year=index + 1,
            injection_hours=min(8_760.0, arrays["injection_hours"][index]),
            production_hours=min(8_760.0, arrays["production_hours"][index]),
            oil_produced_m3=arrays["oil"][index],
            gross_gas_produced_std_m3=arrays["gas"][index],
            produced_co2_fraction=value.produced_co2_fraction,
            co2_standard_density_kg_m3=density,
            injected_co2_tonnes=arrays["injected"][index],
            inventory_produced_back_co2_tonnes=arrays["produced_back"][index],
            surface_loss_co2_tonnes=arrays["injected"][index] * surface_loss_fraction,
            workover_count=int(round(arrays["workovers"][index])),
        )
        for index in range(project_life_years)
    ]


def uncertainty_from_percentages(
    periods: list[AnnualEconomicPeriod],
    uncertainty: dict[str, float],
    source_id: str,
) -> EconomicUncertaintyProfile:
    production_error = float(uncertainty.get("production_error_pct", 0.0)) / 100.0
    mass_error = float(uncertainty.get("co2_mass_error_pct", 0.0)) / 100.0
    return EconomicUncertaintyProfile(
        periods=[
            AnnualUncertainty(
                year=period.year,
                oil_error_fraction=production_error,
                gas_error_fraction=production_error,
                co2_mass_error_fraction=mass_error,
            )
            for period in periods
        ],
        provenance=[
            EconomicProvenance(
                source_class="surrogate_prediction",
                source_id=source_id,
                notes="Compatibility uncertainty supplied by the Phase 1 metric summary.",
            )
        ],
    )


def combine_portfolios(
    portfolios: list[PortfolioEconomicInput],
    *,
    portfolio_id: str,
    provenance_notes: str = "Aggregate of allocated development-only Phase 1 well portfolios.",
) -> PortfolioEconomicInput:
    """Combine allocated well economics while preserving exactly-once ownership totals."""
    if not portfolios:
        raise ValueError("At least one portfolio is required for aggregation.")
    life = portfolios[0].project_life_years
    if any(item.project_life_years != life for item in portfolios):
        raise ValueError("Combined portfolios must share a project life.")
    if not all(isinstance(item.supply, PipelineRawSupplyCost) for item in portfolios):
        raise ValueError("The Phase 1 aggregate currently requires allocated pipeline_raw supply inputs.")
    supplies = [item.supply for item in portfolios]
    commodity = supplies[0].commodity_supply_usd_per_tonne
    if any(abs(item.commodity_supply_usd_per_tonne - commodity) > 1e-9 for item in supplies):
        raise ValueError("Combined pipeline portfolios must share a commodity supply price.")

    periods_by_portfolio = [{period.year: period for period in item.periods} for item in portfolios]
    combined_periods: list[AnnualEconomicPeriod] = []
    combined_uncertainty: list[AnnualUncertainty] = []
    uncertainty_maps = [
        {period.year: period for period in item.uncertainty.periods} for item in portfolios
    ]
    for year in range(1, life + 1):
        annual = [mapping.get(year) for mapping in periods_by_portfolio]
        annual = [item for item in annual if item is not None]
        gross_gas = sum(item.gross_gas_produced_std_m3 for item in annual)
        co2_volume = sum(
            item.gross_gas_produced_std_m3 * item.produced_co2_fraction for item in annual
        )
        fraction = co2_volume / gross_gas if gross_gas else 0.0
        density = (
            sum(
                item.gross_gas_produced_std_m3
                * item.produced_co2_fraction
                * item.co2_standard_density_kg_m3
                for item in annual
            )
            / co2_volume
            if co2_volume
            else standard_co2_density_kg_m3()
        )
        inventory_values = [item.inventory_produced_back_co2_tonnes for item in annual]
        combined_periods.append(
            AnnualEconomicPeriod(
                year=year,
                injection_hours=min(8_760.0, sum(item.injection_hours for item in annual)),
                production_hours=min(8_760.0, sum(item.production_hours for item in annual)),
                oil_produced_m3=sum(item.oil_produced_m3 for item in annual),
                gross_gas_produced_std_m3=gross_gas,
                produced_co2_fraction=fraction,
                co2_standard_density_kg_m3=density,
                injected_co2_tonnes=sum(item.injected_co2_tonnes for item in annual),
                inventory_produced_back_co2_tonnes=(
                    None
                    if any(value is None for value in inventory_values)
                    else sum(float(value) for value in inventory_values)
                ),
                surface_loss_co2_tonnes=sum(item.surface_loss_co2_tonnes for item in annual),
                workover_count=sum(item.workover_count for item in annual),
                taxable_emissions_tonnes=sum(item.taxable_emissions_tonnes for item in annual),
            )
        )
        uncertainties = [mapping.get(year) for mapping in uncertainty_maps]
        uncertainties = [item for item in uncertainties if item is not None]
        combined_uncertainty.append(
            AnnualUncertainty(
                year=year,
                oil_error_fraction=max((item.oil_error_fraction for item in uncertainties), default=0.0),
                gas_error_fraction=max((item.gas_error_fraction for item in uncertainties), default=0.0),
                co2_mass_error_fraction=max(
                    (item.co2_mass_error_fraction for item in uncertainties), default=0.0
                ),
            )
        )
    provenance = [
        EconomicProvenance(
            source_class="engineering_assumption",
            source_id=portfolio_id,
            notes=provenance_notes,
        )
    ]
    return PortfolioEconomicInput(
        portfolio_id=portfolio_id,
        evaluation_stage=(
            "final" if all(item.evaluation_stage == "final" for item in portfolios) else "preliminary"
        ),
        project_life_years=life,
        periods=combined_periods,
        supply=PipelineRawSupplyCost(
            pipeline_capex_usd=sum(item.pipeline_capex_usd for item in supplies),
            booster_capex_usd=sum(item.booster_capex_usd for item in supplies),
            annual_maintenance_usd=np.sum(
                [item.annual_maintenance_usd for item in supplies], axis=0
            ).tolist(),
            annual_booster_energy_usd=np.sum(
                [item.annual_booster_energy_usd for item in supplies], axis=0
            ).tolist(),
            commodity_supply_usd_per_tonne=commodity,
            provenance=provenance,
        ),
        facility=FacilityEconomicInput(
            capex_usd=sum(item.facility.capex_usd for item in portfolios),
            annual_opex_usd=np.sum(
                [item.facility.annual_opex_usd for item in portfolios], axis=0
            ).tolist(),
            provenance=provenance,
        ),
        uncertainty=EconomicUncertaintyProfile(
            periods=combined_uncertainty,
            extended_horizon=any(item.uncertainty.extended_horizon for item in portfolios),
            low_confidence_reasons=list(
                dict.fromkeys(
                    reason
                    for item in portfolios
                    for reason in item.uncertainty.low_confidence_reasons
                )
            ),
            provenance=provenance,
        ),
        terminal_cashflow_usd=sum(item.terminal_cashflow_usd for item in portfolios),
        provenance=provenance,
    )
