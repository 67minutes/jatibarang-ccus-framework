"""Deterministic Feature 007 paper-result bundle builder.

The builder is deliberately evidence-driven.  It copies only compact, derived
tables into the bundle, records SHA-256 provenance for every source, and leaves
G3/G4-dependent panels blocked until their real artifacts exist.  It never
manufactures paper-facing screening, MRST, or economic results.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Sequence


BUNDLE_SCHEMA_VERSION = "feature007-bundle-v1"
DEFAULT_BUNDLE_ID = "working"
DEFAULT_SEED = 20260717
DEFAULT_GENERATED_AT = "2026-07-17T00:00:00+07:00"
ROOT = Path(__file__).resolve().parents[3]
BUNDLE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

SCHEDULE_FIELDS = (
    "injection_rate_m3_day",
    "soak_duration_days",
    "production_duration_days",
    "production_bhp_psi",
    "cycles",
)

ARM_A_SCHEDULE = {
    "injection_rate_m3_day": 9000.0,
    "injection_duration_days": 45.0,
    "soak_duration_days": 30.0,
    "production_duration_days": 190.0,
    "production_bhp_psi": 675.0,
    "cycles": 3,
}


def _validate_bundle_id(bundle_id: str) -> str:
    if not BUNDLE_ID_PATTERN.fullmatch(bundle_id):
        raise ValueError(
            "bundle_id must contain only letters, numbers, dot, underscore, or hyphen"
        )
    return bundle_id


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _write_compact_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, separators=(",", ":"), sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _repo_relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _stable_tiebreak(seed: int, *parts: str) -> int:
    text = "|".join((str(seed), *parts)).encode("utf-8")
    return int.from_bytes(hashlib.sha256(text).digest(), "big")


def _normalise_schedules(schedules: Sequence[dict[str, Any]]) -> list[tuple[float, ...]]:
    rows = [item["values"] for item in schedules]
    bounds = {
        field: (
            min(float(row[field]) for row in rows),
            max(float(row[field]) for row in rows),
        )
        for field in SCHEDULE_FIELDS
    }
    vectors: list[tuple[float, ...]] = []
    for row in rows:
        vector = []
        for field in SCHEDULE_FIELDS:
            low, high = bounds[field]
            value = float(row[field])
            vector.append(0.0 if high == low else (value - low) / (high - low))
        vectors.append(tuple(vector))
    return vectors


def _distance(left: Sequence[float], right: Sequence[float]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))


def select_arm_b_design(
    design: dict[str, Any], *, seed: int = DEFAULT_SEED
) -> list[dict[str, Any]]:
    """Select exactly two real-MRST designs per candidate by seeded maximin.

    Selection is global across the five locked schedule dimensions, so the 40
    primaries cover the operating grid instead of repeating the same two
    schedules for every geology.  Hash-based tie breaking makes the result
    independent of Python/numpy RNG implementations.
    """

    geologies = sorted(design["geologies"], key=lambda item: item["candidate_id"])
    schedules = sorted(
        design["schedules"], key=lambda item: item["schedule_fingerprint"]
    )
    if len(geologies) != 20:
        raise ValueError(f"Arm B requires 20 geologies, found {len(geologies)}")
    if len(schedules) < 40:
        raise ValueError("Arm B maximin design requires at least 40 schedules")

    vectors = _normalise_schedules(schedules)
    selected_schedule_indices: list[int] = []
    rows: list[dict[str, Any]] = []

    for replicate in (1, 2):
        for geology in geologies:
            available = [
                index
                for index in range(len(schedules))
                if index not in selected_schedule_indices
            ]
            if not selected_schedule_indices:
                chosen = min(
                    available,
                    key=lambda index: _stable_tiebreak(
                        seed, schedules[index]["schedule_fingerprint"]
                    ),
                )
                min_distance = None
            else:
                scores = {
                    index: min(
                        _distance(vectors[index], vectors[prior])
                        for prior in selected_schedule_indices
                    )
                    for index in available
                }
                best = max(scores.values())
                tied = [
                    index
                    for index in available
                    if math.isclose(scores[index], best, rel_tol=0.0, abs_tol=1e-12)
                ]
                chosen = min(
                    tied,
                    key=lambda index: _stable_tiebreak(
                        seed,
                        geology["candidate_id"],
                        str(replicate),
                        schedules[index]["schedule_fingerprint"],
                    ),
                )
                min_distance = scores[chosen]

            selected_schedule_indices.append(chosen)
            schedule = schedules[chosen]
            values = schedule["values"]
            row = {
                "selection_rank": len(rows) + 1,
                "candidate_id": geology["candidate_id"],
                "source_case_id": geology["source_case_id"],
                "replicate": replicate,
                "schedule_fingerprint": schedule["schedule_fingerprint"],
                "min_distance_at_selection": (
                    "" if min_distance is None else f"{min_distance:.12f}"
                ),
            }
            for field in (
                "injection_rate_m3_day",
                "injection_duration_days",
                "soak_duration_days",
                "production_duration_days",
                "production_bhp_psi",
                "cycles",
            ):
                row[field] = values[field]
            rows.append(row)

    counts = Counter(row["candidate_id"] for row in rows)
    if len(rows) != 40 or set(counts.values()) != {2}:
        raise AssertionError("Arm B selection did not produce two rows per geology")
    return rows


def select_arm_b_replacement_order(
    design: dict[str, Any],
    primary_rows: Sequence[dict[str, Any]],
    *,
    seed: int = DEFAULT_SEED,
) -> list[dict[str, Any]]:
    """Pre-rank every same-geology replacement after the 40 primaries."""

    geologies = sorted(design["geologies"], key=lambda item: item["candidate_id"])
    schedules = sorted(
        design["schedules"], key=lambda item: item["schedule_fingerprint"]
    )
    vectors = _normalise_schedules(schedules)
    distances = [
        [_distance(left, right) for right in vectors]
        for left in vectors
    ]
    index_by_fingerprint = {
        item["schedule_fingerprint"]: index for index, item in enumerate(schedules)
    }
    primary_by_geology: dict[str, list[int]] = defaultdict(list)
    for row in primary_rows:
        primary_by_geology[row["candidate_id"]].append(
            index_by_fingerprint[row["schedule_fingerprint"]]
        )

    result: list[dict[str, Any]] = []
    for geology in geologies:
        selected = list(primary_by_geology[geology["candidate_id"]])
        if len(selected) != 2:
            raise ValueError(
                f"replacement order requires two primaries for {geology['candidate_id']}"
            )
        available = [index for index in range(len(schedules)) if index not in selected]
        scores = {
            index: min(distances[index][prior] for prior in selected)
            for index in available
        }
        replacement_rank = 0
        while available:
            best = max(scores.values())
            tied = [
                index
                for index in available
                if math.isclose(scores[index], best, rel_tol=0.0, abs_tol=1e-12)
            ]
            chosen = min(
                tied,
                key=lambda index: _stable_tiebreak(
                    seed,
                    geology["candidate_id"],
                    "reserve",
                    str(replacement_rank + 1),
                    schedules[index]["schedule_fingerprint"],
                ),
            )
            replacement_rank += 1
            schedule = schedules[chosen]
            values = schedule["values"]
            row = {
                "candidate_id": geology["candidate_id"],
                "source_case_id": geology["source_case_id"],
                "replacement_rank": replacement_rank,
                "schedule_fingerprint": schedule["schedule_fingerprint"],
                "min_distance_at_selection": f"{scores[chosen]:.12f}",
            }
            for field in (
                "injection_rate_m3_day",
                "injection_duration_days",
                "soak_duration_days",
                "production_duration_days",
                "production_bhp_psi",
                "cycles",
            ):
                row[field] = values[field]
            result.append(row)
            selected.append(chosen)
            available.remove(chosen)
            scores.pop(chosen)
            for index in available:
                scores[index] = min(scores[index], distances[index][chosen])
    return result


def _write_csv(path: Path, rows: Sequence[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"refusing to write an untyped empty table: {path}")
    fieldnames = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def _copy_csv(source: Path, target: Path) -> int:
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return _write_csv(target, rows)


def _preset_readiness(root: Path, preset_id: str, expected: tuple[int, int, int]) -> dict[str, Any]:
    preset_dir = root / "data" / "screening_presets" / preset_id
    manifest_path = preset_dir / "manifest.json"
    if not manifest_path.exists():
        return {
            "ready": False,
            "reason": "manifest is missing",
            "manifest": _repo_relative(manifest_path, root),
        }
    try:
        manifest = _json(manifest_path)
        dimensions = (
            int(manifest["logical_scenarios"]),
            int(manifest["geology_count"]),
            int(manifest["schedule_count"]),
        )
        payload = preset_dir / manifest["payload_file"]
        expected_hash = str(manifest["payload_sha256"]).upper()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {
            "ready": False,
            "reason": f"manifest is invalid: {exc}",
            "manifest": _repo_relative(manifest_path, root),
        }
    if dimensions != expected:
        return {
            "ready": False,
            "reason": f"dimensions {dimensions} do not match {expected}",
            "manifest": _repo_relative(manifest_path, root),
        }
    if not payload.exists():
        return {
            "ready": False,
            "reason": "payload is missing",
            "manifest": _repo_relative(manifest_path, root),
        }
    actual_hash = _sha256(payload)
    if actual_hash != expected_hash:
        return {
            "ready": False,
            "reason": "payload SHA-256 does not match manifest",
            "manifest": _repo_relative(manifest_path, root),
        }
    return {
        "ready": True,
        "reason": "",
        "manifest": _repo_relative(manifest_path, root),
        "manifest_sha256": _sha256(manifest_path),
        "payload": _repo_relative(payload, root),
        "payload_sha256": actual_hash,
    }


def _accepted_manifest_status(path: Path, root: Path, expected: int) -> dict[str, Any]:
    if not path.exists():
        return {
            "ready": False,
            "reason": "manifest is missing",
            "manifest": _repo_relative(path, root),
            "accepted_runs": 0,
        }
    try:
        payload = _json(path)
        accepted = int(payload.get("accepted_runs", payload.get("completed_runs", 0)))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return {
            "ready": False,
            "reason": f"manifest is invalid: {exc}",
            "manifest": _repo_relative(path, root),
            "accepted_runs": 0,
        }
    ready = accepted >= expected and not payload.get("failed_hashes", [])
    return {
        "ready": ready,
        "reason": "" if ready else f"requires {expected} accepted runs; found {accepted}",
        "manifest": _repo_relative(path, root),
        "manifest_sha256": _sha256(path),
        "accepted_runs": accepted,
    }


def _register_table(
    *,
    bundle_dir: Path,
    logical_name: str,
    target: Path,
    rows: int,
    source_class: str,
    source: Path,
    root: Path,
) -> tuple[str, dict[str, Any]]:
    return logical_name, {
        "path": target.relative_to(bundle_dir).as_posix(),
        "sha256": _sha256(target),
        "rows": rows,
        "source_class": source_class,
        "source_path": _repo_relative(source, root),
        "source_sha256": _sha256(source),
    }


def _build_fig02_atlas_payload(
    *, root: Path, bundle_dir: Path
) -> tuple[dict[str, Any], dict[str, str]] | None:
    """Export the exact terrain, geology, schedule, and price data for Figure 2."""

    assumptions_path = root / "data" / "jatibarang" / "case_study_assumptions.json"
    economics_path = root / "data" / "jatibarang" / "economic_basis.json"
    exclusions_path = root / "data" / "jatibarang" / "pipeline_exclusions.geojson"
    terrain_path = (
        root
        / "data"
        / "terrain"
        / "12. DEM SRTM 30m Provinsi Jawa Barat"
        / "DEM SRTM 30M JAWA BARAT.tif"
    )
    case_ids = ("0016", "0115", "0176", "0197", "0209")
    case_paths = [
        root / "data" / "validation_cases" / f"case_{case_id}.mat"
        for case_id in case_ids
    ]
    source_paths = [
        assumptions_path,
        economics_path,
        exclusions_path,
        terrain_path,
        *case_paths,
    ]
    if not all(path.exists() for path in source_paths):
        return None

    try:
        import h5py
        import numpy as np
        import rasterio
        from rasterio.windows import from_bounds
    except ImportError as exc:  # pragma: no cover - paper extras are present in CI
        raise RuntimeError(
            "h5py, numpy, and rasterio are required to export Figure 2 data"
        ) from exc

    assumptions = _json(assumptions_path)
    economics = _json(economics_path)
    exclusions = _json(exclusions_path)
    extent = [107.65, 108.58, -6.73, -6.35]
    with rasterio.open(terrain_path) as dataset:
        lon_min, lon_max, lat_min, lat_max = extent
        window = from_bounds(lon_min, lat_min, lon_max, lat_max, dataset.transform)
        dem = dataset.read(
            1,
            window=window,
            out_shape=(int(window.height / 4), int(window.width / 4)),
        ).astype(float)
    dem[dem > 10000] = np.nan
    dem = np.clip(dem, 0, None)
    dem = np.nan_to_num(dem, nan=0.0).astype(np.float32)

    fields: dict[str, dict[str, Any]] = {}
    for case_id, path in zip(case_ids, case_paths, strict=True):
        with h5py.File(path, "r") as handle:
            permeability = np.asarray(handle["perm_map"], dtype=np.float32)
            well_mask = np.rint(np.asarray(handle["well_mask"])).astype(np.int8)
        fields[case_id] = {
            "mean_log10_permeability": float(permeability.mean()),
            "geometric_mean_permeability_md": float(10 ** permeability.mean()),
            "permeability_log10_md": {
                "shape": list(permeability.shape),
                "axis_order": ["row", "column"],
                "values": permeability.tolist(),
            },
            "well_mask": {
                "shape": list(well_mask.shape),
                "axis_order": ["row", "column"],
                "values": well_mask.tolist(),
            },
        }
    order = sorted(case_ids, key=lambda case_id: fields[case_id]["mean_log10_permeability"])
    selection = [order[0], order[len(order) // 2], order[-1]]
    tags = ("low", "median", "high")

    screening_grid = assumptions["screening_grid"]
    schedule_count = math.prod(len(values) for values in screening_grid.values())
    hashes = {_repo_relative(path, root): _sha256(path) for path in source_paths}
    payload = {
        "schema_version": "feature007-figure02-v1",
        "terrain": {
            "source": "SRTM 30 m",
            "extent_lon_lat": extent,
            "downsample_factor": 4,
            "rendered_cell_spacing_m": 120.0,
            "elevation_m": {
                "shape": list(dem.shape),
                "axis_order": ["row", "column"],
                "values": dem.tolist(),
            },
        },
        "co2_source": assumptions["co2_source"],
        "candidate_wells": assumptions["candidates"],
        "routing_exclusions": exclusions["features"],
        "geology_selection": {
            "rule": "minimum, median, and maximum mean log10 permeability among five curated MRST-derived validation cases",
            "candidate_case_ids": list(case_ids),
            "selected_case_ids": selection,
            "tags": list(tags),
            "fields": {case_id: fields[case_id] for case_id in selection},
        },
        "screening_grid": screening_grid,
        "schedules_per_well": schedule_count,
        "carbon_price_scenarios": economics["carbon_price_scenarios"],
        "provenance": {
            "source_hashes": hashes,
            "raw_training_corpus_copied": False,
        },
    }
    output = bundle_dir / "figure_data" / "figure02_atlas.json"
    _write_compact_json(output, payload)
    record = {
        "path": output.relative_to(bundle_dir).as_posix(),
        "sha256": _sha256(output),
        "source_class": "srtm_terrain_mrst_derived_geology_and_declared_design",
        "available": True,
    }
    return record, hashes


def _build_fig03_reservoir_payload(
    *, root: Path, bundle_dir: Path
) -> tuple[dict[str, Any], dict[str, str]] | None:
    """Export Figure 3's real median validation case for the interactive viewer."""

    case_path = root / "data" / "validation_cases" / "case_0016.mat"
    cache_path = root / "paper" / "figures" / ".fig03_rollout_cache.npz"
    if not case_path.exists() or not cache_path.exists():
        return None
    try:
        import h5py
        import numpy as np
    except ImportError as exc:  # pragma: no cover - validation extra is present in CI
        raise RuntimeError(
            "h5py and numpy are required to export the Figure 3 reservoir payload"
        ) from exc

    with h5py.File(case_path, "r") as handle:
        static = {
            # MRST stores this field as log10(mD); the public payload exposes
            # physical permeability, matching GeologyInput and the viewer label.
            "permeability_md": np.power(
                10.0, np.asarray(handle["perm_map"], dtype=np.float32)
            ).astype(np.float32),
            "porosity_fraction": np.asarray(handle["poro_map"], dtype=np.float32),
            "facies": np.rint(np.asarray(handle["facies_map"])).astype(np.int16),
            "structure_m": np.asarray(handle["structure_map"], dtype=np.float32),
            "barrier": np.asarray(handle["barrier_map"], dtype=np.float32),
            "fracture_proxy": np.asarray(handle["fracture_proxy_map"], dtype=np.float32),
            "well_mask": np.rint(np.asarray(handle["well_mask"])).astype(np.int8),
            "completion_mask": np.rint(np.asarray(handle["completion_mask"])).astype(np.int8),
        }
        pressure = np.asarray(handle["pressure"], dtype=np.float32)
        gas_truth_all = np.asarray(handle["gas_sat"], dtype=np.float32)
        oil = np.asarray(handle["oil_sat"], dtype=np.float32)
        z_co2 = np.asarray(handle["z_co2"], dtype=np.float32)
        stage_labels = np.rint(np.asarray(handle["stage_labels"])).astype(int).ravel()
        cycle_index = np.rint(np.asarray(handle["cycle_index"])).astype(int).ravel()
        dt_days = np.asarray(handle["dt_days"], dtype=np.float64).ravel()
        well_ij = np.asarray(handle["well_ij"]).astype(int).ravel()
        completion_ij = np.asarray(handle["completion_ij"]).astype(int).T.tolist()
        params = {
            key: float(np.asarray(value).ravel()[0])
            for key, value in handle["params"].items()
        }

    candidate_cases = (
        "case_0016",
        "case_0115",
        "case_0176",
        "case_0197",
        "case_0209",
    )
    with np.load(cache_path, allow_pickle=False) as cache:
        gas_prediction = np.asarray(cache["case_0016/gas_pred"], dtype=np.float32)
        checkpoint_sha256 = str(np.asarray(cache["sha"]).item()).upper()
        cumulative = {
            "oil_m3_mrst": np.asarray(cache["case_0016/cum_oil_true"], dtype=np.float64).tolist(),
            "oil_m3_surrogate": np.asarray(cache["case_0016/cum_oil_pred"], dtype=np.float64).tolist(),
            "gas_m3_mrst": np.asarray(cache["case_0016/cum_gas_true"], dtype=np.float64).tolist(),
            "gas_m3_surrogate": np.asarray(cache["case_0016/cum_gas_pred"], dtype=np.float64).tolist(),
        }
        validation_cohort = {
            case_id: {
                "horizon_steps": int(np.asarray(cache[f"{case_id}/horizon"]).item()),
                "oil_m3_mrst": np.asarray(
                    cache[f"{case_id}/cum_oil_true"], dtype=np.float64
                ).tolist(),
                "oil_m3_surrogate": np.asarray(
                    cache[f"{case_id}/cum_oil_pred"], dtype=np.float64
                ).tolist(),
                "gas_m3_mrst": np.asarray(
                    cache[f"{case_id}/cum_gas_true"], dtype=np.float64
                ).tolist(),
                "gas_m3_surrogate": np.asarray(
                    cache[f"{case_id}/cum_gas_pred"], dtype=np.float64
                ).tolist(),
            }
            for case_id in candidate_cases
        }

    seed_frames = 8
    horizon = int(gas_prediction.shape[0])
    gas_truth = gas_truth_all[seed_frames : seed_frames + horizon]
    if gas_truth.shape != gas_prediction.shape:
        raise ValueError(
            f"Figure 3 truth/prediction shape mismatch: {gas_truth.shape} vs {gas_prediction.shape}"
        )
    residual = gas_prediction - gas_truth
    residual_limit = math.ceil(float(np.max(np.abs(residual))) * 10.0) / 10.0
    baseline_index = seed_frames - 1
    stage_names = {1: "inject", 2: "soak", 3: "produce"}
    elapsed = np.cumsum(dt_days)
    frame_metadata = [
        {
            "forecast_step": step + 1,
            "mrst_frame_index_zero_based": seed_frames + step,
            "mrst_frame_index_one_based": seed_frames + step + 1,
            "elapsed_days": float(elapsed[seed_frames + step]),
            "dt_days": float(dt_days[seed_frames + step]),
            "stage_code": int(stage_labels[seed_frames + step]),
            "stage": stage_names[int(stage_labels[seed_frames + step])],
            "cycle": int(cycle_index[seed_frames + step]),
        }
        for step in range(horizon)
    ]

    def array_record(array, units: str, axis_order: list[str]) -> dict[str, Any]:
        return {
            "shape": list(array.shape),
            "axis_order": axis_order,
            "units": units,
            "values": array.tolist(),
        }

    static_payload = {
        name: array_record(
            array,
            {
                "permeability_md": "mD",
                "porosity_fraction": "fraction",
                "facies": "class_id",
                "structure_m": "m_relative",
                "barrier": "proxy_fraction",
                "fracture_proxy": "proxy_fraction",
                "well_mask": "binary",
                "completion_mask": "binary",
            }[name],
            ["row", "column"],
        )
        for name, array in static.items()
    }
    baseline = {
        "frame_index_zero_based": baseline_index,
        "meaning": "last of eight real MRST warm-start seed frames",
        "pressure_bar": array_record(pressure[baseline_index], "bar", ["row", "column"]),
        "gas_saturation": array_record(gas_truth_all[baseline_index], "fraction", ["row", "column"]),
        "oil_saturation": array_record(oil[baseline_index], "fraction", ["row", "column"]),
        "z_co2": array_record(z_co2[baseline_index], "mole_fraction", ["row", "column"]),
    }
    payload = {
        "schema_version": "feature007-reservoir-v1",
        "case_id": "case_0016",
        "selection": {
            "role": "Figure 3 gallery and frontend declared median validation case",
            "method": "median cumulative-oil error among five curated local MRST cases",
            "candidate_cases": list(candidate_cases),
        },
        "geometry": {
            "dimensions": [64, 64, 1],
            "length_x_m": 900.0,
            "length_y_m": 600.0,
            "thickness_m": 6.0,
            "cell_size_x_m": 900.0 / 64.0,
            "cell_size_y_m": 600.0 / 64.0,
            "coordinate_system": "local_proxy_grid_not_surveyed_subsea_coordinates",
            "array_axis_order": ["row", "column"],
        },
        "static_fields": static_payload,
        "well": {
            "well_ij_one_based": well_ij.tolist(),
            "completion_ij_one_based": completion_ij,
        },
        "operating_parameters": params,
        "baseline": baseline,
        "warm_start": {
            "frame_count": seed_frames,
            "meaning": "eight real MRST seed frames preceding the free rollout",
            "gas_saturation": array_record(
                gas_truth_all[:seed_frames],
                "fraction",
                ["warm_start_frame", "row", "column"],
            ),
        },
        "dynamic": {
            "field": "gas_saturation",
            "mrst_truth": array_record(
                gas_truth, "fraction", ["forecast_step", "row", "column"]
            ),
            "surrogate_free_rollout": array_record(
                gas_prediction, "fraction", ["forecast_step", "row", "column"]
            ),
            "residual_prediction_minus_truth": array_record(
                residual, "fraction", ["forecast_step", "row", "column"]
            ),
        },
        "frame_metadata": frame_metadata,
        "comparison_steps": [8, 10, 24, 40],
        "shared_limits": {
            "gas_saturation": [0.0, 0.72],
            "gas_residual": [-residual_limit, residual_limit],
            "permeability_md": [
                float(np.min(static["permeability_md"])),
                float(np.max(static["permeability_md"])),
            ],
            "pressure_bar": [float(np.min(pressure)), float(np.max(pressure))],
            "oil_saturation": [float(np.min(oil)), float(np.max(oil))],
            "z_co2": [float(np.min(z_co2)), float(np.max(z_co2))],
        },
        "production": cumulative,
        "validation_cohort": {
            "selection_metric": "cumulative-oil error across the declared forecast horizon",
            "cases": validation_cohort,
        },
        "provenance": {
            "mrst_source_class": "offline_mrst_ground_truth",
            "surrogate_source_class": "frozen_checkpoint_free_rollout",
            "checkpoint_sha256": checkpoint_sha256,
            "case_path": _repo_relative(case_path, root),
            "case_sha256": _sha256(case_path),
            "rollout_cache_path": _repo_relative(cache_path, root),
            "rollout_cache_sha256": _sha256(cache_path),
            "raw_training_corpus_copied": False,
        },
    }
    output = bundle_dir / "reservoirs" / "case_0016.json"
    _write_compact_json(output, payload)
    record = {
        "path": output.relative_to(bundle_dir).as_posix(),
        "sha256": _sha256(output),
        "source_class": "mrst_truth_and_frozen_surrogate_prediction",
        "available": True,
        "case_id": "case_0016",
        "fields": ["gas_saturation"],
        "comparison_steps": [8, 10, 24, 40],
    }
    hashes = {
        _repo_relative(case_path, root): _sha256(case_path),
        _repo_relative(cache_path, root): _sha256(cache_path),
    }
    return record, hashes


