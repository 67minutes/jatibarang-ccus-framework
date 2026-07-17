from __future__ import annotations

import argparse
import csv
from dataclasses import replace
from datetime import datetime
import json
import os
from pathlib import Path
import platform
import threading
from time import perf_counter, sleep
from typing import Any

import numpy as np
import torch

from .postprocessing import co2_density_kg_m3, reservoir_inventory_tonnes
from .preprocessing import compile_request
from .runner import SurrogateRunner, load_surrogate
from .schemas import PredictRequest


REPO_ROOT = Path(__file__).resolve().parents[3]
VALIDATION_DIR = REPO_ROOT / "data" / "validation_cases"
MANIFEST = VALIDATION_DIR / "manifest.json"
OUTPUT_DIR = REPO_ROOT / "paper" / "validation"


def load_validation_case(case_id: str) -> tuple[PredictRequest, dict[str, np.ndarray]]:
    from ..imports.mrst import load_mrst_reservoir

    path = VALIDATION_DIR / f"{case_id}.mat"
    imported = load_mrst_reservoir(path)
    request = PredictRequest(
        scenario_id=case_id,
        geology=imported.geology,
        schedule=imported.schedule,
        seed=imported.seed,
    )
    return request, imported.targets


def _r2(true: np.ndarray, pred: np.ndarray) -> float:
    target = np.asarray(true, dtype=np.float64).reshape(-1)
    estimate = np.asarray(pred, dtype=np.float64).reshape(-1)
    denominator = float(np.sum(np.square(target - np.mean(target))))
    if denominator <= 1e-12:
        return 1.0 if np.allclose(target, estimate) else 0.0
    return float(1.0 - np.sum(np.square(target - estimate)) / denominator)


def _rmse(true: np.ndarray, pred: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(np.asarray(true, dtype=np.float64) - np.asarray(pred, dtype=np.float64)))))


def _iou(true: np.ndarray, pred: np.ndarray, threshold: float) -> float:
    true_mask = np.asarray(true) >= threshold
    pred_mask = np.asarray(pred) >= threshold
    union = int(np.logical_or(true_mask, pred_mask).sum())
    return 1.0 if union == 0 else float(np.logical_and(true_mask, pred_mask).sum() / union)


def _mass_error(true: np.ndarray, pred: np.ndarray) -> float:
    true_mass = float(np.sum(true))
    return float(abs(float(np.sum(pred)) - true_mass) / max(abs(true_mass), 1e-6) * 100.0)


def _relative_error_pct(true: float, pred: float) -> float | None:
    return None if abs(true) <= 1e-9 else abs(pred - true) / abs(true) * 100.0


