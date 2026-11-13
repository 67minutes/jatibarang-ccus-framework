from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from jatibarang_ccus.contracts import CO2Source, Coordinate, EconomicProvenance
from jatibarang_ccus.infrastructure.economic_adapters import (
    assumptions_from_basis,
    carbon_prices_from_basis,
    fiscal_cases_from_basis,
    load_economic_basis,
)
from jatibarang_ccus.phase1.case_study import load_assumptions
from jatibarang_ccus.surrogate.config import REPO_ROOT
from jatibarang_ccus.surrogate.preprocessing import schedule_fingerprint
from jatibarang_ccus.surrogate.schemas import (
    GeologyInput,
    Grid2D,
    OperatingSchedule,
    ReservoirState,
    SeedHistory,
)

from .presets import (
    EXPECTED_PRESETS,
    CompactPresetCandidate,
    CompactPresetMetadata,
    PresetManifest,
    _sha256,
)
from .schemas import (
    ProducedCO2Assumption,
)


DEFAULT_SOURCE_MANIFEST = Path(
    r"C:\Users\mauli\Documents\boreyes2026\exports_hnp_expressive\final\manifest.json"
)
DEFAULT_DESIGN_RULES = REPO_ROOT / "data" / "jatibarang" / "feature005_seed_design.json"
DEFAULT_PRESET_ROOT = REPO_ROOT / "data" / "screening_presets"
GEOLOGY_FEATURES = (
    "poro_mean",
    "perm_mult",
    "anisotropy_ratio",
    "corridor_width_norm",
    "dip_relief_m",
    "local_structure_amp_m",
)
SECONDS_PER_DAY = 86_400.0


def _json_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest().upper()


def _normalized_maximin(rows: list[tuple[str, np.ndarray]], count: int) -> list[str]:
    if len(rows) < count:
        raise ValueError(f"need at least {count} accepted geologies, found {len(rows)}")
    ids = [item[0] for item in rows]
    values = np.asarray([item[1] for item in rows], dtype=np.float64)
    minimum = values.min(axis=0)
    span = values.max(axis=0) - minimum
    span[span == 0] = 1.0
    normalized = (values - minimum) / span
    median = np.median(normalized, axis=0)
    first = min(range(len(ids)), key=lambda index: (np.linalg.norm(normalized[index] - median), ids[index]))
    selected = [first]
    while len(selected) < count:
        remaining = [index for index in range(len(ids)) if index not in selected]
        best = min(
            remaining,
            key=lambda index: (
                -min(np.linalg.norm(normalized[index] - normalized[chosen]) for chosen in selected),
                ids[index],
            ),
        )
        selected.append(best)
    return sorted(ids[index] for index in selected)


def select_geologies(source_manifest: dict[str, Any], *, count: int = 20) -> list[dict[str, Any]]:
    entries = [
        item
        for item in source_manifest.get("entries", [])
        if item.get("status") == "accepted" and item.get("usable_for_training", False)
    ]
    by_case: dict[str, dict[str, Any]] = {}
    rows = []
    for entry in entries:
        case_id = str(entry["case_id"])
        params = dict(entry["params"])
        if case_id in by_case:
            continue
        by_case[case_id] = entry
        rows.append((case_id, np.asarray([float(params[name]) for name in GEOLOGY_FEATURES])))
    selected_ids = _normalized_maximin(rows, count)
    return [
        {
            "candidate_id": f"W{index:02d}",
            "source_case_id": case_id,
            "source_output_file": by_case[case_id]["output_file"],
            "params": by_case[case_id]["params"],
        }
        for index, case_id in enumerate(selected_ids, start=1)
    ]


