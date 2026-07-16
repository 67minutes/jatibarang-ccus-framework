from __future__ import annotations

from dataclasses import asdict
from functools import lru_cache
from typing import TYPE_CHECKING

import CoolProp.CoolProp as CP
import numpy as np

from .metadata import PLUME_THRESHOLDS, confidence_for_horizon
from .preprocessing import CompiledScenario
from .schemas import (
    ConfidenceMetadata,
    Grid2D,
    InventorySeries,
    PlumeSummary,
    PredictionResult,
    ProductionSeries,
    SpatialFrame,
    TimelineStep,
)

if TYPE_CHECKING:
    from .runner import ScheduledPrediction, SurrogateRunner


CO2 = "CO2"


@lru_cache(maxsize=32)
def _density_table(temperature_c_rounded: float, pressure_min_bar: float, pressure_max_bar: float) -> tuple[np.ndarray, np.ndarray]:
    temperature_k = temperature_c_rounded + 273.15
    pressures = np.linspace(pressure_min_bar, pressure_max_bar, 256, dtype=np.float64)
    densities = np.asarray(
        [CP.PropsSI("D", "P", value * 1e5, "T", temperature_k, CO2) for value in pressures],
        dtype=np.float64,
    )
    return pressures, densities


def co2_density_kg_m3(pressure_bar: np.ndarray, temperature_c: float) -> np.ndarray:
    pressure = np.asarray(pressure_bar, dtype=np.float64)
    if not np.all(np.isfinite(pressure)) or np.any(pressure <= 0.0):
        raise ValueError("inventory density requires finite positive pressure")
    lower = max(0.05, float(np.min(pressure)) * 0.98)
    upper = max(lower + 0.1, float(np.max(pressure)) * 1.02)
    table_pressure, table_density = _density_table(round(float(temperature_c), 4), round(lower, 4), round(upper, 4))
    return np.interp(pressure, table_pressure, table_density).astype(np.float64)


def reservoir_inventory_tonnes(
    porosity: np.ndarray,
    gas_saturation: np.ndarray,
    z_co2: np.ndarray,
    density_kg_m3: np.ndarray,
    cell_volume_m3: float,
) -> np.ndarray:
    gas = np.asarray(gas_saturation, dtype=np.float64)
    composition = np.asarray(z_co2, dtype=np.float64)
    density = np.asarray(density_kg_m3, dtype=np.float64)
    pore_volume = np.asarray(porosity, dtype=np.float64) * float(cell_volume_m3)
    if gas.ndim == 2:
        gas = gas[None]
        composition = composition[None]
        density = density[None]
    return np.sum(pore_volume[None] * gas * composition * density, axis=(-2, -1)) / 1000.0


def _inventory_series(
    compiled: CompiledScenario,
    prediction: "ScheduledPrediction",
) -> InventorySeries:
    pressure = np.concatenate([compiled.seed_pressure_bar, prediction.pred_pressure_bar], axis=0)
    gas = np.concatenate([compiled.seed_gas_saturation, prediction.pred_normalized[:, 1]], axis=0)
    z_co2 = np.concatenate([compiled.seed_z_co2, prediction.pred_normalized[:, 2]], axis=0)
    try:
        initial_density = co2_density_kg_m3(compiled.initial_pressure_bar, compiled.reservoir_temperature_c)
        density = co2_density_kg_m3(pressure, compiled.reservoir_temperature_c)
        initial_inventory = float(
            reservoir_inventory_tonnes(
                compiled.porosity,
                compiled.initial_gas_saturation,
                compiled.initial_z_co2,
                initial_density,
                compiled.cell_volume_m3,
            )[0]
        )
        inventory = reservoir_inventory_tonnes(
            compiled.porosity,
            gas,
            z_co2,
            density,
            compiled.cell_volume_m3,
        )
        reference_density = float(
            CP.PropsSI(
                "D",
                "P",
                compiled.injection_reference_pressure_bar * 1e5,
                "T",
                compiled.injection_reference_temperature_c + 273.15,
                CO2,
            )
        )
        horizon = len(inventory)
        injected_delta = (
            (compiled.stages[:horizon] == 1).astype(np.float64)
            * compiled.injection_rate_m3_day
            * compiled.dt_days[:horizon]
            * reference_density
            / 1000.0
        )
        injected = np.cumsum(injected_delta)
        inventory_gain = inventory - initial_inventory
        produced_back = np.maximum(0.0, injected - inventory_gain)
        residual = initial_inventory + injected - produced_back - inventory
        return InventorySeries(
            status="available",
            co2_inventory_tonnes=inventory.astype(float).tolist(),
            injected_co2_tonnes=injected.astype(float).tolist(),
            produced_back_co2_tonnes=produced_back.astype(float).tolist(),
            reconciliation_residual_tonnes=residual.astype(float).tolist(),
            method="porosity * cell_volume * gas_sat * z_co2 * CoolProp pure-CO2 density",
            caveat=(
                "Engineering approximation: z_co2 is a surrogate composition field, "
                "not a dedicated produced-CO2 head; dissolved/liquid-phase partitioning is not resolved."
            ),
        )
    except (ValueError, RuntimeError, OverflowError) as exc:
        count = len(pressure)
        return InventorySeries(
            status="unavailable",
            co2_inventory_tonnes=[None] * count,
            injected_co2_tonnes=[0.0] * count,
            produced_back_co2_tonnes=[None] * count,
            reconciliation_residual_tonnes=[None] * count,
            method="unavailable",
            caveat=f"Inventory post-processing failed: {exc}",
        )


