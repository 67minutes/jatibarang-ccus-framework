from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

import numpy as np

from .metadata import SCHEDULE_DISCRETIZATION, TRAINED_RANGES
from .schemas import ExtrapolationFlag, GeologyInput, OperatingSchedule, PredictRequest


BAR_TO_PSI = 14.503773773
SECONDS_PER_DAY = 86400.0


@dataclass(frozen=True)
class CompiledScenario:
    scenario_id: str
    schedule_fingerprint: str
    x_dynamic_seed: np.ndarray
    x_static: np.ndarray
    controls: np.ndarray
    dt_days: np.ndarray
    stages: np.ndarray
    cycles: np.ndarray
    elapsed_days: np.ndarray
    seed_oil_delta_m3: np.ndarray
    seed_gas_delta_m3: np.ndarray
    initial_pressure_bar: np.ndarray
    initial_gas_saturation: np.ndarray
    initial_z_co2: np.ndarray
    seed_pressure_bar: np.ndarray
    seed_gas_saturation: np.ndarray
    seed_z_co2: np.ndarray
    porosity: np.ndarray
    completion_mask: np.ndarray
    cell_volume_m3: float
    cell_area_m2: float
    reservoir_temperature_c: float
    injection_reference_pressure_bar: float
    injection_reference_temperature_c: float
    injection_rate_m3_day: float
    extrapolation_flags: tuple[ExtrapolationFlag, ...]
    seed_source_class: str
    seed_source_id: str

    @property
    def forecast_steps(self) -> int:
        return len(self.dt_days) - self.x_dynamic_seed.shape[0]


def schedule_fingerprint(schedule: OperatingSchedule) -> str:
    payload = schedule.model_dump(mode="json")
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest().upper()


def _schedule_vectors(schedule: OperatingSchedule) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    inject_count = SCHEDULE_DISCRETIZATION["inject_frames_per_cycle"]
    soak_count = SCHEDULE_DISCRETIZATION["soak_frames_per_cycle"]
    produce_count = SCHEDULE_DISCRETIZATION["produce_frames_per_cycle"]
    dt: list[float] = []
    stages: list[int] = []
    cycles: list[int] = []
    for cycle in range(1, schedule.cycles + 1):
        dt.extend([schedule.injection_duration_days / inject_count] * inject_count)
        stages.extend([1] * inject_count)
        cycles.extend([cycle] * inject_count)
        dt.extend([schedule.soak_duration_days / soak_count] * soak_count)
        stages.extend([2] * soak_count)
        cycles.extend([cycle] * soak_count)
        dt.extend([schedule.production_duration_days / produce_count] * produce_count)
        stages.extend([3] * produce_count)
        cycles.extend([cycle] * produce_count)
    return np.asarray(dt, dtype=np.float32), np.asarray(stages, dtype=np.int64), np.asarray(cycles, dtype=np.int64)