def _figure_entry(
    root: Path,
    number: int,
    *,
    status: str,
    sources: Sequence[str],
    blockers: Sequence[str] = (),
) -> dict[str, Any]:
    stem_names = {
        1: "fig01_framework",
        2: "fig02_atlas",
        3: "fig03_surrogate",
        4: "fig04_screening_surface",
        5: "fig05_pipeline",
        6: "fig06_facility",
        7: "fig07_carbon_price_pivot",
        8: "fig08_abc_economics",
    }
    stem = stem_names[number]
    script = root / "paper" / "figures" / f"{stem}.py"
    artifact = root / "paper" / "figures" / f"{stem}.pdf"
    payload: dict[str, Any] = {
        "status": status,
        "script": _repo_relative(script, root),
        "source_classes": list(sources),
        "blockers": list(blockers),
    }
    if script.exists():
        payload["script_sha256"] = _sha256(script)
    if artifact.exists():
        payload["path"] = _repo_relative(artifact, root)
        payload["sha256"] = _sha256(artifact)
    return payload


def build_feature007_bundle(
    *,
    root: Path = ROOT,
    bundle_id: str = DEFAULT_BUNDLE_ID,
    generated_at: str = DEFAULT_GENERATED_AT,
    seed: int = DEFAULT_SEED,
) -> Path:
    """Build a deterministic working bundle from currently available evidence."""

    bundle_id = _validate_bundle_id(bundle_id)
    if bundle_id == "submitted":
        raise ValueError("use the freeze command to create the immutable submitted bundle")
    root = root.resolve()
    bundle_dir = root / "paper" / "results" / "feature007" / bundle_id
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    tables_dir = bundle_dir / "tables"
    tables_dir.mkdir(parents=True)

    full_design_path = (
        root / "data" / "screening_presets" / "jatibarang_full_v1" / "upstream_design.json"
    )
    if not full_design_path.exists():
        raise FileNotFoundError(f"Feature 005 full design is missing: {full_design_path}")
    full_design = _json(full_design_path)
    arm_b_rows = select_arm_b_design(full_design, seed=seed)
    arm_b_path = tables_dir / "arm_b_design.csv"
    arm_b_count = _write_csv(arm_b_path, arm_b_rows)
    arm_b_replacement_rows = select_arm_b_replacement_order(
        full_design, arm_b_rows, seed=seed
    )
    arm_b_replacement_path = tables_dir / "arm_b_replacement_order.csv"
    arm_b_replacement_count = _write_csv(
        arm_b_replacement_path, arm_b_replacement_rows
    )

    tables: dict[str, dict[str, Any]] = {}
    name, record = _register_table(
        bundle_dir=bundle_dir,
        logical_name="arm_b_design",
        target=arm_b_path,
        rows=arm_b_count,
        source_class="design_not_result",
        source=full_design_path,
        root=root,
    )
    tables[name] = record
    name, record = _register_table(
        bundle_dir=bundle_dir,
        logical_name="arm_b_replacement_order",
        target=arm_b_replacement_path,
        rows=arm_b_replacement_count,
        source_class="design_not_result",
        source=full_design_path,
        root=root,
    )
    tables[name] = record

    table_sources = {
        "surrogate_validation": (
            root / "paper" / "validation" / "feature001_validation.csv",
            "mrst_truth_and_surrogate_prediction",
        ),
        "pipeline_pressure_mechanics": (
            root / "paper" / "validation" / "feature002" / "continuous_pressure_profiles.csv",
            "coolprop_screening_mechanics_not_final_network",
        ),
        "pipeline_cost_sensitivity": (
            root / "paper" / "validation" / "feature002" / "cost_sensitivity.csv",
            "screening_cost_proxy_not_final_network",
        ),
        "facility_validation": (
            root / "paper" / "validation" / "feature003" / "runtime_comparison.csv",
            "dwsim_truth_and_runtime_correlation",
        ),
        "facility_cost_curve": (
            root / "paper" / "validation" / "feature003" / "equipment_cost_curve.csv",
            "screening_cost_correlation",
        ),
        "module004_reference_economics": (
            root / "paper" / "validation" / "feature004" / "carbon_price_sensitivity.csv",
            "module004_reference_not_arm_abc",
        ),
        "screening_surface": (
            root / "paper" / "validation" / "feature007" / "screening_surface.csv",
            "surrogate_prediction",
        ),
        "pipeline_route_final": (
            root / "paper" / "validation" / "feature007" / "pipeline_route.csv",
            "srtm_astar_and_arm_c_milp_result",
        ),
        "pipeline_pressure_final": (
            root / "paper" / "validation" / "feature007" / "pipeline_pressure_profile.csv",
            "coolprop_continuous_pressure_audit",
        ),
        "pipeline_cost_crossover_final": (
            root / "paper" / "validation" / "feature007" / "pipeline_cost_crossover.csv",
            "screening_cost_proxy",
        ),
        "carbon_price_rankings": (
            root / "paper" / "validation" / "feature007" / "carbon_price_rankings.csv",
            "arm_c_integrated_result",
        ),
        "carbon_price_regret": (
            root / "paper" / "validation" / "feature007" / "carbon_price_regret.csv",
            "arm_c_integrated_result",
        ),
        "npv_vs_carbon_price": (
            root / "paper" / "validation" / "feature007" / "npv_vs_carbon_price.csv",
            "arm_c_integrated_result",
        ),
        "abc_economics": (
            root / "paper" / "validation" / "feature007" / "abc_economics.csv",
            "mrst_and_surrogate_integrated_result",
        ),
        "abc_runtime": (
            root / "paper" / "validation" / "feature007" / "abc_runtime.csv",
            "measured_runtime",
        ),
        "topk_confirmation": (
            root / "paper" / "validation" / "feature007" / "topk_confirmation.csv",
            "mrst_truth_and_surrogate_prediction",
        ),
    }
    for logical_name, (source, source_class) in table_sources.items():
        if not source.exists():
            continue
        target = tables_dir / f"{logical_name}.csv"
        row_count = _copy_csv(source, target)
        name, record = _register_table(
            bundle_dir=bundle_dir,
            logical_name=logical_name,
            target=target,
            rows=row_count,
            source_class=source_class,
            source=source,
            root=root,
        )
        tables[name] = record

    figure_data: dict[str, dict[str, Any]] = {}
    figure_data_input_hashes: dict[str, str] = {}
    fig02_data = _build_fig02_atlas_payload(root=root, bundle_dir=bundle_dir)
    if fig02_data is not None:
        record, source_hashes = fig02_data
        figure_data["2"] = record
        figure_data_input_hashes.update(source_hashes)

    reservoirs: dict[str, dict[str, Any]] = {}
    reservoir_input_hashes: dict[str, str] = {}
    fig03_reservoir = _build_fig03_reservoir_payload(root=root, bundle_dir=bundle_dir)
    if fig03_reservoir is not None:
        record, source_hashes = fig03_reservoir
        reservoirs[record["case_id"]] = record
        reservoir_input_hashes.update(source_hashes)

    demo = _preset_readiness(root, "jatibarang_demo_v1", (200, 20, 10))
    full = _preset_readiness(root, "jatibarang_full_v1", (3240, 20, 162))
    arm_a = _accepted_manifest_status(
        root / "data" / "scenario_a_runs" / "manifest.json", root, 2
    )
    arm_b = _accepted_manifest_status(
        root / "data" / "scenario_b_runs" / "manifest.json", root, 40
    )
    top_k = _accepted_manifest_status(
        root / "data" / "scenario_c_topk_runs" / "manifest.json", root, 5
    )
    promoted = full if full["ready"] else demo
    scenario_count = 3240 if full["ready"] else (200 if demo["ready"] else 0)

    arm_c_result = root / "paper" / "validation" / "feature007" / "arm_c_screening.json"
    arm_c_ready = promoted["ready"] and arm_c_result.exists()
    arm_c_status = {
        "ready": arm_c_ready,
        "reason": "" if arm_c_ready else (
            promoted["reason"] if not promoted["ready"] else "Arm C screening result is missing"
        ),
        "result": _repo_relative(arm_c_result, root),
    }
    if arm_c_result.exists():
        arm_c_status["result_sha256"] = _sha256(arm_c_result)

    screening_blocker = (
        "Feature 005 200/3240 scenario preset is not promoted"
        if not promoted["ready"]
        else "Arm C screening result is missing"
    )
    abc_blockers = []
    if not arm_a["ready"]:
        abc_blockers.append("Arm A two-case MRST confirmation is incomplete")
    if not arm_b["ready"]:
        abc_blockers.append("Arm B requires 40 accepted MRST runs")
    if not arm_c_ready:
        abc_blockers.append(screening_blocker)
    if not top_k["ready"]:
        abc_blockers.append("Arm C top-five MRST confirmation is incomplete")

    figure4_ready = arm_c_ready and "screening_surface" in tables
    figure5_ready = arm_c_ready and {
        "pipeline_route_final",
        "pipeline_pressure_final",
        "pipeline_cost_crossover_final",
    }.issubset(tables)
    figure6_ready = {
        "facility_validation",
        "facility_cost_curve",
    }.issubset(tables)
    figure7_ready = arm_c_ready and {
        "carbon_price_rankings",
        "carbon_price_regret",
        "npv_vs_carbon_price",
    }.issubset(tables)
    figure8_ready = not abc_blockers and {
        "abc_economics",
        "abc_runtime",
        "topk_confirmation",
    }.issubset(tables)
    figure1_ready = (root / "paper" / "figures" / "fig01_framework.pdf").exists()
    figure2_ready = "2" in figure_data and (
        root / "paper" / "figures" / "fig02_atlas.pdf"
    ).exists()
    figure3_ready = "case_0016" in reservoirs and (
        root / "paper" / "figures" / "fig03_surrogate.pdf"
    ).exists()
    figures = {
        "1": _figure_entry(
            root,
            1,
            status="ready" if figure1_ready else "blocked",
            sources=["methodology"],
            blockers=[] if figure1_ready else ["Figure 1 artifact is missing"],
        ),
        "2": _figure_entry(
            root,
            2,
            status="ready" if figure2_ready else "blocked",
            sources=["srtm_terrain", "mrst_derived_geology", "design_grid"],
            blockers=[] if figure2_ready else ["Figure 2 canonical atlas data or artifact is missing"],
        ),
        "3": _figure_entry(
            root,
            3,
            status="ready" if figure3_ready else "blocked",
            sources=["mrst_truth", "surrogate_prediction"],
            blockers=[] if figure3_ready else ["Figure 3 case_0016 bundle payload or artifact is missing"],
        ),
        "4": _figure_entry(
            root,
            4,
            status="ready" if figure4_ready else "blocked",
            sources=["surrogate_prediction"],
            blockers=[] if figure4_ready else [
                screening_blocker if not arm_c_ready else "screening_surface.csv is missing"
            ],
        ),
        "5": _figure_entry(
            root,
            5,
            status="ready" if figure5_ready else "blocked",
            sources=["srtm_terrain", "coolprop_mechanics", "milp_result"],
            blockers=[] if figure5_ready else ([screening_blocker] if not arm_c_ready else []) + [
                "final Arm C route, pressure, or crossover table is missing; existing Feature 002 network is mechanics evidence only"
            ],
        ),
        "6": _figure_entry(
            root,
            6,
            status="ready" if figure6_ready else "blocked",
            sources=["dwsim_truth", "runtime_correlation", "screening_cost_correlation"],
            blockers=[] if figure6_ready else ["Feature 003 validation tables are missing"],
        ),
        "7": _figure_entry(
            root,
            7,
            status="ready" if figure7_ready else "blocked",
            sources=["arm_c_integrated_result"],
            blockers=[] if figure7_ready else [
                screening_blocker if not arm_c_ready else "ranking, regret, or NPV curve table is missing"
            ],
        ),
        "8": _figure_entry(
            root,
            8,
            status="ready" if figure8_ready else "blocked",
            sources=["mrst_truth", "surrogate_integrated_result"],
            blockers=abc_blockers or (
                [] if figure8_ready else ["A/B/C economics, runtime, or top-five confirmation table is missing"]
            ),
        ),
    }

    all_blockers = sorted(
        {
            blocker
            for entry in figures.values()
            for blocker in entry.get("blockers", [])
        }
    )
    ready_count = sum(entry["status"] == "ready" for entry in figures.values())
    status = "ready" if ready_count == 8 else ("partial" if ready_count else "blocked")

    experiment_design = {
        "screening": {
            "surrogate_training_proxy_geologies": 177,
            "candidate_geologies": len(full_design["geologies"]),
            "schedules_per_geology": len(full_design["schedules"]),
            "designed_scenario_count": len(full_design["geologies"])
            * len(full_design["schedules"]),
            "actual_promoted_scenario_count": scenario_count,
        },
        "arm_a": {
            "label": "naive_fixed_schedule",
            "schedule": ARM_A_SCHEDULE,
            "geology_count": 20,
            "mrst_confirmations": ["median_permeability", "low_permeability"],
            "result_status": arm_a,
        },
        "arm_b": {
            "label": "limited_mrst_optimization",
            "seed": seed,
            "selection_method": "global_seeded_normalized_maximin",
            "dimensions": list(SCHEDULE_FIELDS),
            "target_accepted_runs": 40,
            "runs_per_geology": 2,
            "failure_policy": (
                "retain failed run in audit and use the next pre-ranked schedule "
                "for the same geology until 40 accepted runs exist"
            ),
            "design_table": tables["arm_b_design"]["path"],
            "replacement_order_table": tables["arm_b_replacement_order"]["path"],
            "result_status": arm_b,
        },
        "arm_c": {
            "label": "surrogate_integrated_screening",
            "scenario_count_policy": "use 3240 only when complete; otherwise promoted 200",
            "actual_scenario_count": scenario_count,
            "top_k_mrst": 5,
            "dwsim_spotchecks": ["minimum_throughput", "median_throughput", "maximum_throughput"],
            "result_status": arm_c_status,
            "top_k_status": top_k,
        },
    }

    results = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "bundle_id": bundle_id,
        "status": status,
        "summary": {
            "ready_figures": [key for key, value in figures.items() if value["status"] == "ready"],
            "blocked_figures": [key for key, value in figures.items() if value["status"] != "ready"],
            "actual_scenario_count": scenario_count,
            "fabricated_result": False,
            "reservoir_cases": sorted(reservoirs),
        },
        "figure_payloads": {
            key: {
                "status": value["status"],
                "tables": {
                    "6": ["facility_validation", "facility_cost_curve"],
                }.get(key, []),
                "blockers": value.get("blockers", []),
            }
            for key, value in figures.items()
        },
    }
    results_path = bundle_dir / "results.json"
    _write_json(results_path, results)
    tables["paper_results"] = {
        "path": results_path.relative_to(bundle_dir).as_posix(),
        "sha256": _sha256(results_path),
        "rows": 8,
        "source_class": "bundle_index",
    }

    execution_preflight_path = (
        root / "paper" / "validation" / "feature007" / "execution_preflight.json"
    )
    execution = (
        _json(execution_preflight_path)
        if execution_preflight_path.exists()
        else {
            "schema_version": "feature007-execution-preflight-v1",
            "benchmark": {"status": "UNAVAILABLE"},
            "launch": {"demo_200": "UNKNOWN", "full_3240": "UNKNOWN"},
        }
    )
    input_paths = [
        full_design_path,
        root / "paper" / "validation" / "feature003" / "artifact_manifest.json",
        root / "paper" / "validation" / "feature005" / "validation_summary.json",
        execution_preflight_path,
    ]
    input_hashes = {
        _repo_relative(path, root): _sha256(path)
        for path in input_paths
        if path.exists()
    }
    input_hashes.update(reservoir_input_hashes)
    input_hashes.update(figure_data_input_hashes)
    manifest = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "bundle_id": bundle_id,
        "immutable": False,
        "generated_at": generated_at,
        "status": status,
        "freeze_basis": "unfrozen_working_bundle",
        "scenario_count": scenario_count,
        "source_class": "mixed_real_evidence_and_explicit_pending_dependencies",
        "seed": seed,
        "input_hashes": input_hashes,
        "execution": execution,
        "experiment_design": experiment_design,
        "dependencies": {
            "jatibarang_demo_v1": demo,
            "jatibarang_full_v1": full,
            "arm_a_mrst": arm_a,
            "arm_b_mrst": arm_b,
            "arm_c_screening": arm_c_status,
            "arm_c_top_k_mrst": top_k,
        },
        "validation": {
            "mechanical": "PASS" if not all_blockers else "BLOCKED",
            "scientific": "PASS" if status == "ready" else "NOT_RUN",
            "fabricated_result": False,
            "blockers": all_blockers,
        },
        "tables": tables,
        "figure_data": figure_data,
        "reservoirs": reservoirs,
        "figures": figures,
        "provenance": {
            "generator": "src/jatibarang_ccus/paper/feature007.py",
            "raw_177_case_training_corpus_copied": False,
            "paper_numbers_promoted_only_from_ready_artifacts": True,
        },
    }
    _write_json(bundle_dir / "manifest.json", manifest)
    return bundle_dir