def plume_summary(
    gas_saturation: np.ndarray,
    z_co2: np.ndarray,
    completion_mask: np.ndarray,
    *,
    cell_area_m2: float,
) -> PlumeSummary:
    gas = np.asarray(gas_saturation)
    composition = np.asarray(z_co2)
    z_active = composition >= PLUME_THRESHOLDS["z_co2"]
    gas_active = gas >= PLUME_THRESHOLDS["gas_saturation"]
    maximum_z_area = float(np.max(np.sum(z_active, axis=(-2, -1))) * cell_area_m2)
    maximum_gas_area = float(np.max(np.sum(gas_active, axis=(-2, -1))) * cell_area_m2)

    completion = np.argwhere(np.asarray(completion_mask) >= 0.5)
    active = np.argwhere(np.any(z_active, axis=0))
    influence_radius = 0.0
    if len(completion) and len(active):
        cell_size = float(np.sqrt(cell_area_m2))
        differences = active[:, None, :] - completion[None, :, :]
        distances = np.sqrt(np.sum(np.square(differences), axis=2)) * cell_size
        influence_radius = float(np.max(np.min(distances, axis=1)))
    return PlumeSummary(
        maximum_z_co2_area_m2=maximum_z_area,
        maximum_gas_area_m2=maximum_gas_area,
        influence_radius_m=influence_radius,
        z_co2_threshold=PLUME_THRESHOLDS["z_co2"],
        gas_saturation_threshold=PLUME_THRESHOLDS["gas_saturation"],
    )


def build_prediction_result(
    compiled: CompiledScenario,
    prediction: "ScheduledPrediction",
    runner: "SurrogateRunner",
    *,
    include_fields: bool,
) -> PredictionResult:
    horizon = prediction.horizon_steps
    total_steps = 8 + horizon
    all_gas = np.concatenate([compiled.seed_gas_saturation, prediction.pred_normalized[:, 1]], axis=0)
    all_z = np.concatenate([compiled.seed_z_co2, prediction.pred_normalized[:, 2]], axis=0)
    plume = plume_summary(
        all_gas,
        all_z,
        compiled.completion_mask,
        cell_area_m2=compiled.cell_area_m2,
    )
    inventory = _inventory_series(compiled, prediction)
    band, extended = confidence_for_horizon(horizon)
    reasons: list[str] = []
    if extended:
        reasons.append("forecast extends beyond the pinned 24-step upstream validation horizon")
    if any(flag.is_extrapolation for flag in compiled.extrapolation_flags):
        reasons.append("one or more physical inputs are outside the training range")
    if compiled.seed_source_class == "derived_seed":
        reasons.append("warm-start history is a derived seed rather than MRST ground truth or field observation")
    if inventory.status == "unavailable":
        reasons.append("CO2 inventory calculation is unavailable")

    timeline = [
        TimelineStep(
            index=index,
            dt_days=float(compiled.dt_days[index]),
            elapsed_days=float(compiled.elapsed_days[index]),
            stage=("inject", "soak", "produce")[int(compiled.stages[index]) - 1],
            cycle=int(compiled.cycles[index]),
            origin="seed" if index < 8 else "surrogate",
        )
        for index in range(total_steps)
    ]

    fields: list[SpatialFrame] | None = None
    if include_fields:
        fields = []
        for index in range(8):
            fields.append(
                SpatialFrame(
                    step_index=index,
                    pressure_bar=Grid2D.from_array(compiled.seed_pressure_bar[index]),
                    gas_saturation=Grid2D.from_array(compiled.seed_gas_saturation[index]),
                    z_co2=Grid2D.from_array(compiled.seed_z_co2[index]),
                    oil_saturation=None,
                    origin="seed",
                )
            )
        for offset in range(horizon):
            fields.append(
                SpatialFrame(
                    step_index=8 + offset,
                    pressure_bar=Grid2D.from_array(prediction.pred_pressure_bar[offset]),
                    gas_saturation=Grid2D.from_array(prediction.pred_normalized[offset, 1]),
                    z_co2=Grid2D.from_array(prediction.pred_normalized[offset, 2]),
                    oil_saturation=Grid2D.from_array(prediction.pred_normalized[offset, 3]),
                    origin="surrogate",
                )
            )

    info = runner.model_info()
    metrics = asdict(band)
    return PredictionResult(
        scenario_id=compiled.scenario_id,
        timeline=timeline,
        production=ProductionSeries(
            delta_oil_m3=prediction.oil_delta_m3.astype(float).tolist(),
            delta_gas_m3=prediction.gas_delta_m3.astype(float).tolist(),
            cumulative_oil_m3=prediction.cumulative_oil_m3.astype(float).tolist(),
            cumulative_gas_m3=prediction.cumulative_gas_m3.astype(float).tolist(),
        ),
        inventory=inventory,
        plume=plume,
        extrapolation_flags=list(compiled.extrapolation_flags),
        confidence=ConfidenceMetadata(
            band=band.name,
            horizon_steps=horizon,
            metrics=metrics,
            extended_horizon=extended,
            low_confidence_reasons=reasons,
        ),
        provenance={
            "source_class": "surrogate_prediction",
            "checkpoint_sha256": info.checkpoint_sha256,
            "checkpoint_run_name": info.checkpoint_run_name,
            "output_contract": info.output_contract,
            "seed_source_class": compiled.seed_source_class,
            "seed_source_id": compiled.seed_source_id,
            "schedule_fingerprint": compiled.schedule_fingerprint,
            "cpu_only": True,
        },
        fields=fields,
    )