def _schedule_rows(rules: dict[str, Any], preset_id: str) -> list[OperatingSchedule]:
    grid = rules["grid"]
    base = list(
        itertools.product(
            grid["injection_rate_m3_day"],
            grid["soak_duration_days"],
            grid["production_duration_days"],
            grid["production_bhp_psi"],
        )
    )
    if preset_id == "jatibarang_demo_v1":
        values = np.asarray(base, dtype=np.float64)
        minimum = values.min(axis=0)
        span = values.max(axis=0) - minimum
        span[span == 0] = 1.0
        normalized = (values - minimum) / span
        center = np.asarray([9000.0, 30.0, 190.0, 675.0])
        center = (center - minimum) / span
        first = min(range(len(base)), key=lambda index: (np.linalg.norm(normalized[index] - center), base[index]))
        selected = [first]
        while len(selected) < 5:
            remaining = [index for index in range(len(base)) if index not in selected]
            chosen = min(
                remaining,
                key=lambda index: (
                    -min(np.linalg.norm(normalized[index] - normalized[current]) for current in selected),
                    base[index],
                ),
            )
            selected.append(chosen)
        base = sorted(base[index] for index in selected)
    schedules = [
        OperatingSchedule(
            injection_rate_m3_day=rate,
            injection_duration_days=float(rules["fixed_injection_duration_days"]),
            soak_duration_days=soak,
            production_duration_days=production,
            production_bhp_psi=bhp,
            cycles=cycles,
        )
        for rate, soak, production, bhp in base
        for cycles in grid["cycles"]
    ]
    return sorted(schedules, key=lambda item: tuple(item.model_dump().values()))


def build_upstream_design(
    *,
    preset_id: str,
    source_manifest_path: Path = DEFAULT_SOURCE_MANIFEST,
    rules_path: Path = DEFAULT_DESIGN_RULES,
) -> dict[str, Any]:
    if preset_id not in EXPECTED_PRESETS:
        raise ValueError(f"unknown preset: {preset_id}")
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    rules = json.loads(rules_path.read_text(encoding="utf-8"))
    geologies = select_geologies(source_manifest)
    schedules = _schedule_rows(rules, preset_id)
    expected = EXPECTED_PRESETS[preset_id]
    logical = len(geologies) * len(schedules)
    if (logical, len(geologies), len(schedules)) != expected:
        raise ValueError(
            f"derived dimensions {(logical, len(geologies), len(schedules))} do not match {expected}"
        )
    payload = {
        "schema_version": "1.0",
        "preset_id": preset_id,
        "source_manifest": str(source_manifest_path),
        "source_manifest_sha256": _sha256(source_manifest_path),
        "rules_path": str(rules_path.relative_to(REPO_ROOT)),
        "rules_sha256": _sha256(rules_path),
        "selection_method": "normalized_maximin",
        "geology_features": list(GEOLOGY_FEATURES),
        "geologies": geologies,
        "schedules": [
            {
                "values": item.model_dump(mode="json"),
                "schedule_fingerprint": schedule_fingerprint(item),
            }
            for item in schedules
        ],
        "logical_scenarios": logical,
        "output_contract": {
            "file_name": "{candidate_id}--{schedule_fingerprint_prefix}.mat",
            "seed_frames": 8,
            "contents": "static maps, first eight dynamic frames, production increments, provenance",
        },
    }
    payload["design_sha256"] = _json_sha256(payload)
    return payload


