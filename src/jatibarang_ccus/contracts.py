from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator


class Coordinate(BaseModel):
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)


class CO2Source(BaseModel):
    id: str = Field(min_length=1)
    name: str
    location: Coordinate
    capacity_tonnes_per_year: float = Field(gt=0)
    max_mass_flow_kg_s: float = Field(gt=0)
    outlet_pressure_bar: float = Field(ge=80.0)
    outlet_temperature_c: float
    co2_purity: float = Field(ge=0.95, le=1)


class CandidateWell(BaseModel):
    """Legacy Phase 1 candidate metadata retained until Feature 005 integration."""

    id: str
    location: Coordinate
    oil_factor: float = Field(gt=0)
    storage_factor: float = Field(gt=0)
    influence_radius_m: float = Field(default=500.0, gt=0)


class ScreenedWellValue(BaseModel):
    """Legacy Phase 1 value payload adapted to PipelineWellDemand at the boundary."""

    candidate_id: str
    parameters: dict[str, float | int]
    oil_bbl: float = Field(ge=0)
    stored_co2_tonnes: float = Field(ge=0)
    injected_co2_tonnes: float = Field(ge=0)
    preliminary_npv_usd: float
    npv_without_carbon_usd: float
    carbon_price_usd_per_tonne: float = Field(ge=0)
    peak_produced_gas_m3_day: float = Field(ge=0)
    produced_co2_fraction: float = Field(ge=0, le=1)


class PipelineWellDemand(BaseModel):
    candidate_id: str = Field(min_length=1)
    location: Coordinate
    annual_demand_tonnes: float = Field(gt=0)
    peak_mass_flow_kg_s: float = Field(gt=0)
    pre_logistics_value_usd: float
    influence_radius_m: float = Field(default=500.0, gt=0)
    mandatory: bool = False
    provenance: dict[str, Any] = Field(default_factory=dict)


class ExclusionZone(BaseModel):
    zone_id: str
    zone_class: str
    routing_mode: Literal["hard", "penalty"]
    geometry: dict[str, Any]
    buffer_m: float = Field(default=0.0, ge=0)
    penalty_multiplier: float = Field(default=1.0, ge=1.0)
    provenance: dict[str, Any] = Field(default_factory=dict)


class RouteNode(BaseModel):
    id: str
    kind: Literal["source", "well", "junction"]
    location: Coordinate
    elevation_m: float


class RouteSegment(BaseModel):
    id: str
    from_node: str
    to_node: str
    geometry: list[Coordinate]
    elevation_m: list[float]
    length_km: float = Field(gt=0)
    min_slope: float
    max_slope: float
    route_cost: float = Field(ge=0)
    terrain_sha256: str
    method: Literal["astar_srtm"] = "astar_srtm"
    geometry_crs: str = "EPSG:4326"
    hard_exclusion_ids: list[str] = Field(default_factory=list)
    penalty_zone_ids: list[str] = Field(default_factory=list)
    penalty_cost: float = Field(default=0.0, ge=0)

    @model_validator(mode="after")
    def _profiles_align(self) -> "RouteSegment":
        if len(self.geometry) != len(self.elevation_m) or len(self.geometry) < 2:
            raise ValueError("Route geometry and elevation profile must have the same length >=2.")
        if self.hard_exclusion_ids:
            raise ValueError("A routable segment may not intersect a hard exclusion.")
        return self


class RouteLibraryRequest(BaseModel):
    sources: list[CO2Source] = Field(min_length=1)
    well_demands: list[PipelineWellDemand] = Field(min_length=1)
    routing_assumptions: dict[str, Any]


class RouteLibrary(BaseModel):
    nodes: list[RouteNode]
    segments: list[RouteSegment]
    fingerprint: str
    provenance: dict[str, Any]


