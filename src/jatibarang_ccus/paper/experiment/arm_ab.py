from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Mapping

import CoolProp.CoolProp as CP
import numpy as np

from jatibarang_ccus.imports.mrst import load_mrst_reservoir
from jatibarang_ccus.screening.orchestrator import (
    ScreeningOrchestrator,
    build_default_orchestrator,
)
from jatibarang_ccus.screening.prediction_cache import PredictionCache
from jatibarang_ccus.screening.presets import CompactPresetBank
from jatibarang_ccus.screening.schemas import PresetScreenRequest
from jatibarang_ccus.surrogate.config import REPO_ROOT
from jatibarang_ccus.surrogate.postprocessing import (
    co2_density_kg_m3,
    plume_summary,
    reservoir_inventory_tonnes,
)
from jatibarang_ccus.surrogate.preprocessing import extrapolation_flags
from jatibarang_ccus.surrogate.runner import load_surrogate
from jatibarang_ccus.surrogate.schemas import (
    ConfidenceMetadata,
    Grid2D,
    InventorySeries,
    PlumeSummary,
    PredictRequest,
    PredictionResult,
    ProductionSeries,
    SpatialFrame,
    TimelineStep,
)

from .arm_c import DEFAULT_WORKSPACE, FULL_PRESET_ID
from .schemas import (
    MrstDesign,
    MrstDesignAttempt,
    MrstDesignSlot,
    MrstManifest,
    atomic_write_json,
    canonical_sha256,
    sha256_file,
)


GENERATOR_PATH = (
    Path("C:/Users/mauli/Documents/boreyes2026/data/generate_hnp_dataset.m")
)
ARM_A_MANIFEST = REPO_ROOT / "data" / "scenario_a_runs" / "manifest.json"
ARM_B_MANIFEST = REPO_ROOT / "data" / "scenario_b_runs" / "manifest.json"
TOP5_MANIFEST = (
    REPO_ROOT / "data" / "scenario_c_topk_runs" / "manifest.json"
)

