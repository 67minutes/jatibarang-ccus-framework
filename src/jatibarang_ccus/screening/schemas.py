from __future__ import annotations

from datetime import datetime, timezone
import itertools
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from jatibarang_ccus.contracts import (
    CO2Source,
    CarbonPriceScenario,
    Coordinate,
    EconomicAssumptions,
    EconomicBatchResult,
    EconomicProvenance,
    FacilityPortfolioResult,
    FiscalCase,
    PipelineDesignResult,
    TruckingSupplyResult,
)
from jatibarang_ccus.surrogate.schemas import (
    GeologyInput,
    OperatingSchedule,
    PredictRequest,
    PredictionResult,
    SeedHistory,
)


MAX_LOGICAL_SCENARIOS = 4096
MAX_DETAILED_PREDICTIONS = 10


class ProducedCO2Assumption(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    mole_fraction: float = Field(ge=0, le=1)
    provenance: EconomicProvenance


class ScreeningCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    candidate_id: str = Field(min_length=1)
    location: Coordinate
    geology_id: str = Field(min_length=1)
    seed_by_schedule_fingerprint: dict[str, str] = Field(min_length=1)
    produced_co2: ProducedCO2Assumption

    @model_validator(mode="after")
    def _fingerprints(self) -> "ScreeningCandidate":
        normalized: dict[str, str] = {}
        for fingerprint, seed_id in self.seed_by_schedule_fingerprint.items():
            value = fingerprint.upper()
            if len(value) != 64:
                raise ValueError("schedule fingerprint keys must contain 64 hexadecimal characters")
            try:
                int(value, 16)
            except ValueError as exc:
                raise ValueError("schedule fingerprint keys must be hexadecimal") from exc
            if not seed_id:
                raise ValueError("seed IDs must be non-empty")
            normalized[value] = seed_id
        self.seed_by_schedule_fingerprint = normalized
        return self


class OperationalGrid(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    injection_rate_m3_day: list[float] = Field(min_length=1)
    injection_duration_days: list[float] = Field(min_length=1)
    soak_duration_days: list[float] = Field(min_length=1)
    production_duration_days: list[float] = Field(min_length=1)
    production_bhp_psi: list[float] = Field(min_length=1)
    cycles: list[int] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_positive(self) -> "OperationalGrid":
        for name in (
            "injection_rate_m3_day",
            "injection_duration_days",
            "soak_duration_days",
            "production_duration_days",
            "production_bhp_psi",
            "cycles",
        ):
            values = getattr(self, name)
            if len(values) != len(set(values)):
                raise ValueError(f"{name} levels must be unique")
            if any(value <= 0 for value in values):
                raise ValueError(f"{name} levels must be positive")
        return self

    def expand(self) -> list[OperatingSchedule]:
        return [
            OperatingSchedule(
                injection_rate_m3_day=rate,
                injection_duration_days=injection_days,
                soak_duration_days=soak_days,
                production_duration_days=production_days,
                production_bhp_psi=bhp,
                cycles=cycles,
            )
            for rate, injection_days, soak_days, production_days, bhp, cycles in itertools.product(
                sorted(self.injection_rate_m3_day),
                sorted(self.injection_duration_days),
                sorted(self.soak_duration_days),
                sorted(self.production_duration_days),
                sorted(self.production_bhp_psi),
                sorted(self.cycles),
            )
        ]


class CommonScreenOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    run_id: str | None = Field(default=None, min_length=1, max_length=128)
    supply_scenarios: list[Literal["optimized_pipeline", "trucking_counterfactual"]] = Field(
        default_factory=lambda: ["optimized_pipeline", "trucking_counterfactual"], min_length=1
    )
    cost_case: Literal["low", "base", "high"] = "base"
    selection_fiscal_case_id: str = "pre_tax"
    shortlist_top_k: int = Field(default=5, ge=1, le=10)
    detailed_top_k: int = Field(default=5, ge=0, le=MAX_DETAILED_PREDICTIONS)
    scenario_limit: int = Field(default=MAX_LOGICAL_SCENARIOS, ge=1, le=MAX_LOGICAL_SCENARIOS)


class PresetScreenRequest(CommonScreenOptions):
    mode: Literal["preset"] = "preset"
    preset_id: Literal["jatibarang_demo_v1", "jatibarang_full_v1"]
    carbon_price_scenario_ids: list[str] | None = None
    fiscal_case_ids: list[str] | None = None


class InlineScreenRequest(CommonScreenOptions):
    mode: Literal["inline"] = "inline"
    geologies: dict[str, GeologyInput] = Field(min_length=1)
    seeds: dict[str, SeedHistory] = Field(min_length=1)
    candidates: list[ScreeningCandidate] = Field(min_length=1, max_length=20)
    sources: list[CO2Source] = Field(min_length=1)
    operational_grid: OperationalGrid | None = None
    schedules: list[OperatingSchedule] | None = None
    annual_co2_budget_tonnes: float = Field(gt=0)
    carbon_prices: list[CarbonPriceScenario] = Field(min_length=4)
    fiscal_cases: list[FiscalCase] = Field(min_length=1)
    economic_assumptions: EconomicAssumptions
    project_life_years: int = Field(default=8, ge=1, le=50)
    terrain_id: Literal["jatibarang_srtm_v1"] = "jatibarang_srtm_v1"
    routing_basis_id: Literal["jatibarang_case_study_v1"] = "jatibarang_case_study_v1"
    pipeline_basis_id: Literal["jatibarang_case_study_v1"] = "jatibarang_case_study_v1"

    @model_validator(mode="after")
    def _validate_dimensions(self) -> "InlineScreenRequest":
        if (self.operational_grid is None) == (self.schedules is None):
            raise ValueError("exactly one of operational_grid or schedules is required")
        dimensions = {
            "candidate": [item.candidate_id for item in self.candidates],
            "source": [item.id for item in self.sources],
            "carbon-price": [item.scenario_id for item in self.carbon_prices],
            "fiscal": [item.case_id for item in self.fiscal_cases],
        }
        for name, values in dimensions.items():
            if len(values) != len(set(values)):
                raise ValueError(f"{name} IDs must be unique")
        if self.selection_fiscal_case_id not in dimensions["fiscal"]:
            raise ValueError("selection_fiscal_case_id must be included in fiscal_cases")
        selection = next(item for item in self.fiscal_cases if item.case_id == self.selection_fiscal_case_id)
        if selection.mode != "pre_tax":
            raise ValueError("pipeline selection must use a pre-tax fiscal case")
        return self


ScreenRequest = Annotated[PresetScreenRequest | InlineScreenRequest, Field(discriminator="mode")]


class MaterializedScenario(BaseModel):
    scenario_id: str
    candidate_id: str
    location: Coordinate
    produced_co2: ProducedCO2Assumption
    schedule: OperatingSchedule
    predict_request: PredictRequest
    input_fingerprint: str


class ScreenFlag(BaseModel):
    code: str
    severity: Literal["info", "warning", "blocking"]
    source_module: str
    scenario_ids: list[str] = Field(default_factory=list)
    message: str


class InterferencePair(BaseModel):
    first_well_id: str
    second_well_id: str
    distance_m: float = Field(ge=0)
    radius_sum_m: float = Field(ge=0)
    overlap: bool
    recommendations: list[Literal["increase_spacing", "stagger_timing", "validate_with_full_simulation"]]


class InterferenceReport(BaseModel):
    well_ids: list[str]
    matrix: list[list[bool]]
    flagged_pairs: list[InterferencePair]


class SelectionDiscrepancyAudit(BaseModel):
    original_selected_wells: list[str]
    audit_selected_wells: list[str]
    entrants: list[str]
    exits: list[str]
    changed: bool
    original_objective_usd: float | None = None
    audit_objective_usd: float | None = None
    value_deltas_usd: dict[str, float] = Field(default_factory=dict)
    method: Literal["single_non_convergent_selected_set_counterfactual"] = (
        "single_non_convergent_selected_set_counterfactual"
    )


class WellStrategyResult(BaseModel):
    candidate_id: str
    scenario_id: str
    schedule: OperatingSchedule
    selected: bool
    annual_demand_tonnes: float = Field(ge=0)
    peak_mass_flow_kg_s: float = Field(ge=0)
    preliminary_npv_usd: float
    pre_logistics_value_usd: float
    prediction: PredictionResult
    facility: dict[str, Any] | None = None
    designated_economics: dict[str, Any] | None = None
    flags: list[ScreenFlag] = Field(default_factory=list)


class TruckingCounterfactual(BaseModel):
    supply: TruckingSupplyResult
    economics: EconomicBatchResult


class CarbonPricePlan(BaseModel):
    carbon_price_scenario_id: str
    carbon_price_usd_per_tonne: float = Field(ge=0)
    domain_status: str
    selected_wells: list[str]
    pipeline: PipelineDesignResult
    facility: FacilityPortfolioResult | None = None
    economics: EconomicBatchResult | None = None
    trucking_counterfactual: TruckingCounterfactual | None = None
    well_strategies: list[WellStrategyResult]
    interference: InterferenceReport
    discrepancy_audit: SelectionDiscrepancyAudit | None = None
    flags: list[ScreenFlag] = Field(default_factory=list)


class CrossPriceTransition(BaseModel):
    from_scenario_id: str
    to_scenario_id: str
    entrants: list[str]
    exits: list[str]


class CrossPriceComparison(BaseModel):
    selection_by_carbon_price: dict[str, list[str]]
    transitions: list[CrossPriceTransition]
    pivot_observed: bool


class ValidationShortlistItem(BaseModel):
    rank: int = Field(ge=1)
    candidate_id: str
    scenario_id: str
    carbon_price_scenario_ids: list[str]
    designated_npv_usd: float | None = None
    reasons: list[str]


class RunTimings(BaseModel):
    total_seconds: float = Field(ge=0)
    stages_seconds: dict[str, float] = Field(default_factory=dict)
    milp_solve_seconds: float = Field(default=0, ge=0)


class ScreenResult(BaseModel):
    run_id: str
    request_fingerprint: str
    status: Literal["completed", "completed_with_failures"]
    logical_scenario_count: int = Field(ge=1)
    unique_inference_count: int = Field(ge=1)
    inference_cache_hits: int = Field(ge=0)
    plans: list[CarbonPricePlan]
    cross_price_comparison: CrossPriceComparison
    shortlist: list[ValidationShortlistItem]
    detailed_predictions: dict[str, PredictionResult] = Field(default_factory=dict)
    timings: RunTimings
    warnings: list[str] = Field(default_factory=list)
    provenance_catalog: dict[str, Any] = Field(default_factory=dict)


ProgressEventType = Literal[
    "run_started",
    "stage_started",
    "progress",
    "stage_completed",
    "warning",
    "result",
    "error",
    "cancelled",
    "heartbeat",
]


class ProgressEvent(BaseModel):
    run_id: str
    sequence: int = Field(ge=0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event: ProgressEventType
    stage: str
    completed: int = Field(default=0, ge=0)
    total: int = Field(default=0, ge=0)
    message: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class PresetInfo(BaseModel):
    preset_id: Literal["jatibarang_demo_v1", "jatibarang_full_v1"]
    logical_scenarios: int
    geology_count: int
    schedule_count: int
    ready: bool
    manifest_path: str
    payload_sha256: str = ""
    reason: str = ""
    component_catalog: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: Literal["ready", "degraded"]
    surrogate_loaded: bool
    solver_available: bool
    active_runs: int = Field(ge=0)
    presets: list[PresetInfo]
    details: dict[str, Any] = Field(default_factory=dict)
