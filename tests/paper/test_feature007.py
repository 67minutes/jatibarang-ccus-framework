from __future__ import annotations

import json
import hashlib
import shutil
import csv
from collections import Counter
from pathlib import Path

import pytest

from jatibarang_ccus.paper.feature007 import (
    _accepted_manifest_status,
    _arm_c_result_status,
    _dwsim_topk_status,
    build_feature007_bundle,
    freeze_feature007_bundle,
    select_arm_b_design,
    select_arm_b_replacement_order,
    verify_feature007_bundle,
)


def _design() -> dict:
    geologies = [
        {
            "candidate_id": f"W{index:02d}",
            "source_case_id": f"case_{index:04d}",
        }
        for index in range(1, 21)
    ]
    schedules = []
    index = 0
    for rate in (8000.0, 9000.0, 10000.0):
        for soak in (25.0, 30.0, 35.0):
            for production in (170.0, 190.0, 210.0):
                for bhp in (650.0, 675.0, 700.0):
                    for cycles in (3, 4):
                        index += 1
                        schedules.append(
                            {
                                "schedule_fingerprint": f"{index:064X}",
                                "values": {
                                    "injection_rate_m3_day": rate,
                                    "injection_duration_days": 45.0,
                                    "soak_duration_days": soak,
                                    "production_duration_days": production,
                                    "production_bhp_psi": bhp,
                                    "cycles": cycles,
                                },
                            }
                        )
    return {
        "schema_version": "1.0",
        "preset_id": "jatibarang_full_v1",
        "geologies": geologies,
        "schedules": schedules,
    }


def _fake_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    design_path = (
        root
        / "data"
        / "screening_presets"
        / "jatibarang_full_v1"
        / "upstream_design.json"
    )
    design_path.parent.mkdir(parents=True)
    design_path.write_text(json.dumps(_design()), encoding="utf-8")
    return root


def test_arm_b_design_is_seeded_balanced_and_unique() -> None:
    first = select_arm_b_design(_design(), seed=20260717)
    second = select_arm_b_design(_design(), seed=20260717)

    assert first == second
    assert len(first) == 40
    assert Counter(row["candidate_id"] for row in first) == {
        f"W{index:02d}": 2 for index in range(1, 21)
    }
    assert len({row["schedule_fingerprint"] for row in first}) == 40
    replacements = select_arm_b_replacement_order(_design(), first, seed=20260717)
    assert len(replacements) == 20 * 160
    assert Counter(row["candidate_id"] for row in replacements) == {
        f"W{index:02d}": 160 for index in range(1, 21)
    }