class PipelineDesignRequest(BaseModel):
    objective_mode: Literal["max_net_value", "min_lifecycle_cost"] = "max_net_value"
    supply_scenario_id: str = "optimized_pipeline"
    sources: list[CO2Source] = Field(min_length=1)
    well_demands: list[PipelineWellDemand] = Field(min_length=1)
    route_library: RouteLibrary
    annual_co2_budget_tonnes: float = Field(gt=0)
    assumptions: dict[str, Any]
    cost_case: Literal["low", "base", "high"] = "base"
    delivery_target_tonnes_per_year: float | None = Field(default=None, gt=0)
    solver: str = "cbc"

    @model_validator(mode="after")
    def _validate_design_request(self) -> "PipelineDesignRequest":
        source_ids = [item.id for item in self.sources]
        well_ids = [item.candidate_id for item in self.well_demands]
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("Source ids must be unique.")
        if len(set(well_ids)) != len(well_ids):
            raise ValueError("Well ids must be unique.")
        if set(source_ids) & set(well_ids):
            raise ValueError("Source and well ids must be disjoint.")
        if self.objective_mode == "min_lifecycle_cost":
            if not any(item.mandatory for item in self.well_demands) and self.delivery_target_tonnes_per_year is None:
                raise ValueError("Minimum-cost mode requires a mandatory well or delivery target.")
        return self


class PressureProfilePoint(BaseModel):
    distance_km: float = Field(ge=0)
    elevation_m: float
    pressure_bar: float
    hydraulic_head_bar: float
    density_kg_m3: float = Field(gt=0)
    velocity_m_s: float = Field(ge=0)


class BuiltSegment(BaseModel):
    segment_id: str
    from_node: str
    to_node: str
    diameter_in: float
    maop_bar: float
    length_km: float
    flow_tonnes_per_year: float
    peak_mass_flow_kg_s: float
    velocity_m_s: float
    inlet_pressure_bar: float
    outlet_pressure_bar: float
    pressure_drop_bar: float
    pwl_pressure_drop_bar: float
    pwl_error_bar: float = Field(ge=0)
    pwl_tolerance_bar: float = Field(ge=0)
    dense_phase_ok: bool
    maop_ok: bool = True
    continuous_profile: list[PressureProfilePoint] = Field(default_factory=list)
    allocated_lifecycle_cost_usd: float = Field(default=0.0, ge=0)


class BoosterStation(BaseModel):
    node_id: str
    suction_pressure_bar: float
    discharge_pressure_bar: float
    lift_bar: float = Field(gt=0)
    mass_flow_kg_s: float = Field(gt=0)
    power_kw: float = Field(ge=0)
    capex_usd: float = Field(ge=0)
    annual_energy_cost_usd: float = Field(ge=0)


class WellSelectionDecision(BaseModel):
    candidate_id: str
    selected: bool
    reason: Literal[
        "selected",
        "negative_net_value",
        "annual_budget",
        "source_capacity",
        "peak_deliverability",
        "network_cost",
        "mandatory",
        "infeasible",
    ]


class NetworkCostBreakdown(BaseModel):
    cost_case: Literal["low", "base", "high"]
    currency: str = "USD"
    cost_year: int
    pipeline_capex_usd: float = Field(ge=0)
    booster_capex_usd: float = Field(ge=0)
    annual_maintenance_usd: float = Field(ge=0)
    annual_booster_energy_usd: float = Field(ge=0)
    annual_opex_usd: float = Field(ge=0)
    commodity_supply_usd_per_tonne: float = Field(ge=0)
    present_value_lifecycle_cost_usd: float = Field(ge=0)
    levelized_transport_usd_per_tonne: float = Field(ge=0)
    levelized_delivered_usd_per_tonne: float = Field(ge=0)
    accounting_basis: Literal["raw_cashflows_levelized_display_only"] = "raw_cashflows_levelized_display_only"
    provenance: dict[str, Any] = Field(default_factory=dict)