def _stage_phase_features(stages: np.ndarray, dt_days: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    progress = np.zeros_like(dt_days, dtype=np.float32)
    remaining = np.zeros_like(dt_days, dtype=np.float32)
    start = 0
    while start < len(stages):
        end = start + 1
        while end < len(stages) and stages[end] == stages[start]:
            end += 1
        segment_dt = dt_days[start:end]
        total = float(np.sum(segment_dt))
        elapsed_midpoint = np.cumsum(segment_dt, dtype=np.float32) - 0.5 * segment_dt
        progress[start:end] = np.clip(elapsed_midpoint / total, 0.0, 1.0)
        remaining[start:end] = np.clip((total - elapsed_midpoint) / total, 0.0, 1.0)
        start = end
    return progress, remaining


def _transition_features(stages: np.ndarray) -> tuple[np.ndarray, ...]:
    transitions = np.zeros_like(stages, dtype=np.int64)
    for index in range(1, len(stages)):
        previous, current = int(stages[index - 1]), int(stages[index])
        if previous == 3 and current == 1:
            transitions[index] = 1
        elif previous == 1 and current == 2:
            transitions[index] = 2
        elif previous == 2 and current == 3:
            transitions[index] = 3
    next_stage = np.empty_like(stages)
    next_stage[:-1] = stages[1:]
    next_stage[-1] = stages[-1]
    next_transition = np.zeros_like(transitions)
    next_transition[:-1] = transitions[1:]
    future_any = np.zeros_like(stages, dtype=np.float32)
    future_soak_produce = np.zeros_like(stages, dtype=np.float32)
    for index in range(len(stages)):
        future = transitions[index + 1 : min(index + 3, len(stages))]
        future_any[index] = float(np.any(future != 0))
        future_soak_produce[index] = float(np.any(future == 3))
    return (
        (next_stage == 1).astype(np.float32),
        (next_stage == 2).astype(np.float32),
        (next_stage == 3).astype(np.float32),
        (next_transition != 0).astype(np.float32),
        (next_transition == 3).astype(np.float32),
        future_any,
        future_soak_produce,
    )


def build_control_timeline(schedule: OperatingSchedule, stats: dict[str, Any]) -> tuple[np.ndarray, ...]:
    dt_days, stages, cycles = _schedule_vectors(schedule)
    elapsed = np.cumsum(dt_days, dtype=np.float32)
    progress, remaining = _stage_phase_features(stages, dt_days)
    transition = _transition_features(stages)
    controls = np.zeros((len(stages), 20), dtype=np.float32)
    controls[:, 3] = dt_days / float(stats["dt_max"])
    controls[:, 4] = stages == 1
    controls[:, 5] = stages == 2
    controls[:, 6] = stages == 3
    controls[:, 7] = (stages == 1) * (schedule.injection_rate_m3_day / float(stats["inj_rate_max"]))
    controls[:, 8] = (stages == 3) * (schedule.production_bhp_psi / float(stats["prod_bhp_max"]))
    controls[:, 9] = cycles / float(schedule.cycles)
    controls[:, 10] = elapsed / float(elapsed[-1])
    controls[:, 11] = progress
    controls[:, 12] = remaining
    for offset, values in enumerate(transition, start=13):
        controls[:, offset] = values
    return controls, dt_days, stages, cycles, elapsed


def _flag(quantity: str, observed: np.ndarray | float, bounds: tuple[float, float]) -> ExtrapolationFlag:
    values = np.asarray(observed, dtype=np.float64)
    observed_min = float(np.min(values))
    observed_max = float(np.max(values))
    return ExtrapolationFlag(
        quantity=quantity,
        observed_min=observed_min,
        observed_max=observed_max,
        trained_min=bounds[0],
        trained_max=bounds[1],
        is_extrapolation=observed_min < bounds[0] or observed_max > bounds[1],
    )


def extrapolation_flags(request: PredictRequest) -> tuple[ExtrapolationFlag, ...]:
    geology, schedule, seed = request.geology, request.schedule, request.seed
    porosity = geology.porosity_fraction.as_array()
    permeability = geology.permeability_md.as_array()
    seed_pressures_psi = np.stack([frame.pressure_bar.as_array() for frame in seed.frames]) * BAR_TO_PSI
    return (
        _flag("porosity_mean_fraction", float(np.mean(porosity)), TRAINED_RANGES["porosity_mean_fraction"]),
        _flag("porosity_cell_fraction", porosity, TRAINED_RANGES["porosity_cell_fraction"]),
        _flag("effective_permeability_md", permeability, TRAINED_RANGES["effective_permeability_md"]),
        _flag("injection_rate_m3_day", schedule.injection_rate_m3_day, TRAINED_RANGES["injection_rate_m3_day"]),
        _flag("injection_duration_days", schedule.injection_duration_days, TRAINED_RANGES["injection_duration_days"]),
        _flag("soak_duration_days", schedule.soak_duration_days, TRAINED_RANGES["soak_duration_days"]),
        _flag("production_duration_days", schedule.production_duration_days, TRAINED_RANGES["production_duration_days"]),
        _flag("production_bhp_psi", schedule.production_bhp_psi, TRAINED_RANGES["production_bhp_psi"]),
        _flag("cycles", float(schedule.cycles), TRAINED_RANGES["cycles"]),
        _flag("seed_pressure_psi", seed_pressures_psi, TRAINED_RANGES["seed_pressure_psi"]),
    )


def compile_request(request: PredictRequest, stats: dict[str, Any]) -> CompiledScenario:
    expected = schedule_fingerprint(request.schedule)
    if request.seed.schedule_fingerprint.upper() != expected:
        raise ValueError(f"seed schedule fingerprint mismatch: expected {expected}")

    geology = request.geology
    controls, dt_days, stages, cycles, elapsed = build_control_timeline(request.schedule, stats)
    static = np.stack(
        [
            (np.log10(geology.permeability_md.as_array()) - float(stats["perm_mean"])) / float(stats["perm_std"]),
            (geology.porosity_fraction.as_array() - float(stats["poro_mean"])) / float(stats["poro_std"]),
            geology.structure_m.as_array() / float(stats["structure_abs_max"]),
            geology.fracture_proxy.as_array(),
            geology.barrier.as_array(),
            (geology.facies.as_array() - 1.0) / 2.0,
            geology.well_mask.as_array(),
            geology.completion_mask.as_array(),
            np.full((64, 64), request.schedule.injection_rate_m3_day / float(stats["inj_rate_max"]), dtype=np.float32),
            np.full((64, 64), request.schedule.production_bhp_psi / float(stats["prod_bhp_max"]), dtype=np.float32),
            np.full((64, 64), request.schedule.cycles / float(stats["n_cycles_max"]), dtype=np.float32),
            np.full((64, 64), geology.anisotropy_ratio / float(stats["anisotropy_max"]), dtype=np.float32),
        ],
        axis=0,
    ).astype(np.float32)

    seed_pressure = np.stack([frame.pressure_bar.as_array() for frame in request.seed.frames]).astype(np.float32)
    seed_gas = np.stack([frame.gas_saturation.as_array() for frame in request.seed.frames]).astype(np.float32)
    seed_z = np.stack([frame.z_co2.as_array() for frame in request.seed.frames]).astype(np.float32)
    dynamic = np.broadcast_to(controls[:8, :, None, None], (8, 20, 64, 64)).copy()
    dynamic[:, 0] = (seed_pressure - float(stats["pressure_mean"])) / float(stats["pressure_std"])
    dynamic[:, 1] = seed_gas
    dynamic[:, 2] = seed_z

    initial = request.seed.initial_state
    return CompiledScenario(
        scenario_id=request.scenario_id,
        schedule_fingerprint=expected,
        x_dynamic_seed=dynamic.astype(np.float32),
        x_static=static,
        controls=controls,
        dt_days=dt_days,
        stages=stages,
        cycles=cycles,
        elapsed_days=elapsed,
        seed_oil_delta_m3=np.asarray(request.seed.oil_delta_m3, dtype=np.float32),
        seed_gas_delta_m3=np.asarray(request.seed.gas_delta_m3, dtype=np.float32),
        initial_pressure_bar=initial.pressure_bar.as_array(),
        initial_gas_saturation=initial.gas_saturation.as_array(),
        initial_z_co2=initial.z_co2.as_array(),
        seed_pressure_bar=seed_pressure,
        seed_gas_saturation=seed_gas,
        seed_z_co2=seed_z,
        porosity=geology.porosity_fraction.as_array(),
        completion_mask=geology.completion_mask.as_array(),
        cell_volume_m3=geology.cell_volume_m3,
        cell_area_m2=geology.length_x_m * geology.length_y_m / (64 * 64),
        reservoir_temperature_c=geology.reservoir_temperature_c,
        injection_reference_pressure_bar=request.schedule.injection_reference_pressure_bar,
        injection_reference_temperature_c=request.schedule.injection_reference_temperature_c,
        injection_rate_m3_day=request.schedule.injection_rate_m3_day,
        extrapolation_flags=extrapolation_flags(request),
        seed_source_class=request.seed.source_class,
        seed_source_id=request.seed.source_id,
    )