SCHEDULE_FIELDS = (
    "injection_rate_m3_day",
    "injection_duration_days",
    "soak_duration_days",
    "production_duration_days",
    "production_bhp_psi",
    "cycles",
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _schedule_from_row(row: Mapping[str, Any]) -> dict[str, float | int]:
    return {
        field: (
            int(float(row[field]))
            if field == "cycles"
            else float(row[field])
        )
        for field in SCHEDULE_FIELDS
    }


def _finalize_design(design: MrstDesign) -> MrstDesign:
    payload = design.model_dump(mode="json", exclude={"design_sha256"})
    return design.model_copy(
        update={"design_sha256": canonical_sha256(payload)}
    )


def _arm_a_design(
    source_sha: str,
    geology_params_by_case: Mapping[str, dict[str, float | int]],
) -> MrstDesign:
    schedule = {
        "injection_rate_m3_day": 9000.0,
        "injection_duration_days": 45.0,
        "soak_duration_days": 30.0,
        "production_duration_days": 190.0,
        "production_bhp_psi": 675.0,
        "cycles": 3,
    }
    representatives = (
        ("low", "W09", "case_0090"),
        ("median", "W12", "case_0109"),
    )
    slots = [
        MrstDesignSlot(
            slot_id=f"arm-a-{label}",
            candidate_id=candidate,
            source_case_id=source_case,
            geology_params=geology_params_by_case[source_case],
            attempts=[
                MrstDesignAttempt(
                    attempt_id=f"arm-a-{label}-primary",
                    candidate_id=candidate,
                    source_case_id=source_case,
                    schedule=schedule,
                )
            ],
            replacement_allowed=False,
        )
        for label, candidate, source_case in representatives
    ]
    return _finalize_design(
        MrstDesign(
            arm="A",
            target_accepted=2,
            slots=slots,
            source_design_sha256=source_sha,
        )
    )


def _arm_b_design(
    design_rows: list[dict[str, str]],
    replacement_rows: list[dict[str, str]],
    source_sha: str,
    geology_params_by_case: Mapping[str, dict[str, float | int]],
) -> MrstDesign:
    if len(design_rows) != 40:
        raise ValueError(f"Arm B design must contain 40 rows, got {len(design_rows)}")
    replacements: dict[str, list[dict[str, str]]] = {}
    for row in replacement_rows:
        replacements.setdefault(row["candidate_id"], []).append(row)
    for rows in replacements.values():
        rows.sort(key=lambda item: int(item["replacement_rank"]))

    occurrence: dict[str, int] = {}
    slots: list[MrstDesignSlot] = []
    for row in sorted(design_rows, key=lambda item: int(item["selection_rank"])):
        candidate = row["candidate_id"]
        occurrence[candidate] = occurrence.get(candidate, 0) + 1
        lane = occurrence[candidate] - 1
        primary = MrstDesignAttempt(
            attempt_id=f"arm-b-{int(row['selection_rank']):02d}-primary",
            candidate_id=candidate,
            source_case_id=row["source_case_id"],
            schedule=_schedule_from_row(row),
        )
        attempts = [primary]
        for replacement in replacements.get(candidate, [])[lane::2]:
            if (
                replacement["schedule_fingerprint"]
                == row["schedule_fingerprint"]
            ):
                continue
            attempts.append(
                MrstDesignAttempt(
                    attempt_id=(
                        f"arm-b-{int(row['selection_rank']):02d}-"
                        f"replacement-{int(replacement['replacement_rank']):03d}"
                    ),
                    candidate_id=candidate,
                    source_case_id=row["source_case_id"],
                    schedule=_schedule_from_row(replacement),
                )
            )
        slots.append(
            MrstDesignSlot(
                slot_id=f"arm-b-{int(row['selection_rank']):02d}",
                candidate_id=candidate,
                source_case_id=row["source_case_id"],
                geology_params=geology_params_by_case[row["source_case_id"]],
                attempts=attempts,
                replacement_allowed=True,
            )
        )
    attempt_ids = [
        attempt.attempt_id for slot in slots for attempt in slot.attempts
    ]
    if len(attempt_ids) != len(set(attempt_ids)):
        raise ValueError("Arm B attempt IDs must be unique")
    return _finalize_design(
        MrstDesign(
            arm="B",
            target_accepted=40,
            slots=slots,
            source_design_sha256=source_sha,
        )
    )


def _top5_design(
    plans: list[dict[str, Any]],
    source_case_by_candidate: Mapping[str, str],
    geology_params_by_case: Mapping[str, dict[str, float | int]],
    source_sha: str,
) -> MrstDesign:
    if len(plans) != 5 or len({plan["scenario_id"] for plan in plans}) != 5:
        raise ValueError("Arm C confirmation design requires five unique plans")
    slots = []
    for plan in sorted(plans, key=lambda item: int(item["rank"])):
        candidate = str(plan["candidate_id"])
        slots.append(
            MrstDesignSlot(
                slot_id=str(plan["plan_id"]),
                candidate_id=candidate,
                source_case_id=source_case_by_candidate[candidate],
                geology_params=geology_params_by_case[
                    source_case_by_candidate[candidate]
                ],
                attempts=[
                    MrstDesignAttempt(
                        attempt_id=f"{plan['plan_id']}-primary",
                        candidate_id=candidate,
                        source_case_id=source_case_by_candidate[candidate],
                        schedule={
                            key: value
                            for key, value in plan["schedule"].items()
                            if key in SCHEDULE_FIELDS
                        },
                    )
                ],
                replacement_allowed=False,
            )
        )
    return _finalize_design(
        MrstDesign(
            arm="C_TOP5",
            target_accepted=5,
            slots=slots,
            source_design_sha256=source_sha,
        )
    )


def prepare_mrst_designs(
    *,
    workspace: Path = DEFAULT_WORKSPACE,
) -> dict[str, str]:
    bundle = REPO_ROOT / "paper" / "results" / "feature007" / "working"
    arm_b_path = bundle / "tables" / "arm_b_design.csv"
    replacements_path = bundle / "tables" / "arm_b_replacement_order.csv"
    top5_path = workspace / "top5_plans.json"
    upstream_path = (
        REPO_ROOT
        / "data"
        / "screening_presets"
        / FULL_PRESET_ID
        / "upstream_design.json"
    )
    required = [arm_b_path, replacements_path, top5_path, upstream_path]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "MRST design inputs are missing: " + ", ".join(missing)
        )
    upstream = json.loads(upstream_path.read_text(encoding="utf-8"))
    source_case_by_candidate = {
        item["candidate_id"]: item["source_case_id"]
        for item in upstream["geologies"]
    }
    geology_params_by_case = {
        item["source_case_id"]: item["params"]
        for item in upstream["geologies"]
    }
    source_sha = canonical_sha256(
        {
            "arm_b_design": sha256_file(arm_b_path),
            "arm_b_replacements": sha256_file(replacements_path),
            "top5_plans": sha256_file(top5_path),
            "upstream_design": sha256_file(upstream_path),
        }
    )
    designs = {
        "arm_a": _arm_a_design(source_sha, geology_params_by_case),
        "arm_b": _arm_b_design(
            _read_csv(arm_b_path),
            _read_csv(replacements_path),
            source_sha,
            geology_params_by_case,
        ),
        "top5": _top5_design(
            json.loads(top5_path.read_text(encoding="utf-8")),
            source_case_by_candidate,
            geology_params_by_case,
            source_sha,
        ),
    }
    output_dir = workspace / "mrst_designs"
    output_dir.mkdir(parents=True, exist_ok=True)
    output: dict[str, str] = {}
    for name, design in designs.items():
        path = output_dir / f"{name}.json"
        atomic_write_json(path, design.model_dump(mode="json"))
        output[name] = str(path)
    generator_sha = sha256_file(GENERATOR_PATH)
    backup_path = Path(
        str(GENERATOR_PATH) + ".pre-feature007-20260724.bak"
    )
    generator_before = (
        sha256_file(backup_path) if backup_path.exists() else generator_sha
    )
    atomic_write_json(
        workspace / "mrst_generator_provenance.json",
        {
            "generator_path": str(GENERATOR_PATH),
            "generator_sha256_before": generator_before,
            "generator_sha256_after": generator_sha,
            "source_design_sha256": source_sha,
            "raw_corpus_copied": False,
        },
    )
    return output