class PipelineDesignResult(BaseModel):
    domain_status: Literal[
        "accepted",
        "no_viable_network",
        "infeasible",
        "not_solved_to_tolerance",
        "hydraulic_verification_failed",
    ]
    solver: str
    solver_status: str
    termination_condition: str
    objective_mode: Literal["max_net_value", "min_lifecycle_cost"]
    objective_value_usd: float | None = None
    objective_bound_usd: float | None = None
    optimality_gap: float | None = Field(default=None, ge=0)
    selected_wells: list[str]
    well_decisions: list[WellSelectionDecision]
    built_segments: list[BuiltSegment]
    boosters: list[BoosterStation]
    node_pressures_bar: dict[str, float]
    source_annual_flows_tonnes: dict[str, float]
    source_peak_flows_kg_s: dict[str, float]
    delivered_cost_usd_per_tonne: dict[str, float]
    per_well_allocated_cost_usd: dict[str, float]
    costs: NetworkCostBreakdown
    constraint_audit: dict[str, Any]
    hydraulic_verification: dict[str, Any]
    solve_time_seconds: float
    route_provenance: dict[str, Any]
    # Transitional fields used by the existing Phase 1 economics adapter.
    pipeline_capex_usd: float = Field(ge=0)
    booster_capex_usd: float = Field(ge=0)
    annual_opex_usd: float = Field(ge=0)
    total_network_cost_usd: float = Field(ge=0)

    @property
    def status(self) -> str:
        return self.solver_status

    @property
    def booster_nodes(self) -> list[str]:
        return [item.node_id for item in self.boosters]


class TruckingSupplyResult(BaseModel):
    scenario_id: str
    mode: Literal["trucking"] = "trucking"
    cost_case: Literal["low", "base", "high"]
    annual_mass_tonnes: float = Field(gt=0)
    distance_km: float = Field(gt=0)
    loading_cost_usd_per_tonne: float = Field(ge=0)
    liquefaction_cost_usd_per_tonne: float = Field(ge=0)
    reconditioning_cost_usd_per_tonne: float = Field(ge=0)
    transport_cost_usd_per_tonne: float = Field(ge=0)
    commodity_supply_usd_per_tonne: float = Field(ge=0)
    levelized_delivered_usd_per_tonne: float = Field(ge=0)
    annual_cost_usd: float = Field(ge=0)
    present_value_lifecycle_cost_usd: float = Field(ge=0)
    accounting_basis: Literal["raw_cashflows_levelized_display_only"] = "raw_cashflows_levelized_display_only"
    provenance: dict[str, Any]


class SupplyOptionResult(BaseModel):
    scenario_id: str
    mode: Literal["pipeline", "trucking"]
    cost_case: Literal["low", "base", "high"]
    annual_mass_tonnes: float = Field(gt=0)
    annual_cost_usd: float = Field(ge=0)
    present_value_lifecycle_cost_usd: float = Field(ge=0)
    levelized_transport_usd_per_tonne: float = Field(ge=0)
    levelized_delivered_usd_per_tonne: float = Field(ge=0)
    accounting_basis: Literal["raw_cashflows_levelized_display_only"] = "raw_cashflows_levelized_display_only"
    provenance: dict[str, Any] = Field(default_factory=dict)


class SupplyComparisonRequest(BaseModel):
    pipeline_request: PipelineDesignRequest
    trucking_distance_km: float = Field(gt=0)


class SupplyComparisonResult(BaseModel):
    cost_case: Literal["low", "base", "high"]
    pipeline: PipelineDesignResult
    trucking: TruckingSupplyResult
    alternatives: list[SupplyOptionResult] = Field(min_length=2)
    delivered_cost_difference_usd_per_tonne: float
    cheaper_mode: Literal["pipeline", "trucking", "tie"]
    accounting_basis: Literal["raw_cashflows_levelized_display_only"] = "raw_cashflows_levelized_display_only"


FacilitySourceClass = Literal[
    "field_fact",
    "literature_proxy",
    "surrogate_prediction",
    "pipeline_result",
    "engineering_assumption",
    "engineering_correlation",
    "dwsim_reference",
]


