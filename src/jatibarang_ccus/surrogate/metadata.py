from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from .config import REPO_ROOT


DYNAMIC_CHANNELS: tuple[str, ...] = (
    "pressure_normalized",
    "gas_saturation",
    "z_co2",
    "dt_normalized",
    "stage_inject",
    "stage_soak",
    "stage_produce",
    "active_injection_rate_normalized",
    "active_production_bhp_normalized",
    "cycle_index_normalized",
    "elapsed_time_normalized",
    "stage_progress",
    "time_to_transition",
    "next_stage_inject",
    "next_stage_soak",
    "next_stage_produce",
    "next_transition_any",
    "next_transition_soak_to_produce",
    "future_transition_within_2",
    "future_soak_to_produce_within_2",
)

FORWARDED_DYNAMIC_CHANNELS: tuple[str, ...] = DYNAMIC_CHANNELS[:13]

STATIC_CHANNELS: tuple[str, ...] = (
    "log10_permeability_normalized",
    "porosity_normalized",
    "structure_normalized",
    "fracture_proxy",
    "barrier",
    "facies_normalized",
    "well_mask",
    "completion_mask",
    "injection_rate_normalized",
    "production_bhp_normalized",
    "cycle_count_normalized",
    "anisotropy_normalized",
)

TRAINED_RANGES: dict[str, tuple[float, float]] = {
    "porosity_mean_fraction": (0.17, 0.22),
    "porosity_cell_fraction": (0.14, 0.25),
    "effective_permeability_md": (10.0, 4000.0),
    "injection_rate_m3_day": (8000.0, 10000.0),
    "injection_duration_days": (45.0, 60.0),
    "soak_duration_days": (25.0, 35.0),
    "production_duration_days": (170.0, 210.0),
    "production_bhp_psi": (650.0, 700.0),
    "cycles": (3.0, 4.0),
    "seed_pressure_psi": (0.0, 2000.0),
}

SCHEDULE_DISCRETIZATION: dict[str, int] = {
    "inject_frames_per_cycle": 4,
    "soak_frames_per_cycle": 2,
    "produce_frames_per_cycle": 6,
}

PLUME_THRESHOLDS: dict[str, float] = {
    "z_co2": 0.02,
    "gas_saturation": 0.01,
}


@dataclass(frozen=True)
class AccuracyBand:
    name: str
    horizon_step: int | None
    pressure_r2: float
    pressure_rmse_bar: float
    gas_mass_error_pct: float
    z_co2_mass_error_pct: float
    gas_plume_iou: float
    z_co2_plume_iou: float


ACCURACY_METADATA_PATH = REPO_ROOT / "models" / "metadata" / "production_v2_accuracy.json"
_ACCURACY_METADATA = json.loads(ACCURACY_METADATA_PATH.read_text(encoding="utf-8"))
ACCURACY_BANDS: dict[str, AccuracyBand] = {
    key: AccuracyBand(**value) for key, value in _ACCURACY_METADATA["bands"].items()
}
UPSTREAM_METRICS_SOURCE = str(_ACCURACY_METADATA["source"])
UPSTREAM_METRICS_TEST_CASE_COUNT = int(_ACCURACY_METADATA["upstream_test_case_count"])
UPSTREAM_VALIDATED_ROLLOUT_STEPS = int(_ACCURACY_METADATA["upstream_validated_rollout_steps"])


def confidence_for_horizon(horizon: int) -> tuple[AccuracyBand, bool]:
    if horizon <= 1:
        return ACCURACY_BANDS["one_step"], False
    if horizon <= 5:
        return ACCURACY_BANDS["t_plus_5"], False
    if horizon <= 10:
        return ACCURACY_BANDS["t_plus_10"], False
    if horizon == 11:
        return ACCURACY_BANDS["t_plus_11"], False
    return ACCURACY_BANDS["last_24"], horizon > UPSTREAM_VALIDATED_ROLLOUT_STEPS


def public_metadata() -> dict[str, Any]:
    return {
        "dynamic_channels_stored": list(DYNAMIC_CHANNELS),
        "dynamic_channels_forwarded": list(FORWARDED_DYNAMIC_CHANNELS),
        "static_channels": list(STATIC_CHANNELS),
        "trained_ranges": {key: list(value) for key, value in TRAINED_RANGES.items()},
        "schedule_discretization": SCHEDULE_DISCRETIZATION,
        "plume_thresholds": PLUME_THRESHOLDS,
        "output_units": {
            "pressure": "bar",
            "saturations_and_composition": "fraction",
            "production_increment": "surface m3 per frame",
            "cumulative_production": "surface m3",
            "co2_inventory": "metric tonne",
            "plume_area": "m2",
            "influence_radius": "m",
        },
        "warm_start_frames": 8,
        "upstream_validated_rollout_steps": UPSTREAM_VALIDATED_ROLLOUT_STEPS,
        "upstream_metrics_source": UPSTREAM_METRICS_SOURCE,
        "accuracy_metadata_artifact": str(ACCURACY_METADATA_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
        "upstream_metrics_test_case_count": UPSTREAM_METRICS_TEST_CASE_COUNT,
        "accuracy_bands": {key: vars(value) for key, value in ACCURACY_BANDS.items()},
        "inventory_method": "porosity * cell_volume * gas_sat * z_co2 * CoolProp pure-CO2 density",
        "inventory_status": "engineering approximation; no dedicated produced-CO2 head",
    }