def test_working_bundle_is_deterministic_and_explicitly_blocked(tmp_path: Path) -> None:
    root = _fake_root(tmp_path)
    preflight = root / "paper" / "validation" / "feature007" / "execution_preflight.json"
    preflight.parent.mkdir(parents=True)
    preflight.write_text(
        json.dumps(
            {
                "schema_version": "feature007-execution-preflight-v1",
                "benchmark": {"status": "NOT_RUN", "completed_runs": 0},
                "concurrency": {"selected_workers": 0},
                "launch": {"demo_200": "NOT_LAUNCHED", "full_3240": "NOT_LAUNCHED"},
            }
        ),
        encoding="utf-8",
    )
    stale_crossover = (
        root
        / "paper"
        / "validation"
        / "feature007"
        / "pipeline_cost_crossover.csv"
    )
    stale_crossover.write_text(
        "source_class\nscreening_cost_proxy\n",
        encoding="utf-8",
    )
    bundle = build_feature007_bundle(root=root, generated_at="2026-07-17T00:00:00+07:00")
    first_manifest = (bundle / "manifest.json").read_bytes()
    first_design = (bundle / "tables" / "arm_b_design.csv").read_bytes()

    rebuilt = build_feature007_bundle(root=root, generated_at="2026-07-17T00:00:00+07:00")
    assert (rebuilt / "manifest.json").read_bytes() == first_manifest
    assert (rebuilt / "tables" / "arm_b_design.csv").read_bytes() == first_design
    assert verify_feature007_bundle(rebuilt, root=root) == []

    manifest = json.loads((rebuilt / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["scenario_count"] == 0
    assert manifest["execution"]["concurrency"]["selected_workers"] == 0
    assert "paper/validation/feature007/execution_preflight.json" in manifest["input_hashes"]
    assert manifest["validation"]["fabricated_result"] is False
    assignments = manifest["experiment_design"]["arm_c"]
    assert assignments["independent_assignment_count"] == 20
    assert assignments["correlated_assignment_count"] == 20
    assert assignments["resolve_grouping"] == "assignment_x_carbon_price"
    assert assignments["named_well_single_assignment_claim"] is False
    assignment_table = bundle / assignments["assignment_table"]
    assert len(assignment_table.read_text(encoding="utf-8").splitlines()) == 801
    assert manifest["figures"]["4"]["status"] == "blocked"
    assert manifest["figures"]["8"]["status"] == "blocked"
    assert "pipeline_cost_crossover_final" not in manifest["tables"]

    with pytest.raises(ValueError, match="bundle_id"):
        build_feature007_bundle(root=root, bundle_id="../../outside")


def test_verifier_detects_tampered_table(tmp_path: Path) -> None:
    root = _fake_root(tmp_path)
    bundle = build_feature007_bundle(root=root)
    with (bundle / "tables" / "arm_b_design.csv").open("a", encoding="utf-8") as handle:
        handle.write("tampered\n")
    assert "table arm_b_design SHA-256 mismatch" in verify_feature007_bundle(bundle, root=root)


def test_freeze_refuses_partial_bundle(tmp_path: Path) -> None:
    root = _fake_root(tmp_path)
    source = build_feature007_bundle(root=root)
    with pytest.raises(ValueError, match="only a scientifically ready"):
        freeze_feature007_bundle(
            source,
            source.parent / "submitted",
            frozen_at="2026-07-21T18:00:00+07:00",
            root=root,
        )


def test_strict_experiment_dependencies_require_exact_evidence(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    run_dir = root / "data" / "scenario_a_runs"
    run_dir.mkdir(parents=True)
    entries = []
    for index in range(2):
        output = run_dir / f"slot-{index}.mat"
        output.write_bytes(f"accepted-{index}".encode())
        entries.append(
            {
                "slot_id": f"A-{index}",
                "attempt_id": f"A-{index}-attempt-1",
                "candidate_id": f"W{index + 1:02d}",
                "source_case_id": f"case_{index + 1:04d}",
                "status": "accepted",
                "runtime_seconds": 1.0,
                "output_file": output.name,
                "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                "solver_converged": True,
                "expected_step_count": 36,
                "actual_step_count": 36,
                "finite_arrays": True,
                "sanity_passed": True,
            }
        )
    manifest = run_dir / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "feature007-mrst-manifest-v1",
                "arm": "A",
                "target_accepted": 2,
                "design_sha256": "A" * 64,
                "generator_sha256_before": "B" * 64,
                "generator_sha256_after": "C" * 64,
                "accepted_runs": 2,
                "failed_runs": 0,
                "failed_hashes": [],
                "entries": entries,
            }
        ),
        encoding="utf-8",
    )
    assert _accepted_manifest_status(manifest, root, 2)["ready"] is True

    entries[0]["finite_arrays"] = False
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "feature007-mrst-manifest-v1",
                "target_accepted": 2,
                "design_sha256": "A" * 64,
                "generator_sha256_before": "B" * 64,
                "generator_sha256_after": "C" * 64,
                "accepted_runs": 2,
                "failed_hashes": [],
                "entries": entries,
            }
        ),
        encoding="utf-8",
    )
    status = _accepted_manifest_status(manifest, root, 2)
    assert status["ready"] is False
    assert "scientific gates" in status["reason"]