def verify_feature007_bundle(bundle_dir: Path, *, root: Path = ROOT) -> list[str]:
    """Return deterministic bundle validation errors (empty means PASS)."""

    errors: list[str] = []
    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.exists():
        return ["manifest.json is missing"]
    try:
        manifest = _json(manifest_path)
    except json.JSONDecodeError as exc:
        return [f"manifest.json is invalid JSON: {exc}"]
    if manifest.get("schema_version") != BUNDLE_SCHEMA_VERSION:
        errors.append("unsupported schema_version")
    if manifest.get("bundle_id") != bundle_dir.name:
        errors.append("bundle_id does not match directory name")
    if manifest.get("validation", {}).get("fabricated_result") is not False:
        errors.append("fabricated_result must be false")

    for name, record in sorted(manifest.get("tables", {}).items()):
        path = bundle_dir / record.get("path", "")
        try:
            path.resolve().relative_to(bundle_dir.resolve())
        except ValueError:
            errors.append(f"table {name} escapes bundle directory")
            continue
        if not path.is_file():
            errors.append(f"table {name} is missing: {record.get('path')}")
            continue
        if _sha256(path) != str(record.get("sha256", "")).upper():
            errors.append(f"table {name} SHA-256 mismatch")

    for number, record in sorted(manifest.get("figure_data", {}).items()):
        path = bundle_dir / record.get("path", "")
        try:
            path.resolve().relative_to(bundle_dir.resolve())
        except ValueError:
            errors.append(f"Figure {number} data escapes bundle directory")
            continue
        if not path.is_file():
            errors.append(f"Figure {number} data is missing: {record.get('path')}")
            continue
        if _sha256(path) != str(record.get("sha256", "")).upper():
            errors.append(f"Figure {number} data SHA-256 mismatch")
        if record.get("available") is not True:
            errors.append(f"Figure {number} data is not marked available")

    for case_id, record in sorted(manifest.get("reservoirs", {}).items()):
        path = bundle_dir / record.get("path", "")
        try:
            path.resolve().relative_to(bundle_dir.resolve())
        except ValueError:
            errors.append(f"reservoir {case_id} escapes bundle directory")
            continue
        if not path.is_file():
            errors.append(f"reservoir {case_id} is missing: {record.get('path')}")
            continue
        if _sha256(path) != str(record.get("sha256", "")).upper():
            errors.append(f"reservoir {case_id} SHA-256 mismatch")
        if record.get("available") is not True:
            errors.append(f"registered reservoir {case_id} is not marked available")

    arm_b_record = manifest.get("tables", {}).get("arm_b_design")
    primary_rows: list[dict[str, str]] = []
    if arm_b_record:
        with (bundle_dir / arm_b_record["path"]).open(
            "r", encoding="utf-8", newline=""
        ) as handle:
            primary_rows = list(csv.DictReader(handle))
        counts = Counter(row["candidate_id"] for row in primary_rows)
        if len(primary_rows) != 40:
            errors.append(f"Arm B design has {len(primary_rows)} rows, expected 40")
        if len(counts) != 20 or set(counts.values()) != {2}:
            errors.append("Arm B design must contain two schedules for each of 20 geologies")
        if len({row["schedule_fingerprint"] for row in primary_rows}) != len(primary_rows):
            errors.append("Arm B primary schedules are not globally unique")

    replacement_record = manifest.get("tables", {}).get("arm_b_replacement_order")
    if replacement_record:
        with (bundle_dir / replacement_record["path"]).open(
            "r", encoding="utf-8", newline=""
        ) as handle:
            replacements = list(csv.DictReader(handle))
        replacement_counts = Counter(row["candidate_id"] for row in replacements)
        expected_per_geology = max(
            int(manifest.get("dependencies", {}).get("jatibarang_full_v1", {}).get("schedule_count", 162)) - 2,
            0,
        )
        # The Feature 005 contract locks 162 schedules; retain a direct count
        # fallback because a blocked preset has no parsed schedule_count field.
        if expected_per_geology == 0:
            expected_per_geology = 160
        if len(replacements) != 20 * expected_per_geology:
            errors.append(
                f"Arm B replacement order has {len(replacements)} rows, expected {20 * expected_per_geology}"
            )
        if len(replacement_counts) != 20 or set(replacement_counts.values()) != {
            expected_per_geology
        }:
            errors.append("Arm B replacement order is not balanced across 20 geologies")
        primary_pairs = {
            (row["candidate_id"], row["schedule_fingerprint"]) for row in primary_rows
        }
        replacement_pairs = {
            (row["candidate_id"], row["schedule_fingerprint"]) for row in replacements
        }
        if primary_pairs & replacement_pairs:
            errors.append("Arm B replacement order repeats a primary for the same geology")

    figures = manifest.get("figures", {})
    if set(figures) != {str(i) for i in range(1, 9)}:
        errors.append("figure index must contain Figures 1-8")
    for number, entry in figures.items():
        if entry.get("status") == "blocked" and not entry.get("blockers"):
            errors.append(f"Figure {number} is blocked without an explicit blocker")
        if entry.get("status") == "ready" and entry.get("blockers"):
            errors.append(f"Figure {number} is ready but still has blockers")

    status = manifest.get("status")
    if status == "ready":
        if manifest.get("validation", {}).get("mechanical") != "PASS":
            errors.append("ready bundle lacks mechanical PASS")
        if manifest.get("validation", {}).get("scientific") != "PASS":
            errors.append("ready bundle lacks scientific PASS")
    if manifest.get("immutable") and manifest.get("freeze_basis") not in {
        "complete_200",
        "complete_3240",
    }:
        errors.append("immutable bundle has an invalid freeze_basis")
    return errors