class FacilityProvenance(BaseModel):
    source_class: FacilitySourceClass
    source_id: str = Field(min_length=1)
    notes: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class FacilityWellLoad(BaseModel):
    candidate_id: str = Field(min_length=1)
    injection_rate_std_m3_day: float = Field(gt=0)
    injection_reference_pressure_bar: float = Field(gt=0)
    injection_reference_temperature_c: float = Field(gt=-273.15)
    fresh_co2_peak_mass_flow_kg_s: float = Field(gt=0)
    annual_injected_co2_tonnes: float = Field(ge=0)
    delivery_pressure_bar: float = Field(ge=80)
    delivery_temperature_c: float = Field(gt=-273.15)
    wellhead_injection_pressure_bar: float = Field(ge=80, le=137.895146)
    peak_produced_gas_std_m3_day: float = Field(ge=0)
    produced_gas_reference_pressure_bar: float = Field(gt=0)
    produced_gas_reference_temperature_c: float = Field(gt=-273.15)
    produced_co2_mole_fraction: float = Field(ge=0, le=1)
    peak_produced_liquid_m3_day: float = Field(ge=0)
    water_cut_fraction: float = Field(ge=0, le=1)
    separator_pressure_bar: float = Field(gt=0)
    separator_temperature_c: float = Field(gt=-273.15)
    injection_operating_hours_per_year: float = Field(ge=0, le=8_760)
    production_operating_hours_per_year: float = Field(ge=0, le=8_760)
    recycle_enabled: bool
    recycle_recovery_fraction: float = Field(ge=0, le=1)
    provenance: list[FacilityProvenance] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_recycle(self) -> "FacilityWellLoad":
        if not self.recycle_enabled and self.recycle_recovery_fraction != 0:
            raise ValueError("Recycle recovery must be zero when recycle is disabled.")
        return self


class FacilityPortfolioRequest(BaseModel):
    contract_type: Literal["facility_portfolio_request"] = "facility_portfolio_request"
    portfolio_id: str = Field(min_length=1)
    ownership_basis: Literal["dedicated_well_pad_skids"] = "dedicated_well_pad_skids"
    cost_case: Literal["low", "base", "high"] = "base"
    design_basis_version: str = Field(min_length=1)
    cost_basis_version: str = Field(min_length=1)
    wells: list[FacilityWellLoad] = Field(min_length=1, max_length=8)
    provenance: list[FacilityProvenance] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_wells(self) -> "FacilityPortfolioRequest":
        ids = [well.candidate_id for well in self.wells]
        if len(ids) != len(set(ids)):
            raise ValueError("Facility portfolio well ids must be unique.")
        return self


class FacilityEquipmentItem(BaseModel):
    equipment_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    equipment_type: Literal[
        "injection_pump",
        "recycle_compressor",
        "intercooler",
        "dehydration",
        "three_phase_separator",
        "balance_of_plant",
    ]
    ownership_scope: Literal["dedicated_well_pad"] = "dedicated_well_pad"
    duty_value: float = Field(ge=0)
    duty_unit: str = Field(min_length=1)
    power_kw: float = Field(default=0, ge=0)
    heat_duty_kw: float = Field(default=0, ge=0)
    operating_hours_per_year: float = Field(default=0, ge=0, le=8_760)
    duty_train_count: int = Field(ge=0)
    installed_train_count: int = Field(ge=0)
    capex_usd: float = Field(ge=0)
    annual_energy_cost_usd: float = Field(default=0, ge=0)
    annual_maintenance_usd: float = Field(default=0, ge=0)
    annual_opex_usd: float = Field(ge=0)
    calculation_method: str = ""
    specifications: dict[str, Any] = Field(default_factory=dict)
    provenance: list[FacilityProvenance] = Field(default_factory=list)

    @model_validator(mode="after")
    def _train_counts(self) -> "FacilityEquipmentItem":
        if self.installed_train_count < self.duty_train_count:
            raise ValueError("Installed train count cannot be below duty train count.")
        return self


class FacilitySurfaceLossLedger(BaseModel):
    fresh_co2_handled_tonnes_per_year: float = Field(ge=0)
    recycle_co2_handled_tonnes_per_year: float = Field(ge=0)
    conditioning_purge_tonnes_per_year: float = Field(ge=0)
    recycle_non_recovery_tonnes_per_year: float = Field(ge=0)
    fugitive_tonnes_per_year: float = Field(ge=0)
    atmospheric_emissions_tonnes_per_year: float = Field(ge=0)
    net_storage_debit_tonnes_per_year: float = Field(ge=0)
    net_storage_debit_fraction: float = Field(ge=0, le=1)
    produced_back_co2_tonnes_per_year: float = Field(ge=0)
    reconciliation_residual_tonnes_per_year: float = Field(ge=0)


FacilityCalibrationStatus = Literal["validated", "outside_calibration_envelope", "unvalidated"]


