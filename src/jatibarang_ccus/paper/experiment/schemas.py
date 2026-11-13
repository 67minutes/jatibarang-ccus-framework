from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable, Literal, Sequence, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator


SourceClass = Literal[
    "surrogate_prediction",
    "arm_c_integrated_result",
    "mrst_and_surrogate_integrated_result",
    "mrst_truth_and_surrogate_prediction",
    "measured_runtime",
    "dwsim_truth",
    "screening_cost_proxy",
]
APPROVED_SOURCE_CLASSES = set(SourceClass.__args__)


class ExperimentRow(BaseModel):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)

    source_class: SourceClass


class ScreeningSurfaceRow(ExperimentRow):
    geology_id: str
    mean_permeability_md: float = Field(gt=0)
    injection_rate_m3_day: float = Field(gt=0)
    incremental_oil_m3: float
    co2_retention_fraction: float = Field(ge=0, le=1)
    cycles: int = Field(ge=1)
    sample_count: int = Field(ge=1)
    incremental_oil_p10_m3: float
    incremental_oil_p90_m3: float
    co2_retention_p10_fraction: float = Field(ge=0, le=1)
    co2_retention_p90_fraction: float = Field(ge=0, le=1)


class PipelineRouteRow(ExperimentRow):
    route_id: str
    point_order: int = Field(ge=0)
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    node_type: str = ""
    mode: str = ""
    selected: bool = False
    reason: str = ""
    route_method: str = "srtm_astar_and_arm_c_milp_result"


class PipelinePressureRow(ExperimentRow):
    route_id: str
    distance_km: float = Field(ge=0)
    pressure_bar: float = Field(gt=0)
    dense_phase_floor_bar: float = Field(gt=0)
    maop_bar: float = Field(gt=0)
    pressure_method: str = "coolprop_continuous_pressure_audit"

    @model_validator(mode="after")
    def _valid_pressure_envelope(self) -> "PipelinePressureRow":
        if self.dense_phase_floor_bar > self.maop_bar:
            raise ValueError("dense-phase floor cannot exceed MAOP")
        return self


class PipelineCostCrossoverRow(ExperimentRow):
    annual_tonnes: float = Field(gt=0)
    mode: Literal["trucking", "pipeline_direct", "hybrid_trunk_truck"]
    cost_case: Literal["low", "base", "high"]
    levelized_usd_per_tonne: float = Field(ge=0)
    hydraulically_admissible: bool
    diameter_in: float | None = Field(default=None, gt=0)


class CarbonPriceRankingRow(ExperimentRow):
    scenario_id: str
    carbon_price_usd_per_tonne: float = Field(ge=0)
    rank: int = Field(ge=1)
    independent_rank_p10: float = Field(ge=1)
    independent_rank_p90: float = Field(ge=1)
    independent_npv_mean_usd: float
    independent_npv_p10_usd: float
    independent_npv_p90_usd: float
    independent_assignment_count: int = Field(ge=1)
    correlated_rank: int = Field(ge=1)
    correlated_npv_median_usd: float


class NpvVsCarbonPriceRow(ExperimentRow):
    scenario_id: str
    carbon_price_usd_per_tonne: float = Field(ge=0)
    npv_usd: float
    npv_low_usd: float
    npv_high_usd: float
    correlated_npv_usd: float | None = None


class CarbonPriceRegretRow(ExperimentRow):
    chosen_price_scenario: str
    realized_price_scenario: str
    regret_usd: float = Field(ge=0)
    regret_p10_usd: float = Field(ge=0)
    regret_p90_usd: float = Field(ge=0)
    correlated_regret_usd: float | None = Field(default=None, ge=0)


class AbcEconomicsRow(ExperimentRow):
    arm: Literal["A", "B", "C"]
    carbon_price_usd_per_tonne: float = Field(ge=0)
    npv_usd: float
    npv_low_usd: float
    npv_high_usd: float
    irr: float | None = None
    payback_years: float | None = None
    breakeven_carbon_usd_per_tonne: float | None = None
    breakeven_oil_usd_per_bbl: float | None = None
    fiscal_case: str
    valid_metric_count: int = Field(default=1, ge=0)
    npv_valid_count: int = Field(default=1, ge=1)
    irr_valid_count: int = Field(default=0, ge=0)
    payback_valid_count: int = Field(default=0, ge=0)
    breakeven_carbon_valid_count: int = Field(default=0, ge=0)
    breakeven_oil_valid_count: int = Field(default=0, ge=0)


class AbcRuntimeRow(ExperimentRow):
    arm: Literal["A", "B", "C"]
    wall_clock_seconds: float = Field(ge=0)
    scenarios_evaluated: int = Field(ge=1)
    economics_scenarios: int = Field(ge=1)
    accepted_runs: int = Field(ge=0)
    attempted_runs: int = Field(ge=0)
    failed_attempt_seconds: float = Field(default=0, ge=0)
    downstream_resolve_seconds: float = Field(default=0, ge=0)
    mrst_equivalence_weeks: float | None = Field(default=None, ge=0)
    runtime_kind: str


