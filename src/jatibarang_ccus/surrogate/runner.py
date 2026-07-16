from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import torch

from .config import CHANNEL_CONTRACT, PROMOTED_CHECKPOINT, PROMOTED_CHECKPOINT_SHA256
from .model_hnp import HNPSurrogateModel
from .preprocessing import CompiledScenario, SECONDS_PER_DAY


@dataclass(frozen=True)
class ModelInfo:
    checkpoint_path: str
    checkpoint_sha256: str
    checkpoint_run_name: str
    output_contract: str
    tin: int
    stored_dynamic_channels: int
    forward_dynamic_channels: int
    static_channels: int
    model_kwargs: dict[str, Any]


@dataclass(frozen=True)
class SurrogatePrediction:
    pred: np.ndarray
    pred_delta_norm: np.ndarray
    pred_delta_raw: np.ndarray | None
    stage: np.ndarray


@dataclass(frozen=True)
class ScheduledPrediction:
    scenario_id: str
    pred_normalized: np.ndarray
    pred_pressure_bar: np.ndarray
    pred_delta_normalized: np.ndarray
    forecast_oil_delta_m3: np.ndarray
    forecast_gas_delta_m3: np.ndarray
    oil_delta_m3: np.ndarray
    gas_delta_m3: np.ndarray
    cumulative_oil_m3: np.ndarray
    cumulative_gas_m3: np.ndarray
    stages: np.ndarray

    @property
    def horizon_steps(self) -> int:
        return int(self.pred_normalized.shape[0])


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def verify_checkpoint(path: Path = PROMOTED_CHECKPOINT) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Promoted checkpoint is missing: {path}")
    digest = sha256_file(path)
    if digest != PROMOTED_CHECKPOINT_SHA256:
        raise ValueError(
            f"Checkpoint SHA256 mismatch for {path}: expected {PROMOTED_CHECKPOINT_SHA256}, got {digest}"
        )
    return digest


def _to_numpy(value: np.ndarray | torch.Tensor) -> np.ndarray:
    if isinstance(value, torch.Tensor):
        return value.detach().cpu().numpy()
    return np.asarray(value)


