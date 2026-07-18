from __future__ import annotations

from jatibarang_ccus.contracts import (
    SupplyComparisonRequest,
    SupplyComparisonResult,
    SupplyOptionResult,
    TruckingSupplyResult,
)
from jatibarang_ccus.infrastructure.costs import annuity_present_value_factor, load_cost_basis
from jatibarang_ccus.infrastructure.pipeline import solve_pipeline_design


def _trucking_result(request: SupplyComparisonRequest, annual_mass_tonnes: float) -> TruckingSupplyResult:
    design_request = request.pipeline_request
    assumptions = design_request.assumptions
    basis = load_cost_basis(assumptions["pipeline"]["cost_basis_path"])
    case = basis["cases"][design_request.cost_case]
    loading = float(case["trucking_loading_usd_per_tonne"])
    liquefaction = float(case["trucking_liquefaction_usd_per_tonne"])
    reconditioning = float(case["trucking_reconditioning_usd_per_tonne"])
    distance_transport = float(case["trucking_usd_per_tonne_km"]) * request.trucking_distance_km
    supply = float(case["co2_supply_usd_per_tonne"])
    delivered = loading + liquefaction + reconditioning + distance_transport + supply
    annual_cost = delivered * annual_mass_tonnes
    economics = assumptions["economics"]
    pv_factor = annuity_present_value_factor(
        float(economics["discount_rate"]),
        int(economics["project_life_years"]),
    )
    return TruckingSupplyResult(
        scenario_id="subang_trucking",
        cost_case=design_request.cost_case,
        annual_mass_tonnes=annual_mass_tonnes,
        distance_km=request.trucking_distance_km,
        loading_cost_usd_per_tonne=loading,
        liquefaction_cost_usd_per_tonne=liquefaction,
        reconditioning_cost_usd_per_tonne=reconditioning,
        transport_cost_usd_per_tonne=distance_transport,
        commodity_supply_usd_per_tonne=supply,
        levelized_delivered_usd_per_tonne=delivered,
        annual_cost_usd=annual_cost,
        present_value_lifecycle_cost_usd=annual_cost * pv_factor,
        distance_provenance=request.distance_provenance,
        legs=request.trucking_legs,
        provenance={
            "status": basis["status"],
            "source": basis["trucking_source"],
            "cost_basis_path": basis["path"],
            "components": ["loading", "liquefaction", "reconditioning", "distance", "commodity_supply"],
        },
    )


def evaluate_trucking_supply(
    request: SupplyComparisonRequest,
    *,
    annual_mass_tonnes: float,
) -> TruckingSupplyResult:
    """Price trucking for an already-selected portfolio without rerunning well selection."""

    if annual_mass_tonnes <= 0:
        raise ValueError("Trucking counterfactual requires positive selected annual demand.")
    return _trucking_result(request, annual_mass_tonnes)


def compare_supply_scenarios(request: SupplyComparisonRequest) -> SupplyComparisonResult:
    """Compare optimized pipeline and cost-only trucking on one accounting basis."""

    pipeline = solve_pipeline_design(request.pipeline_request)
    if pipeline.domain_status != "accepted":
        raise ValueError(f"Pipeline design must be accepted before supply comparison; got {pipeline.domain_status!r}.")
    annual_mass = sum(
        demand.annual_demand_tonnes
        for demand in request.pipeline_request.well_demands
        if demand.candidate_id in pipeline.selected_wells
    )
    if annual_mass <= 0:
        raise ValueError("Supply comparison requires positive selected annual demand.")
    trucking = _trucking_result(request, annual_mass)
    pipeline_cost = pipeline.costs.levelized_delivered_usd_per_tonne
    difference = pipeline_cost - trucking.levelized_delivered_usd_per_tonne
    cheaper = "tie" if abs(difference) <= 1e-9 else ("pipeline" if difference < 0 else "trucking")
    pipeline_annual = pipeline.costs.annual_opex_usd + pipeline.costs.commodity_supply_usd_per_tonne * annual_mass
    alternatives = [
        SupplyOptionResult(
            scenario_id=request.pipeline_request.supply_scenario_id,
            mode="pipeline",
            cost_case=request.pipeline_request.cost_case,
            annual_mass_tonnes=annual_mass,
            annual_cost_usd=pipeline_annual,
            present_value_lifecycle_cost_usd=pipeline.costs.present_value_lifecycle_cost_usd,
            levelized_transport_usd_per_tonne=pipeline.costs.levelized_transport_usd_per_tonne,
            levelized_delivered_usd_per_tonne=pipeline_cost,
            provenance=pipeline.costs.provenance,
        ),
        SupplyOptionResult(
            scenario_id=trucking.scenario_id,
            mode="trucking",
            cost_case=trucking.cost_case,
            annual_mass_tonnes=annual_mass,
            annual_cost_usd=trucking.annual_cost_usd,
            present_value_lifecycle_cost_usd=trucking.present_value_lifecycle_cost_usd,
            levelized_transport_usd_per_tonne=(
                trucking.loading_cost_usd_per_tonne
                + trucking.liquefaction_cost_usd_per_tonne
                + trucking.reconditioning_cost_usd_per_tonne
                + trucking.transport_cost_usd_per_tonne
            ),
            levelized_delivered_usd_per_tonne=trucking.levelized_delivered_usd_per_tonne,
            provenance=trucking.provenance,
        ),
    ]
    return SupplyComparisonResult(
        cost_case=request.pipeline_request.cost_case,
        pipeline=pipeline,
        trucking=trucking,
        alternatives=alternatives,
        delivered_cost_difference_usd_per_tonne=difference,
        cheaper_mode=cheaper,
    )
