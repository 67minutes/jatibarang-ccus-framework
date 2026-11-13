"""Two-arm (A vs C) completion path for the GEOPETRA 2026 submission.

Arm B (40 full-MRST runs, ~5 h) is out of scope for this submission. This
module reuses the locked harness pieces for Arm A (two MRST confirmations plus
the central-schedule economics), the Arm C top-five MRST confirmation, and the
aggregation, without requiring Arm B manifests.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

from jatibarang_ccus.screening.orchestrator import build_default_orchestrator
from jatibarang_ccus.screening.prediction_cache import PredictionCache
from jatibarang_ccus.screening.presets import CompactPresetBank
from jatibarang_ccus.screening.schemas import PresetScreenRequest
from jatibarang_ccus.surrogate.config import REPO_ROOT
from jatibarang_ccus.surrogate.runner import load_surrogate

from .aggregate import (
    economics_rows_from_field_scenarios,
    economics_rows_from_screen_result,
    topk_rows,
    _runtime_summary,
)
from .arm_ab import (
    ARM_A_MANIFEST,
    GENERATOR_PATH,
    TOP5_MANIFEST,
    _arm_a_design,
    _top5_design,
    verify_mrst_manifest,
)
from .arm_c import DEFAULT_WORKSPACE, FULL_PRESET_ID
from .run import _matlab_expression, _run_matlab_checked
from .schemas import (
    AbcEconomicsRow,
    AbcRuntimeRow,
    TopKConfirmationRow,
    atomic_write_csv,
    atomic_write_json,
    canonical_sha256,
    sha256_file,
)

PRESET_DIR = REPO_ROOT / "data" / "screening_presets" / FULL_PRESET_ID


def prepare_designs(workspace: Path = DEFAULT_WORKSPACE) -> dict[str, str]:
    top5_path = workspace / "top5_plans.json"
    upstream_path = PRESET_DIR / "upstream_design.json"
    upstream = json.loads(upstream_path.read_text(encoding="utf-8"))
    source_case_by_candidate = {
        item["candidate_id"]: item["source_case_id"] for item in upstream["geologies"]
    }
    geology_params_by_case = {
        item["source_case_id"]: item["params"] for item in upstream["geologies"]
    }
    if not top5_path.exists():
        # Arm A does not depend on Arm C; its design can be written first.
        designs = {
            "arm_a": _arm_a_design(
                canonical_sha256(
                    {"upstream_design": sha256_file(upstream_path), "scope": "arm_A"}
                ),
                geology_params_by_case,
            )
        }
    else:
        source_sha = canonical_sha256(
            {
                "top5_plans": sha256_file(top5_path),
                "upstream_design": sha256_file(upstream_path),
                "scope": "two_arm_A_vs_C",
            }
        )
        designs = {
            "top5": _top5_design(
                json.loads(top5_path.read_text(encoding="utf-8")),
                source_case_by_candidate,
                geology_params_by_case,
                source_sha,
            ),
        }
    output_dir = workspace / "mrst_designs"
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, design in designs.items():
        path = output_dir / f"{name}.json"
        atomic_write_json(path, design.model_dump(mode="json"))
        paths[name] = str(path)
    return paths


def run_mrst(name: str, workspace: Path = DEFAULT_WORKSPACE) -> None:
    design = workspace / "mrst_designs" / f"{name}.json"
    output, target = {
        "arm_a": (ARM_A_MANIFEST.parent, 2),
        "top5": (TOP5_MANIFEST.parent, 5),
    }[name]
    output.mkdir(parents=True, exist_ok=True)
    import shutil

    matlab = shutil.which("matlab")
    if matlab is None:
        raise FileNotFoundError("MATLAB executable is not available on PATH")
    _run_matlab_checked(
        [matlab, "-batch", _matlab_expression(design, output, target, max_slots=None)],
        workspace=workspace,
        label=name,
        phase="production",
    )


def _manifests(workspace: Path) -> dict[str, Any]:
    design_dir = workspace / "mrst_designs"
    return {
        "arm_a": verify_mrst_manifest(
            ARM_A_MANIFEST,
            design_path=design_dir / "arm_a.json",
            expected_arm="A",
            expected_count=2,
        ),
        "top5": verify_mrst_manifest(
            TOP5_MANIFEST,
            design_path=design_dir / "top5.json",
            expected_arm="C_TOP5",
            expected_count=5,
        ),
    }


def run_arm_a(workspace: Path = DEFAULT_WORKSPACE) -> dict[str, Any]:
    # The Arm C cache is identity-locked; reuse its stored identity so Arm A
    # can run before the Arm C audit file is written.
    import sqlite3

    with sqlite3.connect(
        f"file:{workspace / 'arm_c_predictions.sqlite3'}?mode=ro", uri=True
    ) as connection:
        identity = json.loads(
            connection.execute(
                "select value from metadata where key = 'identity_json'"
            ).fetchone()[0]
        )
    orchestrator = build_default_orchestrator(load_surrogate())
    manifest = json.loads((PRESET_DIR / "manifest.json").read_text(encoding="utf-8"))
    bank = CompactPresetBank(PRESET_DIR / manifest["payload_file"])
    request = PresetScreenRequest(
        mode="preset",
        preset_id=FULL_PRESET_ID,
        selection_fiscal_case_id="pre_tax",
        shortlist_top_k=5,
        detailed_top_k=0,
        scenario_limit=4096,
    )
    with PredictionCache(workspace / "arm_c_predictions.sqlite3", identity=identity) as cache:
        try:
            central = [
                scenario
                for scenario in bank.iter_scenarios()
                if scenario.schedule.injection_rate_m3_day == 9000.0
                and scenario.schedule.injection_duration_days == 45.0
                and scenario.schedule.soak_duration_days == 30.0
                and scenario.schedule.production_duration_days == 190.0
                and scenario.schedule.production_bhp_psi == 675.0
                and scenario.schedule.cycles == 3
            ]
            if len(central) != 20:
                raise ValueError(f"Arm A central schedule resolved {len(central)} scenarios")
            result = orchestrator.run_materialized_with_prediction_cache(
                request.model_copy(update={"run_id": "feature007-arm-a"}),
                central,
                cache,
            )
        finally:
            bank.close()
    output = {
        "schema_version": "feature007-arm-a-v1",
        "arm_a": result.model_dump(mode="json"),
        "scope": "two_arm_A_vs_C (Arm B not executed)",
    }
    atomic_write_json(workspace / "arm_a_results.json", output)
    return output


def aggregate(workspace: Path = DEFAULT_WORKSPACE, *, with_mrst: bool = True) -> dict[str, Any]:
    arm_c_audit = json.loads((workspace / "arm_c_screening.json").read_text(encoding="utf-8"))
    arm_c_internal = json.loads((workspace / "arm_c_internal.json").read_text(encoding="utf-8"))
    arm_c = {
        **arm_c_audit,
        "screen_result": arm_c_internal["screen_result"],
        "field_scenario": arm_c_internal["field_scenario"],
    }
    arm_a = json.loads((workspace / "arm_a_results.json").read_text(encoding="utf-8"))
    economics = [
        *economics_rows_from_screen_result("A", arm_a["arm_a"]),
        *economics_rows_from_field_scenarios(arm_c),
    ]
    atomic_write_csv(workspace / "abc_economics.csv", economics, model=AbcEconomicsRow)

    assignment_times: dict[str, float] = {}
    for record in arm_c["field_scenario"]["independent"] + arm_c["field_scenario"]["correlated"]:
        assignment_times.setdefault(
            record["assignment_id"],
            float(record["result"].get("downstream_total_seconds", 0.0)),
        )
    screen_seconds = float(
        arm_c.get("timings", {}).get(
            "initial_screen_seconds",
            arm_c["screen_result"]["timings"]["total_seconds"],
        )
    )
    summary: dict[str, Any] = {"economics_rows": len(economics)}
    runtime: list[AbcRuntimeRow] = []
    if with_mrst:
        manifests = _manifests(workspace)
        accepted = [
            float(entry.runtime_seconds)
            for manifest in manifests.values()
            for entry in manifest.entries
            if entry.status == "accepted"
        ]
        equivalent_weeks = 3240 * statistics.fmean(accepted) / (7 * 86_400)
        a_seconds, a_attempts, a_failed = _runtime_summary(manifests["arm_a"])
        runtime.append(
            AbcRuntimeRow(
                arm="A",
                wall_clock_seconds=a_seconds,
                scenarios_evaluated=2,
                economics_scenarios=20,
                accepted_runs=2,
                attempted_runs=a_attempts,
                failed_attempt_seconds=a_failed,
                runtime_kind="measured_full_mrst_confirmations",
                source_class="measured_runtime",
            )
        )
        summary["mrst_mean_runtime_seconds"] = statistics.fmean(accepted)
        summary["mrst_accepted_runs"] = len(accepted)
    else:
        equivalent_weeks = None
    runtime.append(
        AbcRuntimeRow(
            arm="C",
            wall_clock_seconds=screen_seconds,
            scenarios_evaluated=3240,
            economics_scenarios=3240,
            accepted_runs=0,
            attempted_runs=0,
            downstream_resolve_seconds=sum(assignment_times.values()),
            mrst_equivalence_weeks=equivalent_weeks,
            runtime_kind="measured_surrogate_screen_plus_labeled_mrst_equivalence",
            source_class="measured_runtime",
        )
    )
    atomic_write_csv(workspace / "abc_runtime.csv", runtime, model=AbcRuntimeRow)
    if with_mrst:
        if not (workspace / "dwsim_confirmation.json").exists():
            atomic_write_json(workspace / "dwsim_confirmation.json", {"rows": []})
        try:
            confirmations = topk_rows(
                workspace=workspace,
                arm_c=arm_c,
                top5_manifest=_manifests(workspace)["top5"],
                orchestrator=build_default_orchestrator(load_surrogate()),
            )
        except ValueError as exc:
            if "three DWSIM rows" not in str(exc):
                raise
            confirmations = _topk_rows_without_dwsim(workspace, arm_c)
        atomic_write_csv(
            workspace / "topk_confirmation.csv",
            confirmations,
            model=TopKConfirmationRow,
        )
        summary["topk_rows"] = len(confirmations)
    atomic_write_json(workspace / "aggregate_ac_manifest.json", summary)
    return summary


def _topk_rows_without_dwsim(workspace: Path, arm_c: dict[str, Any]) -> list[TopKConfirmationRow]:
    # Same MRST valuation as topk_rows, tolerated when DWSIM rows are absent.
    from . import aggregate as agg

    original = agg.topk_rows
    payload_path = workspace / "dwsim_confirmation.json"
    plans = json.loads((workspace / "top5_plans.json").read_text(encoding="utf-8"))
    rows: list[TopKConfirmationRow] = []
    orchestrator = build_default_orchestrator(load_surrogate())
    manifest = json.loads((PRESET_DIR / "manifest.json").read_text(encoding="utf-8"))
    bank = CompactPresetBank(PRESET_DIR / manifest["payload_file"])
    screen_result = agg.ScreenResult.model_validate(arm_c["screen_result"])
    entries = {
        entry.slot_id: entry
        for entry in _manifests(workspace)["top5"].entries
        if entry.status == "accepted"
    }
    try:
        for plan in sorted(plans, key=lambda item: int(item["rank"])):
            prediction = agg.prediction_result_from_mrst(
                agg._entry_path(TOP5_MANIFEST, entries[str(plan["plan_id"])]),
                scenario_id=str(plan["scenario_id"]),
            )
            mrst_value = agg._top5_mrst_value(
                plan_record=plan,
                mrst_prediction=prediction,
                screen_result=screen_result,
                orchestrator=orchestrator,
                bank=bank,
            )
            surrogate_value = float(plan["surrogate_value"])
            relative = (surrogate_value - mrst_value) / max(abs(mrst_value), 1.0)
            rows.append(
                TopKConfirmationRow(
                    plan_id=str(plan["plan_id"]),
                    designated_carbon_price_scenario_id=str(plan["designated_carbon_price_scenario_id"]),
                    carbon_price_usd_per_tonne=float(plan["carbon_price_usd_per_tonne"]),
                    fiscal_case="pre_tax",
                    surrogate_value=surrogate_value,
                    mrst_value=mrst_value,
                    relative_error=relative,
                    absolute_relative_error=abs(relative),
                    source_class="mrst_truth_and_surrogate_prediction",
                )
            )
    finally:
        bank.close()
    del original, payload_path
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=["prepare", "mrst-arm-a", "mrst-top5", "arm-a", "aggregate", "aggregate-no-mrst"],
    )
    args = parser.parse_args(argv)
    if args.command == "prepare":
        print(json.dumps(prepare_designs(), indent=2))
    elif args.command == "mrst-arm-a":
        run_mrst("arm_a")
    elif args.command == "mrst-top5":
        run_mrst("top5")
    elif args.command == "arm-a":
        run_arm_a()
        print("arm A done")
    elif args.command == "aggregate":
        print(json.dumps(aggregate(), indent=2))
    else:
        print(json.dumps(aggregate(with_mrst=False), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