def verify_mrst_manifest(
    path: Path,
    *,
    design_path: Path,
    expected_arm: str,
    expected_count: int,
) -> MrstManifest:
    design = MrstDesign.model_validate_json(
        design_path.read_text(encoding="utf-8")
    )
    expected_design_hash = canonical_sha256(
        design.model_dump(mode="json", exclude={"design_sha256"})
    )
    if design.design_sha256 != expected_design_hash:
        raise ValueError(f"{design_path} has an invalid internal design hash")
    if design.arm != expected_arm or design.target_accepted != expected_count:
        raise ValueError(f"{design_path} does not match the locked arm contract")
    manifest = MrstManifest.model_validate_json(
        path.read_text(encoding="utf-8")
    )
    if manifest.arm != expected_arm:
        raise ValueError(f"{path} declares arm {manifest.arm}, expected {expected_arm}")
    if manifest.target_accepted != expected_count:
        raise ValueError(f"{path} has the wrong accepted target")
    if manifest.design_sha256 != design.design_sha256:
        raise ValueError(f"{path} does not match {design_path.name}")
    generator_after = sha256_file(GENERATOR_PATH)
    backup_path = Path(
        str(GENERATOR_PATH) + ".pre-feature007-20260724.bak"
    )
    generator_before = (
        sha256_file(backup_path)
        if backup_path.exists()
        else generator_after
    )
    if manifest.generator_sha256_after != generator_after:
        raise ValueError(f"{path} generator-after hash is stale")
    if manifest.generator_sha256_before != generator_before:
        raise ValueError(f"{path} generator-before hash is stale")
    if manifest.accepted_runs != expected_count:
        raise ValueError(
            f"{path} has {manifest.accepted_runs}/{expected_count} accepted runs"
        )
    if manifest.failed_hashes:
        raise ValueError(f"{path} contains failed accepted-output hashes")
    accepted = [entry for entry in manifest.entries if entry.status == "accepted"]
    if len(accepted) != expected_count:
        raise ValueError(f"{path} accepted entry count does not reconcile")
    if len({entry.slot_id for entry in accepted}) != expected_count:
        raise ValueError(f"{path} does not have one accepted run per slot")
    slots = {slot.slot_id: slot for slot in design.slots}
    attempt_specs = {
        attempt.attempt_id: (slot, attempt)
        for slot in design.slots
        for attempt in slot.attempts
    }
    if len({entry.attempt_id for entry in manifest.entries}) != len(
        manifest.entries
    ):
        raise ValueError(f"{path} contains duplicate attempt entries")
    if manifest.failed_runs != sum(
        entry.status == "failed" for entry in manifest.entries
    ):
        raise ValueError(f"{path} failed-run count does not reconcile")
    for entry in manifest.entries:
        if entry.slot_id not in slots or entry.attempt_id not in attempt_specs:
            raise ValueError(
                f"MRST attempt identity is absent from design: {entry.attempt_id}"
            )
        slot, attempt = attempt_specs[entry.attempt_id]
        if (
            slot.slot_id != entry.slot_id
            or attempt.candidate_id != entry.candidate_id
            or attempt.source_case_id != entry.source_case_id
        ):
            raise ValueError(
                f"MRST attempt identity differs from design: {entry.attempt_id}"
            )
        locked_expected_steps = 12 * int(attempt.schedule["cycles"])
        if entry.expected_step_count != locked_expected_steps:
            raise ValueError(
                f"MRST attempt step contract differs from design: "
                f"{entry.attempt_id}"
            )
    for entry in accepted:
        if not (
            entry.solver_converged
            and entry.finite_arrays
            and entry.sanity_passed
            and entry.actual_step_count == entry.expected_step_count
        ):
            raise ValueError(
                f"accepted MRST entry fails scientific gates: {entry.attempt_id}"
            )
        output = Path(entry.output_file)
        if not output.is_absolute():
            output = path.parent / output
        if not output.exists():
            raise FileNotFoundError(output)
        if sha256_file(output) != entry.output_sha256.upper():
            raise ValueError(f"MRST output hash mismatch: {output}")
    return manifest