def validate_cases(runner: SurrogateRunner) -> dict[str, Any]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    case_ids = [item["case_id"] for item in manifest["cases"]]
    rows: list[dict[str, Any]] = []
    case_summaries: list[dict[str, Any]] = []
    for case_id in case_ids:
        request, targets = load_validation_case(case_id)
        compiled = compile_request(request, runner.checkpoint["stats"])
        prediction = runner.predict_compiled(compiled)
        horizon = prediction.horizon_steps
        true_slice = slice(8, 8 + horizon)
        checkpoints = [("t_plus_1", 1), ("t_plus_5", 5), ("t_plus_10", 10), ("t_plus_11", 11), ("last", horizon)]
        for label, step in checkpoints:
            if step > horizon:
                continue
            index = step - 1
            target_index = 8 + index
            true_oil_delta = float(targets["oil_delta_m3"][target_index])
            true_gas_delta = float(targets["gas_delta_m3"][target_index])
            pred_oil_delta = float(prediction.forecast_oil_delta_m3[index])
            pred_gas_delta = float(prediction.forecast_gas_delta_m3[index])
            true_oil_cumulative_at_step = float(np.sum(targets["oil_delta_m3"][: target_index + 1]))
            true_gas_cumulative_at_step = float(np.sum(targets["gas_delta_m3"][: target_index + 1]))
            pred_oil_cumulative_at_step = float(prediction.cumulative_oil_m3[target_index])
            pred_gas_cumulative_at_step = float(prediction.cumulative_gas_m3[target_index])
            rows.append(
                {
                    "case_id": case_id,
                    "horizon": label,
                    "step": step,
                    "pressure_r2": _r2(targets["pressure"][target_index], prediction.pred_pressure_bar[index]),
                    "pressure_rmse_bar": _rmse(targets["pressure"][target_index], prediction.pred_pressure_bar[index]),
                    "gas_iou": _iou(targets["gas_sat"][target_index], prediction.pred_normalized[index, 1], 0.01),
                    "z_co2_iou": _iou(targets["z_co2"][target_index], prediction.pred_normalized[index, 2], 0.02),
                    "gas_mass_proxy_error_pct": _mass_error(targets["gas_sat"][target_index], prediction.pred_normalized[index, 1]),
                    "z_co2_mass_proxy_error_pct": _mass_error(targets["z_co2"][target_index], prediction.pred_normalized[index, 2]),
                    "oil_r2": _r2(targets["oil_sat"][target_index], prediction.pred_normalized[index, 3]),
                    "oil_rmse_fraction": _rmse(targets["oil_sat"][target_index], prediction.pred_normalized[index, 3]),
                    "oil_delta_error_m3": abs(pred_oil_delta - true_oil_delta),
                    "gas_delta_error_m3": abs(pred_gas_delta - true_gas_delta),
                    "oil_delta_error_pct": _relative_error_pct(true_oil_delta, pred_oil_delta),
                    "gas_delta_error_pct": _relative_error_pct(true_gas_delta, pred_gas_delta),
                    "oil_cumulative_error_pct": _relative_error_pct(true_oil_cumulative_at_step, pred_oil_cumulative_at_step),
                    "gas_cumulative_error_pct": _relative_error_pct(true_gas_cumulative_at_step, pred_gas_cumulative_at_step),
                }
            )

        true_oil_cumulative = float(np.sum(targets["oil_delta_m3"][: 8 + horizon]))
        true_gas_cumulative = float(np.sum(targets["gas_delta_m3"][: 8 + horizon]))
        true_pressure = targets["pressure"][true_slice]
        true_density = co2_density_kg_m3(true_pressure, request.geology.reservoir_temperature_c)
        true_inventory = reservoir_inventory_tonnes(
            request.geology.porosity_fraction.as_array(),
            targets["gas_sat"][true_slice],
            targets["z_co2"][true_slice],
            true_density,
            request.geology.cell_volume_m3,
        )
        pred_density = co2_density_kg_m3(prediction.pred_pressure_bar, request.geology.reservoir_temperature_c)
        pred_inventory = reservoir_inventory_tonnes(
            request.geology.porosity_fraction.as_array(),
            prediction.pred_normalized[:, 1],
            prediction.pred_normalized[:, 2],
            pred_density,
            request.geology.cell_volume_m3,
        )
        case_summaries.append(
            {
                "case_id": case_id,
                "cycles": request.schedule.cycles,
                "forecast_steps": horizon,
                "forecast_oil_delta_mae_m3": float(np.mean(np.abs(prediction.forecast_oil_delta_m3 - targets["oil_delta_m3"][true_slice]))),
                "forecast_gas_delta_mae_m3": float(np.mean(np.abs(prediction.forecast_gas_delta_m3 - targets["gas_delta_m3"][true_slice]))),
                "cumulative_oil_error_pct": abs(float(prediction.cumulative_oil_m3[-1]) - true_oil_cumulative) / max(true_oil_cumulative, 1e-6) * 100.0,
                "cumulative_gas_error_pct": abs(float(prediction.cumulative_gas_m3[-1]) - true_gas_cumulative) / max(true_gas_cumulative, 1e-6) * 100.0,
                "final_inventory_approximation_error_pct": abs(float(pred_inventory[-1]) - float(true_inventory[-1])) / max(float(true_inventory[-1]), 1e-6) * 100.0,
            }
        )
    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "checkpoint_sha256": runner.checkpoint_sha256,
        "checkpoint_run_name": runner.model_info().checkpoint_run_name,
        "mechanical_verdict": "PASS",
        "scientific_verdict": "CONDITIONAL",
        "case_count": len(case_ids),
        "cases": case_summaries,
        "horizon_metrics": rows,
        "scientific_caveats": [
            "Validation is a curated five-case local check, not a replacement for the full held-out 36-case upstream evaluation.",
            "The files do not contain a pre-operation state; the first exported frame is the inventory baseline.",
            "Inventory is a pore-volume/pure-CO2-density approximation because the checkpoint has no produced-CO2 head.",
            "Three- and four-cycle forecasts extend beyond the pinned 24-step upstream confidence horizon.",
            "Pressure R2 is unstable at nearly spatially uniform target frames; interpret it together with pressure RMSE.",
        ],
    }