class FacilityWellResult(BaseModel):
    candidate_id: str = Field(min_length=1)
    input_fingerprint: str = Field(min_length=1)
    equipment: list[FacilityEquipmentItem] = Field(min_length=1)
    compression_power_kw: float = Field(ge=0)
    pump_power_kw: float = Field(ge=0)
    total_power_kw: float = Field(ge=0)
    separator_capacity_m3_day: float = Field(ge=0)
    capex_usd: float = Field(ge=0)
    annual_opex_usd: float = Field(ge=0)
    surface_loss_tonnes_per_year: float = Field(ge=0)
    surface_loss_fraction: float = Field(ge=0, le=1)
    loss_ledger: FacilitySurfaceLossLedger
    reconciliation_passed: Literal[True]
    calibration_status: FacilityCalibrationStatus
    calibration_flags: list[str] = Field(default_factory=list)
    provenance: list[FacilityProvenance] = Field(min_length=1)

    @model_validator(mode="after")
    def _reconcile_components(self) -> "FacilityWellResult":
        capex = sum(item.capex_usd for item in self.equipment)
        opex = sum(item.annual_opex_usd for item in self.equipment)
        tolerance = 1e-6 * max(1.0, self.capex_usd, self.annual_opex_usd)
        if abs(capex - self.capex_usd) > tolerance or abs(opex - self.annual_opex_usd) > tolerance:
            raise ValueError("Facility equipment costs do not reconcile to the well totals.")
        if abs(self.loss_ledger.net_storage_debit_tonnes_per_year - self.surface_loss_tonnes_per_year) > 1e-6:
            raise ValueError("Facility loss ledger does not reconcile to the well surface loss.")
        return self

    @property
    def dwsim_validation_status(self) -> FacilityCalibrationStatus:
        return self.calibration_status


class FacilityPortfolioResult(BaseModel):
    contract_type: Literal["facility_portfolio_result"] = "facility_portfolio_result"
    portfolio_id: str = Field(min_length=1)
    ownership_basis: Literal["dedicated_well_pad_skids"] = "dedicated_well_pad_skids"
    design_basis_version: str = Field(min_length=1)
    cost_basis_version: str = Field(min_length=1)
    calibration_version: str = Field(min_length=1)
    validation_status: FacilityCalibrationStatus
    well_results: list[FacilityWellResult] = Field(min_length=1, max_length=8)
    total_capex_usd: float = Field(ge=0)
    total_annual_opex_usd: float = Field(ge=0)
    total_surface_loss_tonnes_per_year: float = Field(ge=0)
    reconciliation_passed: Literal[True]
    evidence_manifest: str = ""
    provenance: list[FacilityProvenance] = Field(min_length=1)

    @model_validator(mode="after")
    def _reconcile_portfolio(self) -> "FacilityPortfolioResult":
        ids = [well.candidate_id for well in self.well_results]
        if len(ids) != len(set(ids)):
            raise ValueError("Facility result well ids must be unique.")
        capex = sum(well.capex_usd for well in self.well_results)
        opex = sum(well.annual_opex_usd for well in self.well_results)
        losses = sum(well.surface_loss_tonnes_per_year for well in self.well_results)
        tolerance = 1e-6 * max(1.0, self.total_capex_usd, self.total_annual_opex_usd)
        if (
            abs(capex - self.total_capex_usd) > tolerance
            or abs(opex - self.total_annual_opex_usd) > tolerance
            or abs(losses - self.total_surface_loss_tonnes_per_year) > 1e-6
        ):
            raise ValueError("Facility well results do not reconcile to the portfolio totals.")
        return self


# Transitional Feature 003 aliases remain available to its existing callers.
FacilityInput = FacilityWellLoad
FacilityResult = FacilityWellResult


EconomicSourceClass = Literal[
    "field_fact",
    "literature_proxy",
    "market_observation",
    "regulatory_source",
    "surrogate_prediction",
    "pipeline_result",
    "facility_result",
    "engineering_assumption",
    "engineering_correlation",
    "economic_assumption",
]


