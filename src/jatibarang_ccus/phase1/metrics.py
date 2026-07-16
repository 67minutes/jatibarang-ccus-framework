from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jatibarang_ccus.surrogate.config import UPSTREAM_FINAL_MANIFEST, UPSTREAM_METRICS, UPSTREAM_TRAIN_SUMMARY


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required Phase 1 source file is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def surrogate_metric_summary(metrics_path: Path = UPSTREAM_METRICS) -> dict[str, float | int | str]:
    payload = load_json(metrics_path)
    cumulative_last = payload["production_rollout"]["cumulative"]["last"]
    rollout_last = payload["rollout"]["last"]
    return {
        "one_step_pressure_r2": float(payload["one_step"]["pressure_r2"]),
        "one_step_gas_plume_iou": float(payload["one_step"]["gas_sat_plume_iou"]),
        "cumulative_production_error_pct": float(cumulative_last["cumulative_raw_oil_relative_mae_pct"]),
        "end_sequence_co2_mass_error_pct": float(rollout_last["z_co2_mass_error_pct"]),
        "rollout_validation_case_count": int(payload["production_rollout"]["cumulative"]["case_count"]),
        "output_contract": str(payload["output_contract"]),
        "tin": int(payload["tin"]),
    }


def geology_span(
    assumptions: dict[str, Any],
    train_summary_path: Path = UPSTREAM_TRAIN_SUMMARY,
    manifest_path: Path = UPSTREAM_FINAL_MANIFEST,
) -> dict[str, float | int]:
    train_payload = load_json(train_summary_path)
    split = train_payload["summary"]["split"]
    selected_case_ids = set(split["train"]) | set(split["val"]) | set(split["test"])

    manifest = load_json(manifest_path)
    entries = [
        entry
        for entry in manifest["entries"]
        if entry.get("case_id") in selected_case_ids and entry.get("status") == "accepted"
    ]
    if not entries:
        raise ValueError("No accepted manifest entries matched the promoted train/validation/test split.")

    porosity_values = [float(entry["params"]["poro_mean"]) for entry in entries]
    geology = assumptions["geology"]
    return {
        "geological_realization_count": len(entries),
        "porosity_min": min(porosity_values),
        "porosity_max": max(porosity_values),
        "matrix_permeability_min_md": float(geology["matrix_permeability_min_md"]),
        "matrix_permeability_max_md": float(geology["matrix_permeability_max_md"]),
    }


def mrst_mean_runtime_seconds(manifest_path: Path = UPSTREAM_FINAL_MANIFEST) -> float:
    manifest = load_json(manifest_path)
    mean_runtime = manifest.get("summary", {}).get("mean_runtime_seconds")
    if mean_runtime is None:
        runtimes = [float(entry["runtime_seconds"]) for entry in manifest["entries"] if entry.get("runtime_seconds")]
        if not runtimes:
            raise ValueError("No MRST runtime data found in final manifest.")
        return sum(runtimes) / len(runtimes)
    return float(mean_runtime)