class _PeakMemorySampler:
    def __init__(self) -> None:
        try:
            import psutil
        except ImportError as exc:
            raise RuntimeError("psutil is required for the peak-memory benchmark; install the test extras") from exc
        self.process = psutil.Process(os.getpid())
        self.peak = self.process.memory_info().rss
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._sample, daemon=True)

    def _sample(self) -> None:
        while not self.stop_event.is_set():
            self.peak = max(self.peak, self.process.memory_info().rss)
            sleep(0.05)

    def __enter__(self) -> "_PeakMemorySampler":
        self.thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop_event.set()
        self.thread.join()
        self.peak = max(self.peak, self.process.memory_info().rss)


def benchmark(runner: SurrogateRunner, scenario_count: int = 200) -> dict[str, Any]:
    request, _ = load_validation_case("case_0016")
    compiled = compile_request(request, runner.checkpoint["stats"])
    fixture = np.load(REPO_ROOT / "tests" / "fixtures" / "surrogate" / "case_0016_expected.npz")

    # Warm up the exact promoted path.
    runner.predict_one_step(compiled.x_dynamic_seed, compiled.x_static, stage=int(fixture["stage"][0]))
    one_step_samples = []
    for _ in range(10):
        started = perf_counter()
        runner.predict_one_step(compiled.x_dynamic_seed, compiled.x_static, stage=int(fixture["stage"][0]))
        one_step_samples.append(perf_counter() - started)

    rollout_samples = []
    for _ in range(3):
        started = perf_counter()
        runner.predict_compiled(compiled, max_forecast_steps=24)
        rollout_samples.append(perf_counter() - started)

    batch = [replace(compiled, scenario_id=f"benchmark_{index:03d}") for index in range(scenario_count)]
    with _PeakMemorySampler() as memory:
        started = perf_counter()
        predictions = runner.predict_compiled_batch(batch, microbatch_size=16, max_forecast_steps=24)
        batch_elapsed = perf_counter() - started
    scenario_steps = scenario_count * 24
    thresholds = {
        "warm_one_step_p95_lt_1s": float(np.percentile(one_step_samples, 95)) < 1.0,
        "rollout24_p95_lt_3s": float(np.percentile(rollout_samples, 95)) < 3.0,
        "batch_200x24_lt_8min": scenario_count != 200 or batch_elapsed < 480.0,
        "peak_memory_lt_4gb": memory.peak < 4 * 1024**3,
        "scenario_count_complete": len(predictions) == scenario_count,
    }
    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "mechanical_verdict": "PASS" if all(thresholds.values()) else "FAIL",
        "checkpoint_sha256": runner.checkpoint_sha256,
        "hardware": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "logical_cpu_count": os.cpu_count(),
        },
        "software": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "numpy": np.__version__,
            "torch_threads": torch.get_num_threads(),
        },
        "configuration": {
            "scenario_count": scenario_count,
            "forecast_steps": 24,
            "microbatch_size": 16,
        },
        "measurements": {
            "warm_one_step_seconds": one_step_samples,
            "warm_one_step_p95_seconds": float(np.percentile(one_step_samples, 95)),
            "rollout24_seconds": rollout_samples,
            "rollout24_p95_seconds": float(np.percentile(rollout_samples, 95)),
            "batch_elapsed_seconds": batch_elapsed,
            "scenario_steps_per_second": scenario_steps / batch_elapsed,
            "peak_rss_bytes": memory.peak,
        },
        "thresholds": thresholds,
    }


def write_reports(validation: dict[str, Any], benchmark_report: dict[str, Any] | None) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "feature001_validation.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
    rows = validation["horizon_metrics"]
    with (OUTPUT_DIR / "feature001_validation.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    if benchmark_report is not None:
        (OUTPUT_DIR / "feature001_benchmark.json").write_text(json.dumps(benchmark_report, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and benchmark Feature 001")
    parser.add_argument("--skip-benchmark", action="store_true")
    parser.add_argument("--benchmark-count", type=int, default=200)
    args = parser.parse_args()
    runner = load_surrogate()
    validation = validate_cases(runner)
    benchmark_report = None if args.skip_benchmark else benchmark(runner, scenario_count=args.benchmark_count)
    write_reports(validation, benchmark_report)
    print(json.dumps({
        "validation": validation["mechanical_verdict"],
        "scientific": validation["scientific_verdict"],
        "benchmark": benchmark_report["mechanical_verdict"] if benchmark_report else "SKIPPED",
        "output_dir": str(OUTPUT_DIR),
    }, indent=2))
    return 0 if validation["mechanical_verdict"] == "PASS" and (benchmark_report is None or benchmark_report["mechanical_verdict"] == "PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