class EconomicProvenance(BaseModel):
    source_class: EconomicSourceClass
    source_id: str = Field(min_length=1)
    url: str = ""
    notes: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class AnnualEconomicPeriod(BaseModel):
    year: int = Field(ge=1, le=50)
    injection_hours: float = Field(default=0.0, ge=0, le=8_760)
    production_hours: float = Field(default=0.0, ge=0, le=8_760)
    oil_produced_m3: float = Field(default=0.0, ge=0)
    gross_gas_produced_std_m3: float = Field(default=0.0, ge=0)
    produced_co2_fraction: float = Field(default=0.0, ge=0, le=1)
    co2_standard_density_kg_m3: float = Field(default=1.872, gt=0)
    injected_co2_tonnes: float = Field(default=0.0, ge=0)
    inventory_produced_back_co2_tonnes: float | None = Field(default=None, ge=0)
    surface_loss_co2_tonnes: float = Field(default=0.0, ge=0)
    workover_count: int = Field(default=0, ge=0)
    taxable_emissions_tonnes: float = Field(default=0.0, ge=0)


class FlatDeliveredSupplyCost(BaseModel):
    model_config = {"extra": "forbid"}

    kind: Literal["flat_delivered"] = "flat_delivered"
    delivered_cost_usd_per_tonne: float = Field(ge=0)
    provenance: list[EconomicProvenance] = Field(min_length=1)


class PipelineRawSupplyCost(BaseModel):
    model_config = {"extra": "forbid"}

    kind: Literal["pipeline_raw"] = "pipeline_raw"
    pipeline_capex_usd: float = Field(ge=0)
    booster_capex_usd: float = Field(ge=0)
    annual_maintenance_usd: list[float]
    annual_booster_energy_usd: list[float]
    commodity_supply_usd_per_tonne: float = Field(ge=0)
    provenance: list[EconomicProvenance] = Field(min_length=1)


class TruckingRawSupplyCost(BaseModel):
    model_config = {"extra": "forbid"}

    kind: Literal["trucking_raw"] = "trucking_raw"
    loading_usd_per_tonne: float = Field(ge=0)
    liquefaction_usd_per_tonne: float = Field(ge=0)
    reconditioning_usd_per_tonne: float = Field(ge=0)
    distance_transport_usd_per_tonne: float = Field(ge=0)
    commodity_supply_usd_per_tonne: float = Field(ge=0)
    provenance: list[EconomicProvenance] = Field(min_length=1)


SupplyCostBasis = Annotated[
    FlatDeliveredSupplyCost | PipelineRawSupplyCost | TruckingRawSupplyCost,
    Field(discriminator="kind"),
]


class FacilityEconomicInput(BaseModel):
    capex_usd: float = Field(ge=0)
    annual_opex_usd: list[float]
    provenance: list[EconomicProvenance] = Field(min_length=1)


class AnnualUncertainty(BaseModel):
    year: int = Field(ge=1, le=50)
    oil_error_fraction: float = Field(default=0.0, ge=0, le=1)
    gas_error_fraction: float = Field(default=0.0, ge=0, le=1)
    co2_mass_error_fraction: float = Field(default=0.0, ge=0, le=1)


class EconomicUncertaintyProfile(BaseModel):
    periods: list[AnnualUncertainty] = Field(default_factory=list)
    extended_horizon: bool = False
    low_confidence_reasons: list[str] = Field(default_factory=list)
    provenance: list[EconomicProvenance] = Field(min_length=1)