class SurrogateRunner:
    def __init__(self, checkpoint_path: Path = PROMOTED_CHECKPOINT, device: str = "cpu") -> None:
        self.checkpoint_path = Path(checkpoint_path)
        self.checkpoint_sha256 = verify_checkpoint(self.checkpoint_path)
        self.device = torch.device(device)
        if self.device.type != "cpu":
            raise ValueError("Phase 1 surrogate inference is CPU-only.")

        checkpoint = torch.load(self.checkpoint_path, map_location=self.device)
        self.checkpoint = checkpoint
        model_kwargs = dict(checkpoint["model_kwargs"])
        self.model = HNPSurrogateModel(variant=checkpoint["model_variant"], **model_kwargs).to(self.device)
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.model.eval()

    def model_info(self) -> ModelInfo:
        return ModelInfo(
            checkpoint_path=str(self.checkpoint_path),
            checkpoint_sha256=self.checkpoint_sha256,
            checkpoint_run_name=str(self.checkpoint.get("run_name", "")),
            output_contract=str(self.checkpoint.get("output_contract", "")),
            tin=int(self.checkpoint.get("tin", CHANNEL_CONTRACT.tin)),
            stored_dynamic_channels=CHANNEL_CONTRACT.stored_dynamic_channels,
            forward_dynamic_channels=CHANNEL_CONTRACT.forward_dynamic_channels,
            static_channels=CHANNEL_CONTRACT.static_channels,
            model_kwargs=dict(self.checkpoint["model_kwargs"]),
        )

    def predict_one_step(
        self,
        x_dyn: np.ndarray | torch.Tensor,
        x_static: np.ndarray | torch.Tensor,
        *,
        stage: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        x_dyn_t = torch.as_tensor(_to_numpy(x_dyn), dtype=torch.float32, device=self.device).unsqueeze(0)
        x_static_t = torch.as_tensor(_to_numpy(x_static), dtype=torch.float32, device=self.device).unsqueeze(0)
        stage_context = torch.tensor([int(stage)], dtype=torch.long, device=self.device)
        with torch.inference_mode():
            pred, aux = self.model(x_dyn_t, x_static_t, stage_context=stage_context, return_aux=True)
        return (
            pred[0].detach().cpu().numpy().astype(np.float32),
            aux["production_delta"][0].detach().cpu().numpy().astype(np.float32),
        )

    def predict_seed(
        self,
        x_dyn: np.ndarray | torch.Tensor,
        x_static: np.ndarray | torch.Tensor,
        *,
        rollout_len: int = 24,
        stage_sequence: list[int] | np.ndarray | None = None,
        production_delta_scale: np.ndarray | None = None,
    ) -> SurrogatePrediction:
        dynamic = _to_numpy(x_dyn).astype(np.float32).copy()
        x_static_np = _to_numpy(x_static).astype(np.float32)
        if dynamic.shape[0] != CHANNEL_CONTRACT.tin:
            raise ValueError(f"Expected Tin={CHANNEL_CONTRACT.tin}, got {dynamic.shape[0]}")
        if dynamic.shape[1] != CHANNEL_CONTRACT.stored_dynamic_channels:
            raise ValueError(
                f"Expected {CHANNEL_CONTRACT.stored_dynamic_channels} stored dynamic channels, got {dynamic.shape[1]}"
            )
        if x_static_np.shape[0] != CHANNEL_CONTRACT.static_channels:
            raise ValueError(f"Expected {CHANNEL_CONTRACT.static_channels} static channels, got {x_static_np.shape[0]}")

        if stage_sequence is None:
            last_stage = int(np.argmax(dynamic[-1, 4:7, 0, 0]) + 1)
            stages = np.full(rollout_len, last_stage, dtype=np.int64)
        else:
            stages = np.asarray(stage_sequence, dtype=np.int64)
            if len(stages) < rollout_len:
                raise ValueError("stage_sequence must be at least rollout_len long")
            stages = stages[:rollout_len]

        seq = dynamic.copy()
        preds: list[np.ndarray] = []
        deltas: list[np.ndarray] = []
        for step in range(rollout_len):
            pred, delta = self.predict_one_step(seq[-CHANNEL_CONTRACT.tin :], x_static_np, stage=int(stages[step]))
            preds.append(pred)
            deltas.append(delta)
            next_frame = seq[-1].copy()
            next_frame[0] = pred[0]
            next_frame[1] = pred[1]
            next_frame[2] = pred[2]
            next_frame[4:7] = 0.0
            next_frame[3 + int(stages[step])] = 1.0
            seq = np.concatenate([seq, next_frame[None]], axis=0)

        delta_norm = np.stack(deltas, axis=0).astype(np.float32)
        delta_raw = None
        if production_delta_scale is not None:
            delta_raw = (delta_norm * np.asarray(production_delta_scale, dtype=np.float32)[None, :]).astype(np.float32)

        return SurrogatePrediction(
            pred=np.stack(preds, axis=0).astype(np.float32),
            pred_delta_norm=delta_norm,
            pred_delta_raw=delta_raw,
            stage=stages,
        )

    def _scheduled_prediction(
        self,
        compiled: CompiledScenario,
        pred: np.ndarray,
        delta_norm: np.ndarray,
    ) -> ScheduledPrediction:
        stats = self.checkpoint["stats"]
        scale = np.asarray([stats["delta_oil_max"], stats["delta_gas_max"]], dtype=np.float32)
        physical_delta = delta_norm * scale[None, :] * SECONDS_PER_DAY
        forecast_oil = physical_delta[:, 0].astype(np.float32)
        forecast_gas = physical_delta[:, 1].astype(np.float32)
        oil_delta = np.concatenate([compiled.seed_oil_delta_m3, forecast_oil]).astype(np.float32)
        gas_delta = np.concatenate([compiled.seed_gas_delta_m3, forecast_gas]).astype(np.float32)
        pressure = (pred[:, 0] * float(stats["pressure_std"]) + float(stats["pressure_mean"])).astype(np.float32)
        horizon = len(pred)
        return ScheduledPrediction(
            scenario_id=compiled.scenario_id,
            pred_normalized=pred.astype(np.float32),
            pred_pressure_bar=pressure,
            pred_delta_normalized=delta_norm.astype(np.float32),
            forecast_oil_delta_m3=forecast_oil,
            forecast_gas_delta_m3=forecast_gas,
            oil_delta_m3=oil_delta,
            gas_delta_m3=gas_delta,
            cumulative_oil_m3=np.cumsum(oil_delta, dtype=np.float64).astype(np.float32),
            cumulative_gas_m3=np.cumsum(gas_delta, dtype=np.float64).astype(np.float32),
            stages=compiled.stages[: 8 + horizon].copy(),
        )

    def predict_compiled(
        self,
        compiled: CompiledScenario,
        *,
        max_forecast_steps: int | None = None,
    ) -> ScheduledPrediction:
        return self.predict_compiled_batch(
            [compiled],
            microbatch_size=1,
            max_forecast_steps=max_forecast_steps,
        )[0]

    def predict_compiled_batch(
        self,
        scenarios: list[CompiledScenario],
        *,
        microbatch_size: int = 16,
        max_forecast_steps: int | None = None,
    ) -> list[ScheduledPrediction]:
        if not scenarios:
            return []
        if microbatch_size <= 0:
            raise ValueError("microbatch_size must be positive")

        indexed = list(enumerate(scenarios))
        groups: dict[int, list[tuple[int, CompiledScenario]]] = {}
        for item in indexed:
            full_horizon = item[1].forecast_steps
            horizon = min(full_horizon, max_forecast_steps) if max_forecast_steps is not None else full_horizon
            if horizon <= 0:
                raise ValueError("forecast horizon must be positive")
            groups.setdefault(horizon, []).append(item)

        ordered: list[ScheduledPrediction | None] = [None] * len(scenarios)
        for horizon, group in groups.items():
            for start in range(0, len(group), microbatch_size):
                chunk = group[start : start + microbatch_size]
                chunk_scenarios = [item[1] for item in chunk]
                sequence = torch.as_tensor(
                    np.stack([item.x_dynamic_seed for item in chunk_scenarios]),
                    dtype=torch.float32,
                    device=self.device,
                )
                static = torch.as_tensor(
                    np.stack([item.x_static for item in chunk_scenarios]),
                    dtype=torch.float32,
                    device=self.device,
                )
                pred_steps: list[np.ndarray] = []
                delta_steps: list[np.ndarray] = []
                with torch.inference_mode():
                    for step in range(horizon):
                        target_index = CHANNEL_CONTRACT.tin + step
                        stages = torch.as_tensor(
                            [int(item.stages[target_index]) for item in chunk_scenarios],
                            dtype=torch.long,
                            device=self.device,
                        )
                        pred, aux = self.model(sequence, static, stage_context=stages, return_aux=True)
                        pred_np = pred.detach().cpu().numpy().astype(np.float32)
                        delta_np = aux["production_delta"].detach().cpu().numpy().astype(np.float32)
                        pred_steps.append(pred_np)
                        delta_steps.append(delta_np)

                        next_controls = np.stack([item.controls[target_index] for item in chunk_scenarios])
                        next_frame = torch.as_tensor(
                            np.broadcast_to(next_controls[:, :, None, None], (len(chunk), 20, 64, 64)).copy(),
                            dtype=torch.float32,
                            device=self.device,
                        )
                        next_frame[:, 0] = pred[:, 0]
                        next_frame[:, 1] = pred[:, 1]
                        next_frame[:, 2] = pred[:, 2]
                        sequence = torch.cat([sequence[:, 1:], next_frame[:, None]], dim=1)

                pred_array = np.stack(pred_steps, axis=1)
                delta_array = np.stack(delta_steps, axis=1)
                for local_index, (original_index, compiled) in enumerate(chunk):
                    ordered[original_index] = self._scheduled_prediction(
                        compiled,
                        pred_array[local_index],
                        delta_array[local_index],
                    )

        return [item for item in ordered if item is not None]

    def info_dict(self) -> dict[str, Any]:
        return asdict(self.model_info())


def load_surrogate(checkpoint_path: Path = PROMOTED_CHECKPOINT) -> SurrogateRunner:
    return SurrogateRunner(checkpoint_path=checkpoint_path)