def verify_all_mrst_manifests(
    *,
    workspace: Path = DEFAULT_WORKSPACE,
) -> dict[str, MrstManifest]:
    design_dir = workspace / "mrst_designs"
    return {
        "arm_a": verify_mrst_manifest(
            ARM_A_MANIFEST,
            design_path=design_dir / "arm_a.json",
            expected_arm="A",
            expected_count=2,
        ),
        "arm_b": verify_mrst_manifest(
            ARM_B_MANIFEST,
            design_path=design_dir / "arm_b.json",
            expected_arm="B",
            expected_count=40,
        ),
        "top5": verify_mrst_manifest(
            TOP5_MANIFEST,
            design_path=design_dir / "top5.json",
            expected_arm="C_TOP5",
            expected_count=5,
        ),
    }


def _cycles_from_stages(stages: np.ndarray) -> np.ndarray:
    output = np.ones(len(stages), dtype=int)
    active_cycle = 1
    for index in range(1, len(stages)):
        if stages[index] == 1 and stages[index - 1] != 1:
            active_cycle += 1
        output[index] = active_cycle
    return output


def prediction_result_from_mrst(
    path: Path,
    *,
    scenario_id: str,
    include_fields: bool = False,
) -> PredictionResult:
    imported = load_mrst_reservoir(path)
    targets = imported.targets
    required = {
        "pressure",
        "gas_sat",
        "z_co2",
        "oil_sat",
        "oil_delta_m3",
        "gas_delta_m3",
        "dt_days",
        "stage_labels",
    }
    missing = sorted(required - set(targets))
    if missing:
        raise ValueError(
            f"MRST confirmation lacks full-history arrays: {missing}"
        )
    pressure = np.asarray(targets["pressure"], dtype=np.float64)
    gas = np.asarray(targets["gas_sat"], dtype=np.float64)
    z_co2 = np.asarray(targets["z_co2"], dtype=np.float64)
    oil_sat = np.asarray(targets["oil_sat"], dtype=np.float64)
    oil_delta = np.asarray(targets["oil_delta_m3"], dtype=np.float64)
    gas_delta = np.asarray(targets["gas_delta_m3"], dtype=np.float64)
    dt_days = np.asarray(targets["dt_days"], dtype=np.float64)
    stages = np.asarray(targets["stage_labels"], dtype=int)
    count = len(dt_days)
    arrays = [
        pressure,
        gas,
        z_co2,
        oil_sat,
        oil_delta,
        gas_delta,
        dt_days,
        stages,
    ]
    if any(len(value) != count for value in arrays):
        raise ValueError("MRST full-history arrays do not share one step count")
    if count <= 8 or not all(np.all(np.isfinite(value)) for value in arrays):
        raise ValueError("MRST confirmation is incomplete or non-finite")
    if np.any(dt_days <= 0):
        raise ValueError("MRST confirmation contains non-positive timesteps")
    if not set(np.unique(stages)).issubset({1, 2, 3}):
        raise ValueError("MRST confirmation contains unknown schedule stages")
    elapsed = np.cumsum(dt_days)
    cycles = _cycles_from_stages(stages)
    timeline = [
        TimelineStep(
            index=index,
            dt_days=float(dt_days[index]),
            elapsed_days=float(elapsed[index]),
            stage=("inject", "soak", "produce")[int(stages[index]) - 1],
            cycle=int(cycles[index]),
            origin="mrst",
        )
        for index in range(count)
    ]
    geology = imported.geology
    density = co2_density_kg_m3(
        pressure,
        geology.reservoir_temperature_c,
    )
    cell_volume = (
        geology.length_x_m
        * geology.length_y_m
        * geology.thickness_m
        / (64 * 64)
    )
    inventory = reservoir_inventory_tonnes(
        geology.porosity_fraction.as_array(dtype=np.float64),
        gas,
        z_co2,
        density,
        cell_volume,
    )
    reference_density = float(
        CP.PropsSI(
            "D",
            "P",
            imported.schedule.injection_reference_pressure_bar * 1e5,
            "T",
            imported.schedule.injection_reference_temperature_c + 273.15,
            "CO2",
        )
    )
    injected = np.cumsum(
        (stages == 1)
        * imported.schedule.injection_rate_m3_day
        * dt_days
        * reference_density
        / 1000.0
    )
    initial_inventory = float(inventory[0])
    produced_back = np.maximum(0.0, injected - (inventory - initial_inventory))
    residual = initial_inventory + injected - produced_back - inventory
    plume: PlumeSummary = plume_summary(
        gas,
        z_co2,
        geology.completion_mask.as_array(),
        cell_area_m2=(
            geology.length_x_m * geology.length_y_m / (64 * 64)
        ),
    )
    request = PredictRequest(
        scenario_id=scenario_id,
        geology=geology,
        schedule=imported.schedule,
        seed=imported.seed,
    )
    fields = None
    if include_fields:
        fields = [
            SpatialFrame(
                step_index=index,
                pressure_bar=Grid2D.from_array(pressure[index]),
                gas_saturation=Grid2D.from_array(gas[index]),
                z_co2=Grid2D.from_array(z_co2[index]),
                oil_saturation=Grid2D.from_array(oil_sat[index]),
                origin="mrst",
            )
            for index in range(count)
        ]
    return PredictionResult(
        scenario_id=scenario_id,
        timeline=timeline,
        production=ProductionSeries(
            delta_oil_m3=oil_delta.astype(float).tolist(),
            delta_gas_m3=gas_delta.astype(float).tolist(),
            cumulative_oil_m3=np.cumsum(oil_delta).astype(float).tolist(),
            cumulative_gas_m3=np.cumsum(gas_delta).astype(float).tolist(),
        ),
        inventory=InventorySeries(
            status="available",
            co2_inventory_tonnes=inventory.astype(float).tolist(),
            injected_co2_tonnes=injected.astype(float).tolist(),
            produced_back_co2_tonnes=produced_back.astype(float).tolist(),
            reconciliation_residual_tonnes=residual.astype(float).tolist(),
            method=(
                "porosity * cell_volume * gas_sat * z_co2 * CoolProp "
                "pure-CO2 density"
            ),
            caveat=(
                "Framework-comparable engineering inventory applied to MRST "
                "states; this is not a dedicated produced-CO2 head."
            ),
        ),
        plume=plume,
        extrapolation_flags=list(extrapolation_flags(request)),
        confidence=ConfidenceMetadata(
            band="mrst_truth",
            horizon_steps=count,
            metrics={
                "source": "offline_full_compositional_mrst",
                "trajectory_uncertainty_fraction": 0.0,
            },
            extended_horizon=False,
            low_confidence_reasons=[],
        ),
        provenance={
            "source_class": "mrst_truth",
            "source_file": path.name,
            "source_sha256": imported.sha256,
            "schedule_fingerprint": imported.seed.schedule_fingerprint,
            "runtime_coupled": False,
            "inventory_accounting": "framework_comparable_adapter",
        },
        fields=fields,
    )