def test_arm_c_and_dwsim_gates_reconcile_locked_counts(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    result = root / "paper" / "validation" / "feature007" / "arm_c_screening.json"
    result.parent.mkdir(parents=True)
    payload_hash = "A" * 64
    artifacts = {}
    for name in (
        "screening_surface.csv",
        "carbon_price_rankings.csv",
        "carbon_price_regret.csv",
        "npv_vs_carbon_price.csv",
    ):
        artifact = result.parent / name
        artifact.write_text(f"{name}\n", encoding="utf-8")
        artifacts[name] = {
            "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()
        }
    result.write_text(
        json.dumps(
            {
                "schema_version": "feature007-arm-c-v1",
                "status": "complete",
                "actual_scenario_count": 3240,
                "independent_assignment_count": 20,
                "correlated_assignment_count": 20,
                "downstream_resolve_count": 160,
                    "screen_result_summary": {
                        "logical_scenario_count": 3240,
                        "result_sha256": "9" * 64,
                    },
                "cache": {
                    "predicted_count": 3240,
                    "reused_count": 0,
                    "cache_entry_count": 3240,
                    "cache_content_sha256": "B" * 64,
                },
                "shortlist": [
                    {
                        "plan_id": f"plan-{index}",
                        "scenario_id": f"scenario-{index}",
                        "designated_carbon_price_scenario_id": "p40",
                    }
                    for index in range(5)
                ],
                    "field_scenario_summary": {
                        "independent_record_count": 80,
                        "correlated_record_count": 80,
                        "surrogate_evaluations_during_resolve": 0,
                        "result_sha256": "F" * 64,
                    },
                "artifacts": artifacts,
                "provenance": {
                    "preset_id": "jatibarang_full_v1",
                    "preset_payload_sha256": payload_hash,
                    "checkpoint_sha256": "C" * 64,
                    "preset_design_sha256": "D" * 64,
                    "field_scenario_design_sha256": "E" * 64,
                },
            }
        ),
        encoding="utf-8",
    )
    arm_c = _arm_c_result_status(
        result,
        root=root,
        promoted={"ready": True, "payload_sha256": payload_hash},
    )
    assert arm_c["ready"] is True
    assert arm_c["shortlist"]["ready"] is True
    assert arm_c["figure5"]["ready"] is False

    topk = result.parent / "topk_confirmation.csv"
    with topk.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "plan_id",
                "throughput_class",
                "dwsim_converged",
                "dwsim_mass_balance_residual_fraction",
            ),
        )
        writer.writeheader()
        classes = ("minimum", "median", "maximum", "", "")
        for index, throughput_class in enumerate(classes):
            writer.writerow(
                {
                    "plan_id": f"plan-{index}",
                    "throughput_class": throughput_class,
                    "dwsim_converged": index < 3,
                    "dwsim_mass_balance_residual_fraction": (
                        "0.0001" if index < 3 else ""
                    ),
                }
            )
    assert _dwsim_topk_status(topk)["ready"] is True


def test_real_figure3_case_exports_truth_prediction_and_residual(tmp_path: Path) -> None:
    root = _fake_root(tmp_path)
    repository = Path(__file__).resolve().parents[2]
    case_target = root / "data" / "validation_cases" / "case_0016.mat"
    cache_target = root / "paper" / "figures" / ".fig03_rollout_cache.npz"
    case_target.parent.mkdir(parents=True)
    cache_target.parent.mkdir(parents=True)
    shutil.copyfile(repository / "data" / "validation_cases" / "case_0016.mat", case_target)
    shutil.copyfile(repository / "paper" / "figures" / ".fig03_rollout_cache.npz", cache_target)

    bundle = build_feature007_bundle(root=root)
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    record = manifest["reservoirs"]["case_0016"]
    payload = json.loads((bundle / record["path"]).read_text(encoding="utf-8"))

    assert record["available"] is True
    assert payload["geometry"]["dimensions"] == [64, 64, 1]
    assert payload["dynamic"]["mrst_truth"]["shape"] == [40, 64, 64]
    assert payload["dynamic"]["surrogate_free_rollout"]["shape"] == [40, 64, 64]
    assert payload["dynamic"]["residual_prediction_minus_truth"]["shape"] == [40, 64, 64]
    assert payload["warm_start"]["gas_saturation"]["shape"] == [8, 64, 64]
    assert set(payload["validation_cohort"]["cases"]) == {
        "case_0016",
        "case_0115",
        "case_0176",
        "case_0197",
        "case_0209",
    }
    assert payload["shared_limits"]["gas_saturation"] == [0.0, 0.72]
    assert payload["shared_limits"]["permeability_md"][1] > 100.0
    assert payload["provenance"]["mrst_source_class"] == "offline_mrst_ground_truth"
    assert verify_feature007_bundle(bundle, root=root) == []