class TopKConfirmationRow(ExperimentRow):
    plan_id: str
    designated_carbon_price_scenario_id: str
    carbon_price_usd_per_tonne: float = Field(ge=0)
    fiscal_case: str
    surrogate_value: float
    mrst_value: float
    relative_error: float
    absolute_relative_error: float = Field(ge=0)
    throughput_class: Literal["minimum", "median", "maximum"] | None = None
    dwsim_converged: bool | None = None
    dwsim_total_power_kw: float | None = Field(default=None, ge=0)
    dwsim_cooling_duty_kw: float | None = None
    dwsim_mass_balance_residual_fraction: float | None = Field(
        default=None,
        ge=0,
    )


class DwsimConfirmationRow(ExperimentRow):
    plan_id: str
    throughput_class: Literal["minimum", "median", "maximum"]
    total_design_mass_flow_kg_s: float = Field(gt=0)
    case_id: str
    converged: bool
    dwsim_version: str = Field(min_length=1)
    model_sha256: str = Field(min_length=64, max_length=64)
    cases_sha256: str = Field(min_length=64, max_length=64)
    property_package: Literal["CoolProp"]
    compressor_power_kw: float = Field(ge=0)
    pump_power_kw: float = Field(ge=0)
    total_power_kw: float = Field(ge=0)
    cooling_duty_kw: float
    separator_gas_std_m3_day: float = Field(ge=0)
    inlet_mass_kg_s: float = Field(gt=0)
    outlet_mass_kg_s: float = Field(gt=0)
    mass_balance_residual_fraction: float = Field(ge=0, le=0.001)
    error_message: str = ""


class MrstDesignAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    attempt_id: str
    candidate_id: str
    source_case_id: str
    schedule: dict[str, float | int]


class MrstDesignSlot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot_id: str
    candidate_id: str
    source_case_id: str
    geology_params: dict[str, float | int]
    attempts: list[MrstDesignAttempt] = Field(min_length=1)
    replacement_allowed: bool


class MrstDesign(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["feature007-mrst-design-v1"] = (
        "feature007-mrst-design-v1"
    )
    arm: Literal["A", "B", "C_TOP5"]
    target_accepted: int = Field(ge=1)
    slots: list[MrstDesignSlot] = Field(min_length=1)
    source_design_sha256: str = Field(min_length=64, max_length=64)
    design_sha256: str = ""

    @model_validator(mode="after")
    def _slot_target(self) -> "MrstDesign":
        if len(self.slots) != self.target_accepted:
            raise ValueError("MRST design requires one slot per accepted target")
        if len({slot.slot_id for slot in self.slots}) != len(self.slots):
            raise ValueError("MRST design slot IDs must be unique")
        return self


class MrstManifestEntry(BaseModel):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)

    slot_id: str
    attempt_id: str
    candidate_id: str
    source_case_id: str
    status: Literal["accepted", "failed"]
    runtime_seconds: float = Field(ge=0)
    output_file: str = ""
    output_sha256: str = ""
    solver_converged: bool
    expected_step_count: int = Field(ge=1)
    actual_step_count: int = Field(ge=0)
    finite_arrays: bool
    sanity_passed: bool
    failure_reason: str = ""


class MrstManifest(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: Literal["feature007-mrst-manifest-v1"]
    arm: Literal["A", "B", "C_TOP5"]
    design_sha256: str = Field(min_length=64, max_length=64)
    target_accepted: int = Field(ge=1)
    accepted_runs: int = Field(ge=0)
    failed_runs: int = Field(ge=0)
    failed_hashes: list[str] = Field(default_factory=list)
    entries: list[MrstManifestEntry]
    generator_sha256_before: str = Field(min_length=64, max_length=64)
    generator_sha256_after: str = Field(min_length=64, max_length=64)


RowT = TypeVar("RowT", bound=BaseModel)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest().upper()


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        value,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def atomic_write_csv(
    path: Path,
    rows: Iterable[RowT | dict[str, Any]],
    *,
    model: type[RowT],
    field_order: Sequence[str] | None = None,
) -> int:
    validated = [model.model_validate(row) for row in rows]
    if not validated:
        raise ValueError(f"refusing to write empty experiment table: {path.name}")
    columns = list(field_order or model.model_fields)
    extras = sorted(
        {
            key
            for row in validated
            for key in row.model_extra or {}
            if key not in columns
        }
    )
    columns.extend(extras)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            for value in validated:
                payload = value.model_dump(mode="json")
                for key, item in payload.items():
                    if isinstance(item, float) and not math.isfinite(item):
                        raise ValueError(f"{path.name} contains non-finite {key}")
                writer.writerow({key: payload.get(key, "") for key in columns})
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return len(validated)


def read_validated_csv(
    path: Path,
    *,
    model: type[RowT],
) -> list[RowT]:
    """Read a complete CSV and validate every row against its locked model."""

    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"experiment table is empty: {path.name}")
    nullable = {
        name
        for name, field in model.model_fields.items()
        if field.default is None
    }
    normalized = [
        {
            key: (None if key in nullable and value == "" else value)
            for key, value in row.items()
        }
        for row in rows
    ]
    return [model.model_validate(row) for row in normalized]