def _accepted_entries(
    manifest: MrstManifest,
) -> dict[str, Any]:
    return {
        entry.attempt_id: entry
        for entry in manifest.entries
        if entry.status == "accepted"
    }


def _entry_path(manifest_path: Path, entry: Any) -> Path:
    path = Path(entry.output_file)
    return path if path.is_absolute() else manifest_path.parent / path


def run_arm_ab(
    *,
    workspace: Path = DEFAULT_WORKSPACE,
    orchestrator: ScreeningOrchestrator | None = None,
) -> dict[str, Any]:
    manifests = verify_all_mrst_manifests(workspace=workspace)
    arm_c = json.loads(
        (workspace / "arm_c_screening.json").read_text(encoding="utf-8")
    )
    cache_identity = {
        key: str(arm_c["provenance"][key])
        for key in (
            "checkpoint_sha256",
            "preset_id",
            "preset_payload_sha256",
            "preset_design_sha256",
        )
    }
    if orchestrator is None:
        orchestrator = build_default_orchestrator(load_surrogate())
    preset_dir = (
        REPO_ROOT / "data" / "screening_presets" / FULL_PRESET_ID
    )
    preset_manifest = json.loads(
        (preset_dir / "manifest.json").read_text(encoding="utf-8")
    )
    bank = CompactPresetBank(
        preset_dir / preset_manifest["payload_file"]
    )
    request = PresetScreenRequest(
        mode="preset",
        preset_id=FULL_PRESET_ID,
        selection_fiscal_case_id="pre_tax",
        shortlist_top_k=5,
        detailed_top_k=0,
        scenario_limit=4096,
    )
    with PredictionCache(
        workspace / "arm_c_predictions.sqlite3",
        identity=cache_identity,
    ) as surrogate_cache:
        try:
            central = []
            arm_b_by_attempt: dict[str, Any] = {}
            design = MrstDesign.model_validate_json(
                (workspace / "mrst_designs" / "arm_b.json").read_text(
                    encoding="utf-8"
                )
            )
            accepted_attempts = _accepted_entries(manifests["arm_b"])
            attempt_lookup = {
                attempt.attempt_id: attempt
                for slot in design.slots
                for attempt in slot.attempts
            }
            accepted_specs = {
                attempt_id: attempt_lookup[attempt_id]
                for attempt_id in accepted_attempts
            }
            for scenario in bank.iter_scenarios():
                schedule = scenario.schedule
                if (
                    schedule.injection_rate_m3_day == 9000.0
                    and schedule.injection_duration_days == 45.0
                    and schedule.soak_duration_days == 30.0
                    and schedule.production_duration_days == 190.0
                    and schedule.production_bhp_psi == 675.0
                    and schedule.cycles == 3
                ):
                    central.append(scenario)
                for attempt_id, attempt in accepted_specs.items():
                    if (
                        scenario.candidate_id == attempt.candidate_id
                        and all(
                            float(getattr(schedule, key))
                            == float(value)
                            for key, value in attempt.schedule.items()
                        )
                    ):
                        arm_b_by_attempt[attempt_id] = scenario
            if len(central) != 20:
                raise ValueError(
                    f"Arm A central schedule resolved {len(central)} scenarios"
                )
            if set(arm_b_by_attempt) != set(accepted_specs):
                missing = sorted(set(accepted_specs) - set(arm_b_by_attempt))
                raise ValueError(
                    f"Arm B accepted schedules are absent from the preset: {missing}"
                )
            arm_a_result = orchestrator.run_materialized_with_prediction_cache(
                request.model_copy(update={"run_id": "feature007-arm-a"}),
                central,
                surrogate_cache,
            )
            mrst_cache = {}
            arm_b_scenarios = []
            for attempt_id, scenario in sorted(arm_b_by_attempt.items()):
                entry = accepted_attempts[attempt_id]
                prediction = prediction_result_from_mrst(
                    _entry_path(ARM_B_MANIFEST, entry),
                    scenario_id=scenario.scenario_id,
                )
                mrst_cache[scenario.input_fingerprint] = prediction
                arm_b_scenarios.append(scenario)
            arm_b_result = orchestrator.run_materialized_with_prediction_cache(
                request.model_copy(update={"run_id": "feature007-arm-b"}),
                arm_b_scenarios,
                mrst_cache,
            )
        finally:
            bank.close()
    output = {
        "schema_version": "feature007-arm-ab-v1",
        "arm_a": arm_a_result.model_dump(mode="json"),
        "arm_b": arm_b_result.model_dump(mode="json"),
        "manifest_summary": {
            name: {
                "accepted_runs": manifest.accepted_runs,
                "failed_runs": manifest.failed_runs,
                "design_sha256": manifest.design_sha256,
            }
            for name, manifest in manifests.items()
        },
        "fair_comparison": {
            "orchestrator_class": type(orchestrator).__name__,
            "economic_evaluator": getattr(
                orchestrator.services.economic_evaluator,
                "__name__",
                type(orchestrator.services.economic_evaluator).__name__,
            ),
            "same_downstream_path": True,
        },
    }
    atomic_write_json(workspace / "arm_ab_results.json", output)
    return output