class PortfolioEconomicInput(BaseModel):
    portfolio_id: str = Field(min_length=1)
    evaluation_stage: Literal["preliminary", "final"] = "final"
    project_life_years: int = Field(ge=1, le=50)
    periods: list[AnnualEconomicPeriod] = Field(min_length=1)
    supply: SupplyCostBasis
    facility: FacilityEconomicInput
    uncertainty: EconomicUncertaintyProfile
    terminal_cashflow_usd: float = 0.0
    provenance: list[EconomicProvenance] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_portfolio(self) -> "PortfolioEconomicInput":
        years = [period.year for period in self.periods]
        if len(set(years)) != len(years):
            raise ValueError("Economic period years must be unique.")
        if max(years) > self.project_life_years:
            raise ValueError("Economic period year exceeds project life.")
        if len(self.facility.annual_opex_usd) != self.project_life_years:
            raise ValueError("Facility annual OPEX must have one value per project year.")
        if isinstance(self.supply, PipelineRawSupplyCost):
            if (
                len(self.supply.annual_maintenance_usd) != self.project_life_years
                or len(self.supply.annual_booster_energy_usd) != self.project_life_years
            ):
                raise ValueError("Pipeline annual cost vectors must match project life.")
        uncertainty_years = [period.year for period in self.uncertainty.periods]
        if len(set(uncertainty_years)) != len(uncertainty_years):
            raise ValueError("Uncertainty period years must be unique.")
        if uncertainty_years and max(uncertainty_years) > self.project_life_years:
            raise ValueError("Uncertainty period year exceeds project life.")
        if self.evaluation_stage == "final" and any(
            period.inventory_produced_back_co2_tonnes is None for period in self.periods
        ):
            raise ValueError("Final economics requires inventory-derived produced-back CO2 for every period.")
        return self


class CarbonPriceScenario(BaseModel):
    scenario_id: str = Field(min_length=1)
    carbon_price_usd_per_tonne: float = Field(ge=0)
    source_type: Literal["market_observation", "economic_assumption"]
    provenance: list[EconomicProvenance] = Field(min_length=1)


RecoverableCostCategory = Literal[
    "supply",
    "facility_capex",
    "facility_opex",
    "pipeline_capex",
    "pipeline_opex",
    "lifting",
    "workover",
    "mrv",
]


class FiscalCase(BaseModel):
    case_id: str = Field(min_length=1)
    mode: Literal["pre_tax", "cost_recovery", "gross_split"]
    government_take_fraction: float = Field(default=0.0, ge=0, le=1)
    cost_recovery_ceiling_fraction: float = Field(default=0.0, ge=0, le=1)
    recoverable_cost_categories: list[RecoverableCostCategory] = Field(
        default_factory=lambda: [
            "supply",
            "facility_capex",
            "facility_opex",
            "pipeline_capex",
            "pipeline_opex",
            "lifting",
            "workover",
            "mrv",
        ]
    )
    carbon_revenue_tax_fraction: float = Field(default=0.0, ge=0, le=1)
    carbon_tax_enabled: bool = False
    carbon_tax_usd_per_tonne: float = Field(default=0.0, ge=0)
    provenance: list[EconomicProvenance] = Field(min_length=1)


class EconomicAssumptions(BaseModel):
    version: str = Field(min_length=1)
    currency_basis: str = Field(min_length=1)
    discount_rate: float = Field(gt=-1, le=1)
    oil_price_usd_per_bbl: float = Field(ge=0)
    gas_price_usd_per_mmbtu: float = Field(ge=0)
    gas_heating_value_mmbtu_per_std_m3: float = Field(gt=0)
    lifting_cost_usd_per_bbl: float = Field(ge=0)
    workover_cost_usd_per_cycle: float = Field(ge=0)
    mrv_cost_usd_per_tonne: float = Field(ge=0)
    certification_haircut: float = Field(ge=0, le=1)
    storage_divergence_threshold_fraction_of_injected: float = Field(ge=0, le=1)
    usd_reconciliation_tolerance: float = Field(default=0.01, gt=0)
    mass_reconciliation_tolerance_tonnes: float = Field(default=1e-6, gt=0)
    irr_min: float = Field(default=-0.99, gt=-1)
    irr_max: float = Field(default=10.0, gt=0)
    carbon_price_max_usd_per_tonne: float = Field(default=1000.0, gt=0)
    oil_price_max_usd_per_bbl: float = Field(default=500.0, gt=0)
    root_iterations: int = Field(default=80, ge=20, le=200)


class EconomicBatchRequest(BaseModel):
    portfolios: list[PortfolioEconomicInput] = Field(min_length=1, max_length=256)
    carbon_prices: list[CarbonPriceScenario] = Field(min_length=4)
    fiscal_cases: list[FiscalCase] = Field(min_length=1)
    assumptions: EconomicAssumptions
    provenance: list[EconomicProvenance] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_dimensions(self) -> "EconomicBatchRequest":
        dimensions = {
            "portfolio": [item.portfolio_id for item in self.portfolios],
            "carbon-price": [item.scenario_id for item in self.carbon_prices],
            "fiscal": [item.case_id for item in self.fiscal_cases],
        }
        for name, values in dimensions.items():
            if len(values) != len(set(values)):
                raise ValueError(f"{name} ids must be unique.")
        return self