def freeze_feature007_bundle(
    source: Path,
    target: Path,
    *,
    frozen_at: str,
    root: Path = ROOT,
) -> Path:
    """Freeze a fully ready working bundle; refuse partial scientific evidence."""

    expected_base = (root.resolve() / "paper" / "results" / "feature007").resolve()
    if source.resolve().parent != expected_base or target.resolve().parent != expected_base:
        raise ValueError("source and target must be direct children of paper/results/feature007")
    _validate_bundle_id(source.name)
    _validate_bundle_id(target.name)
    errors = verify_feature007_bundle(source, root=root)
    if errors:
        raise ValueError("source bundle verification failed: " + "; ".join(errors))
    manifest = _json(source / "manifest.json")
    if manifest["status"] != "ready" or manifest["scenario_count"] not in {200, 3240}:
        raise ValueError("only a scientifically ready 200- or 3240-scenario bundle can be frozen")
    if target.exists():
        raise FileExistsError(f"immutable target already exists: {target}")
    shutil.copytree(source, target)
    frozen = _json(target / "manifest.json")
    frozen["bundle_id"] = target.name
    frozen["immutable"] = True
    frozen["generated_at"] = frozen_at
    frozen["freeze_basis"] = f"complete_{frozen['scenario_count']}"
    results_path = target / "results.json"
    if results_path.exists():
        results = _json(results_path)
        results["bundle_id"] = target.name
        _write_json(results_path, results)
        frozen["tables"]["paper_results"]["sha256"] = _sha256(results_path)
    _write_json(target / "manifest.json", frozen)
    errors = verify_feature007_bundle(target, root=root)
    if errors:
        shutil.rmtree(target)
        raise ValueError("frozen bundle verification failed: " + "; ".join(errors))
    return target


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="build a working Feature 007 bundle")
    build.add_argument("--root", type=Path, default=ROOT)
    build.add_argument("--bundle-id", default=DEFAULT_BUNDLE_ID)
    build.add_argument("--generated-at", default=os.getenv("SOURCE_DATE_ISO", DEFAULT_GENERATED_AT))
    build.add_argument("--seed", type=int, default=DEFAULT_SEED)

    verify = sub.add_parser("verify", help="verify a Feature 007 bundle")
    verify.add_argument("--root", type=Path, default=ROOT)
    verify.add_argument("--bundle-id", default=DEFAULT_BUNDLE_ID)

    freeze = sub.add_parser("freeze", help="freeze a fully ready working bundle")
    freeze.add_argument("--root", type=Path, default=ROOT)
    freeze.add_argument("--source", default=DEFAULT_BUNDLE_ID)
    freeze.add_argument("--target", default="submitted")
    freeze.add_argument("--frozen-at", required=True)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    root = args.root.resolve()
    base = root / "paper" / "results" / "feature007"
    if args.command == "build":
        output = build_feature007_bundle(
            root=root,
            bundle_id=args.bundle_id,
            generated_at=args.generated_at,
            seed=args.seed,
        )
        errors = verify_feature007_bundle(output, root=root)
        print(json.dumps({"bundle": str(output), "verification_errors": errors}))
        return 1 if errors else 0
    if args.command == "verify":
        bundle_id = _validate_bundle_id(args.bundle_id)
        errors = verify_feature007_bundle(base / bundle_id, root=root)
        print(json.dumps({"bundle_id": args.bundle_id, "errors": errors}))
        return 1 if errors else 0
    output = freeze_feature007_bundle(
        base / _validate_bundle_id(args.source),
        base / _validate_bundle_id(args.target),
        frozen_at=args.frozen_at,
        root=root,
    )
    print(json.dumps({"bundle": str(output), "immutable": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
