from __future__ import annotations

import math
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator


GRID_SHAPE = (64, 64)
GRID_CELLS = GRID_SHAPE[0] * GRID_SHAPE[1]


class Grid2D(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    shape: tuple[int, int] = GRID_SHAPE
    values: list[float]

    @model_validator(mode="after")
    def validate_grid(self) -> "Grid2D":
        if tuple(self.shape) != GRID_SHAPE:
            raise ValueError(f"grid shape must be {GRID_SHAPE}")
        if len(self.values) != GRID_CELLS:
            raise ValueError(f"grid must contain exactly {GRID_CELLS} values")
        if not all(math.isfinite(value) for value in self.values):
            raise ValueError("grid values must be finite")
        return self

    def as_array(self, dtype: np.dtype = np.float32) -> np.ndarray:
        return np.asarray(self.values, dtype=dtype).reshape(GRID_SHAPE)

    @classmethod
    def from_array(cls, value: np.ndarray) -> "Grid2D":
        array = np.asarray(value, dtype=np.float32)
        if array.shape != GRID_SHAPE:
            raise ValueError(f"grid shape must be {GRID_SHAPE}")
        return cls(values=array.reshape(-1).astype(float).tolist())


class ReservoirState(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    pressure_bar: Grid2D
    gas_saturation: Grid2D
    z_co2: Grid2D

    @model_validator(mode="after")
    def validate_fractions(self) -> "ReservoirState":
        for name in ("gas_saturation", "z_co2"):
            values = np.asarray(getattr(self, name).values)
            if np.any((values < 0.0) | (values > 1.0)):
                raise ValueError(f"{name} values must be between 0 and 1")
        if min(self.pressure_bar.values) <= 0.0:
            raise ValueError("pressure values must be positive")
        return self


class GeologyInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    permeability_md: Grid2D
    porosity_fraction: Grid2D
    structure_m: Grid2D
    fracture_proxy: Grid2D
    barrier: Grid2D
    facies: Grid2D
    well_mask: Grid2D
    completion_mask: Grid2D
    anisotropy_ratio: float = Field(gt=0)
    reservoir_temperature_c: float = Field(gt=-273.15)
    length_x_m: float = Field(gt=0)
    length_y_m: float = Field(gt=0)
    thickness_m: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_physical_maps(self) -> "GeologyInput":
        if min(self.permeability_md.values) <= 0.0:
            raise ValueError("permeability must be positive")
        for name in ("porosity_fraction", "fracture_proxy", "barrier", "well_mask", "completion_mask"):
            values = np.asarray(getattr(self, name).values)
            if np.any((values < 0.0) | (values > 1.0)):
                raise ValueError(f"{name} values must be between 0 and 1")
        facies = np.asarray(self.facies.values)
        if np.any(~np.isin(facies, (1.0, 2.0, 3.0))):
            raise ValueError("facies values must be 1, 2, or 3")
        if max(self.completion_mask.values) <= 0.0:
            raise ValueError("completion_mask must contain at least one active cell")
        return self

    @property
    def cell_volume_m3(self) -> float:
        return self.length_x_m * self.length_y_m * self.thickness_m / GRID_CELLS


class OperatingSchedule(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    injection_rate_m3_day: float = Field(gt=0)
    injection_reference_pressure_bar: float = Field(default=1.01325, gt=0)
    injection_reference_temperature_c: float = Field(default=15.0, gt=-273.15)
    injection_duration_days: float = Field(gt=0)
    soak_duration_days: float = Field(gt=0)
    production_duration_days: float = Field(gt=0)
    production_bhp_psi: float = Field(gt=0)
    cycles: int = Field(gt=0, le=6)

    @property
    def total_steps(self) -> int:
        return self.cycles * 12


class SeedHistory(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    initial_state: ReservoirState
    frames: list[ReservoirState]
    oil_delta_m3: list[float]
    gas_delta_m3: list[float]
    source_class: Literal["mrst_ground_truth", "field_observation", "derived_seed"]
    source_id: str = Field(min_length=1)
    schedule_fingerprint: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def validate_history(self) -> "SeedHistory":
        if len(self.frames) != 8:
            raise ValueError("seed history must contain exactly eight frames")
        if len(self.oil_delta_m3) != 8 or len(self.gas_delta_m3) != 8:
            raise ValueError("seed production increments must contain exactly eight values")
        if any(not math.isfinite(value) or value < 0.0 for value in self.oil_delta_m3 + self.gas_delta_m3):
            raise ValueError("seed production increments must be finite and non-negative")
        return self


class PredictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    scenario_id: str = Field(min_length=1)
    geology: GeologyInput
    schedule: OperatingSchedule
    seed: SeedHistory


class BatchScenario(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    scenario_id: str = Field(min_length=1)
    geology_id: str = Field(min_length=1)
    seed_id: str = Field(min_length=1)
    schedule: OperatingSchedule


class BatchPredictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    geologies: dict[str, GeologyInput]
    seeds: dict[str, SeedHistory]
    scenarios: list[BatchScenario] = Field(min_length=1, max_length=256)
    full_field_scenario_ids: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def validate_registries(self) -> "BatchPredictRequest":
        scenario_ids = [scenario.scenario_id for scenario in self.scenarios]
        if len(set(scenario_ids)) != len(scenario_ids):
            raise ValueError("scenario IDs must be unique")
        for scenario in self.scenarios:
            if scenario.geology_id not in self.geologies:
                raise ValueError(f"unknown geology_id: {scenario.geology_id}")
            if scenario.seed_id not in self.seeds:
                raise ValueError(f"unknown seed_id: {scenario.seed_id}")
        unknown = set(self.full_field_scenario_ids) - set(scenario_ids)
        if unknown:
            raise ValueError(f"full-field IDs are not scenarios in this request: {sorted(unknown)}")
        return self


class ExtrapolationFlag(BaseModel):
    quantity: str
    observed_min: float
    observed_max: float
    trained_min: float
    trained_max: float
    is_extrapolation: bool
    evaluated: bool = True


class TimelineStep(BaseModel):
    index: int
    dt_days: float
    elapsed_days: float
    stage: Literal["inject", "soak", "produce"]
    cycle: int
    origin: Literal["seed", "surrogate", "mrst"]


class SpatialFrame(BaseModel):
    step_index: int
    pressure_bar: Grid2D
    gas_saturation: Grid2D
    z_co2: Grid2D
    oil_saturation: Grid2D | None = None
    origin: Literal["seed", "surrogate", "mrst"]


class ProductionSeries(BaseModel):
    delta_oil_m3: list[float]
    delta_gas_m3: list[float]
    cumulative_oil_m3: list[float]
    cumulative_gas_m3: list[float]


class InventorySeries(BaseModel):
    status: Literal["available", "unavailable"]
    co2_inventory_tonnes: list[float | None]
    injected_co2_tonnes: list[float]
    produced_back_co2_tonnes: list[float | None]
    reconciliation_residual_tonnes: list[float | None]
    method: str
    caveat: str


class PlumeSummary(BaseModel):
    maximum_z_co2_area_m2: float
    maximum_gas_area_m2: float
    influence_radius_m: float
    z_co2_threshold: float
    gas_saturation_threshold: float


class ConfidenceMetadata(BaseModel):
    band: str
    horizon_steps: int
    metrics: dict[str, float | int | str | None]
    extended_horizon: bool
    low_confidence_reasons: list[str]


class PredictionResult(BaseModel):
    scenario_id: str
    timeline: list[TimelineStep]
    production: ProductionSeries
    inventory: InventorySeries
    plume: PlumeSummary
    extrapolation_flags: list[ExtrapolationFlag]
    confidence: ConfidenceMetadata
    provenance: dict[str, str | int | float | bool]
    fields: list[SpatialFrame] | None = None


class BatchPredictionResult(BaseModel):
    results: list[PredictionResult]
    scenario_count: int
    full_field_scenario_ids: list[str]
    elapsed_seconds: float