MetricStatus = Literal[
    "computed",
    "already_profitable",
    "zero_storage",
    "not_bracketed",
    "no_root",
    "multiple_roots",
    "never_paid_back",
]


class EconomicMetric(BaseModel):
    value: float | None
    status: MetricStatus
    method: str


class StorageReconciliation(BaseModel):
    injected_co2_tonnes: float = Field(ge=0)
    inventory_produced_back_co2_tonnes: float = Field(ge=0)
    stream_produced_back_co2_tonnes: float = Field(ge=0)
    surface_loss_co2_tonnes: float = Field(ge=0)
    primary_net_stored_co2_tonnes: float
    crosscheck_net_stored_co2_tonnes: float
    absolute_divergence_tonnes: float = Field(ge=0)
    divergence_fraction_of_injected: float = Field(ge=0)
    mass_balance_residual_tonnes: float = Field(ge=0)
    mass_balance_passed: bool
    low_confidence: bool
    reasons: list[str] = Field(default_factory=list)


class AnnualCashFlow(BaseModel):
    year: int = Field(ge=0, le=50)
    oil_revenue_usd: float
    gas_revenue_usd: float
    carbon_revenue_usd: float
    lifting_cost_usd: float
    workover_cost_usd: float
    mrv_cost_usd: float
    supply_cost_usd: float
    pipeline_opex_usd: float
    facility_opex_usd: float
    capex_usd: float
    carbon_tax_usd: float
    cost_recovery_usd: float
    government_take_usd: float
    terminal_cashflow_usd: float
    pre_tax_cashflow_usd: float
    post_fiscal_cashflow_usd: float
    discounted_pre_tax_cashflow_usd: float
    discounted_post_fiscal_cashflow_usd: float


class EconomicBreakdown(BaseModel):
    oil_revenue_usd: float
    gas_revenue_usd: float
    carbon_revenue_usd: float
    lifting_cost_usd: float
    workover_cost_usd: float
    mrv_cost_usd: float
    co2_supply_and_transport_usd: float
    pipeline_capex_usd: float
    booster_capex_usd: float
    pipeline_opex_usd: float
    facility_capex_usd: float
    facility_opex_usd: float
    carbon_tax_usd: float
    terminal_cashflow_usd: float
    total_revenue_usd: float
    total_cost_usd: float


class EconomicScenarioResult(BaseModel):
    portfolio_id: str
    carbon_price_scenario_id: str
    fiscal_case_id: str
    fiscal_mode: Literal["pre_tax", "cost_recovery", "gross_split"]
    annual_cashflows: list[AnnualCashFlow]
    storage: StorageReconciliation
    breakdown: EconomicBreakdown
    pre_tax_npv_usd: float
    npv_usd: float
    npv_low_usd: float
    npv_high_usd: float
    irr: EconomicMetric
    discounted_payback: EconomicMetric
    break_even_carbon_price: EconomicMetric
    break_even_oil_price: EconomicMetric
    accounting_reconciliation_usd: float
    reconciliation_passed: bool
    low_confidence: bool
    confidence_reasons: list[str]
    provenance: list[EconomicProvenance]


class EconomicRanking(BaseModel):
    carbon_price_scenario_id: str
    fiscal_case_id: str
    base_order: list[str]
    downside_order: list[str]
    upside_order: list[str]
    stable_across_bounds: bool


class EconomicBatchResult(BaseModel):
    economic_basis_version: str
    currency_basis: str
    scenario_count: int = Field(ge=1)
    results: list[EconomicScenarioResult]
    rankings: list[EconomicRanking]
    elapsed_seconds: float = Field(ge=0)
    accounting_verdict: Literal["PASS", "FAIL"]
    qualification: Literal["screening_grade_parametric_fiscal_sensitivity"] = (
        "screening_grade_parametric_fiscal_sensitivity"
    )
    provenance: list[EconomicProvenance]