def write_upstream_design(payload: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def build_workflow_smoke_design(full_design_path: Path) -> dict[str, Any]:
    """Select one central common schedule for a real 20-well UI smoke bank.

    This derived design is deliberately not a paper preset.  It provides the
    smallest honest common-schedule bank that can exercise the complete blank
    study workflow while the 3,240-run paper bank is still exporting.
    """

    payload = json.loads(Path(full_design_path).read_text(encoding="utf-8"))
    target = {
        "injection_rate_m3_day": 9000.0,
        "injection_reference_pressure_bar": 1.01325,
        "injection_reference_temperature_c": 15.0,
        "injection_duration_days": 45.0,
        "soak_duration_days": 30.0,
        "production_duration_days": 190.0,
        "production_bhp_psi": 675.0,
        "cycles": 4,
    }
    matches = [
        item
        for item in payload.get("schedules", [])
        if item.get("values") == target
    ]
    if len(matches) != 1:
        raise ValueError("full design does not contain the locked workflow smoke schedule")
    geologies = payload.get("geologies", [])
    if len(geologies) != 20:
        raise ValueError("workflow smoke design requires the locked 20 geologies")
    payload.update(
        {
            "preset_id": "jatibarang_workflow_smoke_v1",
            "schedules": matches,
            "logical_scenarios": 20,
            "purpose": "end_to_end_ui_smoke_not_paper_evidence",
        }
    )
    payload.pop("design_sha256", None)
    payload["design_sha256"] = _json_sha256(payload)
    return payload


def _grid(values: np.ndarray) -> Grid2D:
    return Grid2D.from_array(np.asarray(values, dtype=np.float32))


def _load_seed_case(
    path: Path,
    *,
    schedule: OperatingSchedule,
    source_id: str,
) -> tuple[GeologyInput, SeedHistory, str]:
    with h5py.File(path, "r") as handle:
        arrays = {
            key: np.asarray(handle[key], dtype=np.float32)
            for key in (
                "pressure",
                "gas_sat",
                "z_co2",
                "perm_map",
                "poro_map",
                "structure_map",
                "fracture_proxy_map",
                "barrier_map",
                "facies_map",
                "well_mask",
                "completion_mask",
            )
        }
        params = {
            key: float(np.asarray(handle["params"][key]).reshape(-1)[0])
            for key in handle["params"].keys()
        }
        dt = np.asarray(handle["dt_days"], dtype=np.float32).reshape(-1)
        stages = np.rint(np.asarray(handle["stage_labels"])).astype(np.int64).reshape(-1)
        oil_rate = np.asarray(handle["well_oil_rate"], dtype=np.float32).reshape(-1)
        gas_rate = np.asarray(handle["well_gas_rate"], dtype=np.float32).reshape(-1)
    if arrays["pressure"].shape[0] < 8:
        raise ValueError(f"{path} contains fewer than eight seed frames")
    geology = GeologyInput(
        permeability_md=_grid(np.power(10.0, arrays["perm_map"])),
        porosity_fraction=_grid(arrays["poro_map"]),
        structure_m=_grid(arrays["structure_map"]),
        fracture_proxy=_grid(arrays["fracture_proxy_map"]),
        barrier=_grid(arrays["barrier_map"]),
        facies=_grid(arrays["facies_map"]),
        well_mask=_grid(arrays["well_mask"]),
        completion_mask=_grid(arrays["completion_mask"]),
        anisotropy_ratio=params["anisotropy_ratio"],
        reservoir_temperature_c=91.0,
        length_x_m=900.0,
        length_y_m=600.0,
        thickness_m=6.0,
    )
    frames = [
        ReservoirState(
            pressure_bar=_grid(arrays["pressure"][index]),
            gas_saturation=_grid(arrays["gas_sat"][index]),
            z_co2=_grid(arrays["z_co2"][index]),
        )
        for index in range(8)
    ]
    produce = (stages == 3).astype(np.float32)
    seed = SeedHistory(
        initial_state=frames[0],
        frames=frames,
        oil_delta_m3=(np.abs(oil_rate) * dt * SECONDS_PER_DAY * produce)[:8].tolist(),
        gas_delta_m3=(np.abs(gas_rate) * dt * SECONDS_PER_DAY * produce)[:8].tolist(),
        source_class="derived_seed",
        source_id=source_id,
        schedule_fingerprint=schedule_fingerprint(schedule),
    )
    static_hash = _json_sha256(geology.model_dump(mode="json"))
    return geology, seed, static_hash


def import_seed_bank(
    *,
    design_path: Path,
    seed_root: Path,
    output_root: Path = DEFAULT_PRESET_ROOT,
    produced_co2_mole_fraction: float = 0.65,
) -> PresetManifest:
    design = json.loads(design_path.read_text(encoding="utf-8"))
    preset_id = str(design["preset_id"])
    schedules = [OperatingSchedule.model_validate(item["values"]) for item in design["schedules"]]
    exporter_manifest_path = seed_root / "manifest.json"
    if not exporter_manifest_path.exists():
        raise FileNotFoundError(f"upstream Feature 005 exporter manifest is missing: {exporter_manifest_path}")
    exporter_manifest = json.loads(exporter_manifest_path.read_text(encoding="utf-8"))
    expected_logical = len(design["geologies"]) * len(schedules)
    if exporter_manifest.get("design_sha256") != design.get("design_sha256"):
        raise ValueError("upstream exporter manifest design SHA-256 does not match the import design")
    if int(exporter_manifest.get("completed_runs", 0)) != expected_logical:
        raise ValueError(
            f"upstream exporter manifest is incomplete: expected {expected_logical} runs"
        )
    exporter_entries = exporter_manifest.get("entries", [])
    if isinstance(exporter_entries, dict):
        exporter_entries = [exporter_entries]
    exported_by_file = {str(item["output_file"]): item for item in exporter_entries}
    if len(exported_by_file) != expected_logical:
        raise ValueError("upstream exporter manifest does not contain every designed output")
    case_assumptions = load_assumptions()
    economic_basis = load_economic_basis()
    candidates_by_id = {str(item["id"]): item for item in case_assumptions["candidates"]}
    geology_count = len(design["geologies"])
    schedule_count = len(schedules)
    geology_maps = np.empty((geology_count, 8, 4096), dtype=np.float32)
    geology_scalars = np.empty((geology_count, 5), dtype=np.float32)
    seed_frames = np.empty((geology_count, schedule_count, 8, 3, 4096), dtype=np.float32)
    seed_oil_delta = np.empty((geology_count, schedule_count, 8), dtype=np.float32)
    seed_gas_delta = np.empty((geology_count, schedule_count, 8), dtype=np.float32)
    candidates: list[CompactPresetCandidate] = []
    source_files = []
    for geology_index, geology_row in enumerate(design["geologies"]):
        candidate_id = str(geology_row["candidate_id"])
        static_hash = None
        for schedule_index, active_schedule in enumerate(schedules):
            fingerprint = schedule_fingerprint(active_schedule)
            filename = f"{candidate_id}--{fingerprint[:12]}.mat"
            path = seed_root / filename
            if not path.exists():
                raise FileNotFoundError(f"derived seed export is missing: {path}")
            exporter_entry = exported_by_file.get(filename)
            if exporter_entry is None:
                raise ValueError(f"derived seed export is absent from the upstream manifest: {filename}")
            if (
                exporter_entry.get("candidate_id") != candidate_id
                or exporter_entry.get("schedule_fingerprint") != fingerprint
            ):
                raise ValueError(f"upstream exporter provenance mismatch for {filename}")
            geology, active_seed, current_static_hash = _load_seed_case(
                path,
                schedule=active_schedule,
                source_id=f"{preset_id}:{filename}",
            )
            if static_hash is not None and current_static_hash != static_hash:
                raise ValueError(f"static geology changed across fixed schedules for {candidate_id}")
            static_hash = current_static_hash
            if schedule_index == 0:
                geology_maps[geology_index] = np.asarray(
                    [
                        geology.permeability_md.values,
                        geology.porosity_fraction.values,
                        geology.structure_m.values,
                        geology.fracture_proxy.values,
                        geology.barrier.values,
                        geology.facies.values,
                        geology.well_mask.values,
                        geology.completion_mask.values,
                    ],
                    dtype=np.float32,
                )
                geology_scalars[geology_index] = np.asarray(
                    [
                        geology.anisotropy_ratio,
                        geology.reservoir_temperature_c,
                        geology.length_x_m,
                        geology.length_y_m,
                        geology.thickness_m,
                    ],
                    dtype=np.float32,
                )
            seed_frames[geology_index, schedule_index] = np.asarray(
                [
                    [
                        frame.pressure_bar.values,
                        frame.gas_saturation.values,
                        frame.z_co2.values,
                    ]
                    for frame in active_seed.frames
                ],
                dtype=np.float32,
            )
            seed_oil_delta[geology_index, schedule_index] = np.asarray(
                active_seed.oil_delta_m3, dtype=np.float32
            )
            seed_gas_delta[geology_index, schedule_index] = np.asarray(
                active_seed.gas_delta_m3, dtype=np.float32
            )
            source_files.append({"file": filename, "sha256": _sha256(path)})
        location = candidates_by_id[candidate_id]
        candidates.append(
            CompactPresetCandidate(
                candidate_id=candidate_id,
                location=Coordinate(
                    latitude=float(location["latitude"]), longitude=float(location["longitude"])
                ),
                produced_co2=ProducedCO2Assumption(
                    mole_fraction=produced_co2_mole_fraction,
                    provenance=EconomicProvenance(
                        source_class="engineering_assumption",
                        source_id="feature005-produced-gas-co2-v1",
                        notes="Explicit screening composition assumption; independent of storage inventory.",
                        metadata={"basis": "provenance_tagged_candidate_input"},
                    ),
                ),
            )
        )
    source_payload = case_assumptions["co2_source"]
    source = CO2Source(
        id=str(source_payload["id"]),
        name=str(source_payload["name"]),
        location=Coordinate(
            latitude=float(source_payload["latitude"]), longitude=float(source_payload["longitude"])
        ),
        capacity_tonnes_per_year=float(source_payload["capacity_tonnes_per_year"]),
        max_mass_flow_kg_s=float(source_payload["max_mass_flow_kg_s"]),
        outlet_pressure_bar=float(source_payload["outlet_pressure_bar"]),
        outlet_temperature_c=float(source_payload["outlet_temperature_c"]),
        co2_purity=float(source_payload["co2_purity"]),
    )
    metadata = CompactPresetMetadata(
        preset_id=preset_id,
        candidates=candidates,
        sources=[source],
        schedules=schedules,
        annual_co2_budget_tonnes=float(case_assumptions["economics"]["co2_budget_tonnes"]),
        carbon_prices=carbon_prices_from_basis(economic_basis),
        fiscal_cases=fiscal_cases_from_basis(economic_basis),
        economic_assumptions=assumptions_from_basis(economic_basis),
        project_life_years=int(case_assumptions["economics"]["project_life_years"]),
    )
    encoded = metadata.model_dump_json().encode("utf-8")
    preset_dir = output_root / preset_id
    preset_dir.mkdir(parents=True, exist_ok=True)
    payload_path = preset_dir / "payload.npz"
    np.savez_compressed(
        payload_path,
        metadata_json_utf8=np.frombuffer(encoded, dtype=np.uint8),
        geology_maps=geology_maps,
        geology_scalars=geology_scalars,
        seed_frames=seed_frames,
        seed_oil_delta=seed_oil_delta,
        seed_gas_delta=seed_gas_delta,
    )
    manifest = PresetManifest(
        preset_id=preset_id,
        logical_scenarios=len(candidates) * len(schedules),
        geology_count=geology_count,
        schedule_count=len(schedules),
        payload_file=payload_path.name,
        payload_sha256=_sha256(payload_path),
        design_sha256=_sha256(design_path),
        source_manifest=str(design["source_manifest"]),
        generated_at=datetime.now(timezone.utc).isoformat(),
        provenance={
            "policy": "derived_artifacts_only_no_raw_177_case_corpus",
            "payload_format": "compact_array_bank_v2",
            "source_files": source_files,
            "upstream_exporter_manifest_sha256": _sha256(exporter_manifest_path),
            "produced_co2_fraction": produced_co2_mole_fraction,
            "produced_co2_source": "feature005-produced-gas-co2-v1",
        },
    )
    (preset_dir / "manifest.json").write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build and import Feature 005 derived screening presets.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    design = subparsers.add_parser("design")
    design.add_argument("--preset", choices=sorted(EXPECTED_PRESETS), required=True)
    design.add_argument("--source-manifest", type=Path, default=DEFAULT_SOURCE_MANIFEST)
    design.add_argument("--rules", type=Path, default=DEFAULT_DESIGN_RULES)
    design.add_argument("--output", type=Path)
    workflow = subparsers.add_parser("workflow-design")
    workflow.add_argument("--full-design", type=Path, required=True)
    workflow.add_argument("--output", type=Path, required=True)
    importer = subparsers.add_parser("import")
    importer.add_argument("--design", type=Path, required=True)
    importer.add_argument("--seed-root", type=Path, required=True)
    importer.add_argument("--output-root", type=Path, default=DEFAULT_PRESET_ROOT)
    importer.add_argument("--produced-co2-mole-fraction", type=float, default=0.65)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "design":
        payload = build_upstream_design(
            preset_id=args.preset,
            source_manifest_path=args.source_manifest,
            rules_path=args.rules,
        )
        output = args.output or DEFAULT_PRESET_ROOT / args.preset / "upstream_design.json"
        write_upstream_design(payload, output)
        print(json.dumps({"output": str(output), "design_sha256": payload["design_sha256"]}))
        return 0
    if args.command == "workflow-design":
        payload = build_workflow_smoke_design(args.full_design)
        write_upstream_design(payload, args.output)
        print(json.dumps({"output": str(args.output), "design_sha256": payload["design_sha256"]}))
        return 0
    manifest = import_seed_bank(
        design_path=args.design,
        seed_root=args.seed_root,
        output_root=args.output_root,
        produced_co2_mole_fraction=args.produced_co2_mole_fraction,
    )
    print(manifest.model_dump_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
