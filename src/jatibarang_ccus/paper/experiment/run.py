from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Callable

import psutil

from jatibarang_ccus.surrogate.config import REPO_ROOT

from .aggregate import aggregate_experiment
from .arm_ab import (
    ARM_A_MANIFEST,
    ARM_B_MANIFEST,
    GENERATOR_PATH,
    TOP5_MANIFEST,
    prepare_mrst_designs,
    run_arm_ab,
    verify_all_mrst_manifests,
)
from .arm_c import DEFAULT_WORKSPACE, run_arm_c
from .dwsim_confirm import run_dwsim_confirmation
from .schemas import (
    AbcEconomicsRow,
    AbcRuntimeRow,
    CarbonPriceRankingRow,
    CarbonPriceRegretRow,
    DwsimConfirmationRow,
    NpvVsCarbonPriceRow,
    PipelineCostCrossoverRow,
    PipelinePressureRow,
    PipelineRouteRow,
    ScreeningSurfaceRow,
    TopKConfirmationRow,
    atomic_write_json,
    read_validated_csv,
    sha256_file,
)


STAGED_FILES = (
    "screening_surface.csv",
    "pipeline_route.csv",
    "pipeline_pressure_profile.csv",
    "pipeline_cost_crossover.csv",
    "carbon_price_rankings.csv",
    "carbon_price_regret.csv",
    "npv_vs_carbon_price.csv",
    "abc_economics.csv",
    "abc_runtime.csv",
    "topk_confirmation.csv",
    "arm_c_screening.json",
)
MRST_MEMORY_RESERVE_BYTES = 3 * 1024**3

STAGED_TABLE_MODELS = {
    "screening_surface.csv": ScreeningSurfaceRow,
    "pipeline_route.csv": PipelineRouteRow,
    "pipeline_pressure_profile.csv": PipelinePressureRow,
    "pipeline_cost_crossover.csv": PipelineCostCrossoverRow,
    "carbon_price_rankings.csv": CarbonPriceRankingRow,
    "carbon_price_regret.csv": CarbonPriceRegretRow,
    "npv_vs_carbon_price.csv": NpvVsCarbonPriceRow,
    "abc_economics.csv": AbcEconomicsRow,
    "abc_runtime.csv": AbcRuntimeRow,
    "topk_confirmation.csv": TopKConfirmationRow,
}

STAGED_TABLE_COUNTS = {
    "screening_surface.csv": 120,
    "pipeline_cost_crossover.csv": 153,
    "carbon_price_rankings.csv": 16,
    "carbon_price_regret.csv": 16,
    "npv_vs_carbon_price.csv": 16,
    "abc_economics.csv": 12,
    "abc_runtime.csv": 3,
    "topk_confirmation.csv": 5,
}

STAGED_UNIQUE_FIELDS = {
    "screening_surface.csv": (
        "geology_id",
        "injection_rate_m3_day",
        "cycles",
    ),
    "pipeline_route.csv": ("route_id", "point_order"),
    "pipeline_pressure_profile.csv": ("route_id", "distance_km"),
    "pipeline_cost_crossover.csv": (
        "cost_case",
        "annual_tonnes",
        "mode",
    ),
    "carbon_price_rankings.csv": (
        "scenario_id",
        "carbon_price_usd_per_tonne",
    ),
    "carbon_price_regret.csv": (
        "chosen_price_scenario",
        "realized_price_scenario",
    ),
    "npv_vs_carbon_price.csv": (
        "scenario_id",
        "carbon_price_usd_per_tonne",
    ),
    "abc_economics.csv": ("arm", "carbon_price_usd_per_tonne"),
    "abc_runtime.csv": ("arm",),
    "topk_confirmation.csv": ("plan_id",),
}


def _run_checked(command: list[str], *, cwd: Path = REPO_ROOT) -> None:
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed with exit code {completed.returncode}: "
            + " ".join(command)
        )


def _validate_stage_tables(
    workspace: Path,
    *,
    table_names: set[str] | None = None,
) -> None:
    selected_names = table_names or set(STAGED_TABLE_MODELS)
    for name, model in STAGED_TABLE_MODELS.items():
        if name not in selected_names:
            continue
        rows = read_validated_csv(workspace / name, model=model)
        expected = STAGED_TABLE_COUNTS.get(name)
        if expected is not None and len(rows) != expected:
            raise ValueError(
                f"{name} contains {len(rows)} rows, expected {expected}"
            )
        keys = STAGED_UNIQUE_FIELDS[name]
        identities = {
            tuple(getattr(row, field) for field in keys)
            for row in rows
        }
        if len(identities) != len(rows):
            raise ValueError(f"{name} contains duplicate row identities")

    if "topk_confirmation.csv" in selected_names:
        topk = read_validated_csv(
            workspace / "topk_confirmation.csv",
            model=TopKConfirmationRow,
        )
        dwsim = [row for row in topk if row.dwsim_converged is True]
        if len(dwsim) != 3 or {
            row.throughput_class for row in dwsim
        } != {"minimum", "median", "maximum"}:
            raise ValueError(
                "topk_confirmation.csv lacks three min/median/max DWSIM rows"
            )


def _matlab_expression(
    design: Path,
    output: Path,
    target: int,
    *,
    max_slots: int | None,
) -> str:
    def quoted(path: Path) -> str:
        return str(path).replace("'", "''").replace("\\", "/")

    options = (
        f"'mode','feature007_full',"
        f"'feature007_design','{quoted(design)}',"
        f"'feature007_output','{quoted(output)}',"
        f"'feature007_target_accepted',{target},"
        "'feature007_resume',true"
    )
    if max_slots is not None:
        options += f",'feature007_max_slots',{max_slots}"
    return (
        f"cd('{quoted(GENERATOR_PATH.parent)}');"
        f"generate_hnp_dataset({options});"
    )


def _mrst_preflight_path(workspace: Path) -> Path:
    return workspace / "mrst_execution_preflight.json"


def _load_mrst_preflight(workspace: Path) -> dict:
    path = _mrst_preflight_path(workspace)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "schema_version": "feature007-mrst-execution-preflight-v1",
        "required_reserve_bytes": MRST_MEMORY_RESERVE_BYTES,
        "execution_policy": (
            "smoke_one_full_slot_per_design_then_sequential_workers_sized_by_"
            "measured_peak_rss_with_3_gib_reserve"
        ),
        "runs": [],
    }


def _assert_mrst_memory_reserve(
    workspace: Path,
    *,
    require_measured_worker: bool,
) -> None:
    available = int(psutil.virtual_memory().available)
    payload = _load_mrst_preflight(workspace)
    measured_peaks = [
        int(run["peak_worker_rss_bytes"])
        for run in payload.get("runs", [])
        if run.get("phase") == "smoke"
        and int(run.get("returncode", 1)) == 0
    ]
    peak = max(measured_peaks, default=0)
    if require_measured_worker and not measured_peaks:
        ready = False
        reason = "no successful full-slot smoke RSS measurement exists"
    else:
        required = MRST_MEMORY_RESERVE_BYTES + (
            peak if require_measured_worker else 0
        )
        ready = available >= required
        reason = (
            ""
            if ready
            else (
                f"requires {required / 1024**3:.2f} GiB available "
                "for one measured worker plus the 3 GiB reserve"
            )
        )
    payload["last_gate"] = {
        "captured_at": datetime.now().astimezone().isoformat(),
        "available_memory_bytes": available,
        "measured_peak_worker_rss_bytes": peak or None,
        "require_measured_worker": require_measured_worker,
        "selected_workers": 1 if ready else 0,
        "reason": reason,
    }
    atomic_write_json(_mrst_preflight_path(workspace), payload)
    if not ready:
        raise RuntimeError(
            "MRST launch blocked by the locked RAM formula: " + reason
        )


def _run_matlab_checked(
    command: list[str],
    *,
    workspace: Path,
    label: str,
    phase: str,
) -> None:
    process = subprocess.Popen(command, cwd=REPO_ROOT)
    peak_worker_rss = 0
    minimum_available = int(psutil.virtual_memory().available)
    observed = psutil.Process(process.pid)
    while process.poll() is None:
        try:
            processes = [observed, *observed.children(recursive=True)]
            rss = sum(
                item.memory_info().rss
                for item in processes
                if item.is_running()
            )
            peak_worker_rss = max(peak_worker_rss, rss)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        minimum_available = min(
            minimum_available,
            int(psutil.virtual_memory().available),
        )
        time.sleep(0.25)
    returncode = int(process.wait())
    payload = _load_mrst_preflight(workspace)
    payload.setdefault("runs", []).append(
        {
            "label": label,
            "phase": phase,
            "captured_at": datetime.now().astimezone().isoformat(),
            "peak_worker_rss_bytes": peak_worker_rss,
            "minimum_available_memory_bytes": minimum_available,
            "returncode": returncode,
        }
    )
    atomic_write_json(_mrst_preflight_path(workspace), payload)
    if returncode != 0:
        raise RuntimeError(
            f"MATLAB command failed with exit code {returncode}: "
            + " ".join(command)
        )


def run_mrst_batches(
    *,
    workspace: Path = DEFAULT_WORKSPACE,
    smoke_only: bool = False,
) -> None:
    designs = {
        name: Path(path)
        for name, path in prepare_mrst_designs(workspace=workspace).items()
    }
    matlab = shutil.which("matlab")
    if matlab is None:
        raise FileNotFoundError("MATLAB executable is not available on PATH")
    batches = (
        ("arm_a", designs["arm_a"], ARM_A_MANIFEST.parent, 2),
        ("arm_b", designs["arm_b"], ARM_B_MANIFEST.parent, 40),
        ("top5", designs["top5"], TOP5_MANIFEST.parent, 5),
    )
    for name, design, output, target in batches:
        _assert_mrst_memory_reserve(
            workspace,
            require_measured_worker=False,
        )
        output.mkdir(parents=True, exist_ok=True)
        _run_matlab_checked(
            [
                matlab,
                "-batch",
                _matlab_expression(
                    design,
                    output,
                    target,
                    max_slots=1,
                ),
            ],
            workspace=workspace,
            label=name,
            phase="smoke",
        )
    if smoke_only:
        return
    for name, design, output, target in batches:
        _assert_mrst_memory_reserve(
            workspace,
            require_measured_worker=True,
        )
        _run_matlab_checked(
            [
                matlab,
                "-batch",
                _matlab_expression(
                    design,
                    output,
                    target,
                    max_slots=None,
                ),
            ],
            workspace=workspace,
            label=name,
            phase="production",
        )
    verify_all_mrst_manifests(workspace=workspace)


def stage_experiment(
    *,
    workspace: Path = DEFAULT_WORKSPACE,
    render: bool = True,
) -> dict:
    arm_c = json.loads(
        (workspace / "arm_c_screening.json").read_text(encoding="utf-8")
    )
    aggregate = json.loads(
        (workspace / "aggregate_manifest.json").read_text(encoding="utf-8")
    )
    dwsim = json.loads(
        (workspace / "dwsim_confirmation.json").read_text(encoding="utf-8")
    )
    if (
        arm_c.get("status") != "complete"
        or arm_c.get("actual_scenario_count") != 3240
        or arm_c.get("independent_assignment_count") != 20
        or arm_c.get("correlated_assignment_count") != 20
        or arm_c.get("downstream_resolve_count") != 160
    ):
        raise ValueError("Arm C is not complete enough to stage")
    figure5_ready = arm_c.get("figure5", {}).get("ready") is True
    if (
        arm_c.get("shortlist_status", {}).get("ready") is not True
        or len(arm_c.get("shortlist", [])) != 5
    ):
        raise ValueError(
            "Arm C five-plan shortlist remains blocked: "
            + str(
                arm_c.get("shortlist_status", {}).get(
                    "reason",
                    "missing shortlist audit",
                )
            )
        )
    if aggregate.get("status") != "complete":
        raise ValueError("A/B/C aggregation is incomplete")
    if (
        dwsim.get("status") != "complete"
        or dwsim.get("expected_case_count") != 3
        or len(dwsim.get("rows", [])) != 3
    ):
        raise ValueError("DWSIM confirmation is incomplete")
    dwsim_rows = [
        DwsimConfirmationRow.model_validate(row)
        for row in dwsim["rows"]
    ]
    if any(not row.converged for row in dwsim_rows):
        raise ValueError("DWSIM confirmation contains a non-converged row")
    verify_all_mrst_manifests(workspace=workspace)
    figure5_files = {
        "pipeline_route.csv",
        "pipeline_pressure_profile.csv",
        "pipeline_cost_crossover.csv",
    }
    stage_files = tuple(
        name
        for name in STAGED_FILES
        if figure5_ready or name not in figure5_files
    )
    missing = [
        str(workspace / name)
        for name in stage_files
        if not (workspace / name).exists()
    ]
    if missing:
        raise FileNotFoundError(
            "experiment stage inputs are missing: " + ", ".join(missing)
        )
    _validate_stage_tables(
        workspace,
        table_names={
            name for name in stage_files if name.endswith(".csv")
        },
    )

    for manifest, names in (
        (
            arm_c,
            tuple(
                name
                for name in (
                    "screening_surface.csv",
                    "pipeline_route.csv",
                    "pipeline_pressure_profile.csv",
                    "pipeline_cost_crossover.csv",
                    "carbon_price_rankings.csv",
                    "carbon_price_regret.csv",
                    "npv_vs_carbon_price.csv",
                )
                if figure5_ready or name not in figure5_files
            ),
        ),
        (
            aggregate,
            (
                "abc_economics.csv",
                "abc_runtime.csv",
                "topk_confirmation.csv",
            ),
        ),
    ):
        for name in names:
            expected_hash = str(
                manifest.get("artifacts", {})
                .get(name, {})
                .get("sha256", "")
            ).upper()
            if len(expected_hash) != 64:
                raise ValueError(f"{name} lacks a complete manifest hash")
            if sha256_file(workspace / name) != expected_hash:
                raise ValueError(f"{name} does not match its manifest hash")

    destination = REPO_ROOT / "paper" / "validation" / "feature007"
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="feature007-stage-",
        dir=workspace,
    ) as temporary:
        temporary_path = Path(temporary)
        for name in stage_files:
            shutil.copy2(workspace / name, temporary_path / name)
        for name in stage_files:
            os.replace(temporary_path / name, destination / name)

    _run_checked(
        [
            sys.executable,
            "-m",
            "jatibarang_ccus.paper.feature007",
            "build",
            "--bundle-id",
            "working",
        ]
    )
    _run_checked(
        [
            sys.executable,
            "-m",
            "jatibarang_ccus.paper.feature007",
            "verify",
            "--bundle-id",
            "working",
        ]
    )
    bundle_manifest_path = (
        REPO_ROOT
        / "paper"
        / "results"
        / "feature007"
        / "working"
        / "manifest.json"
    )
    bundle_manifest = json.loads(
        bundle_manifest_path.read_text(encoding="utf-8")
    )
    blocked = {
        figure: bundle_manifest["figures"][figure]
        for figure in ("4", "5", "7", "8")
        if bundle_manifest["figures"][figure]["status"] != "ready"
    }
    if render:
        scripts = {
            "4": "fig04_screening_surface.py",
            "5": "fig05_pipeline.py",
            "7": "fig07_carbon_price_pivot.py",
            "8": "fig08_abc_economics.py",
        }
        for figure, script in scripts.items():
            if figure in blocked:
                continue
            _run_checked(
                [
                    sys.executable,
                    str(REPO_ROOT / "paper" / "figures" / script),
                    "--bundle",
                    str(bundle_manifest_path.parent),
                ]
            )
    ready_figures = [
        int(figure)
        for figure in ("4", "5", "7", "8")
        if figure not in blocked
    ]
    result = {
        "status": (
            "complete" if not blocked else "complete_with_scientific_blocker"
        ),
        "bundle": str(bundle_manifest_path.parent),
        "figures_ready": ready_figures,
        "figures_blocked": blocked,
        "mechanical_validation": "PASS",
        "scientific_promotion": (
            "PENDING_REVIEW" if not blocked else "BLOCKED"
        ),
        "immutable_bundle_written": False,
    }
    atomic_write_json(workspace / "stage_manifest.json", result)
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace",
        type=Path,
        default=DEFAULT_WORKSPACE,
    )
    parser.add_argument(
        "--phase",
        choices=("arm_c", "mrst", "dwsim", "aggregate", "stage", "all"),
        help="compatibility interface for the approved phased design",
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("arm-c")
    sub.add_parser("prepare-mrst")
    sub.add_parser("mrst-smoke")
    sub.add_parser("mrst")
    sub.add_parser("verify-mrst")
    sub.add_parser("arm-ab")
    sub.add_parser("dwsim-confirm")
    sub.add_parser("aggregate")
    stage = sub.add_parser("stage")
    stage.add_argument("--no-render", action="store_true")
    sub.add_parser("all")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    command = args.command
    if command is None and args.phase is not None:
        command = args.phase.replace("_", "-")
    if command is None:
        raise SystemExit("choose a command or --phase")
    workspace = args.workspace
    actions: dict[str, Callable[[], object]] = {
        "arm-c": lambda: run_arm_c(workspace=workspace),
        "prepare-mrst": lambda: prepare_mrst_designs(workspace=workspace),
        "mrst-smoke": lambda: run_mrst_batches(
            workspace=workspace,
            smoke_only=True,
        ),
        "mrst": lambda: run_mrst_batches(workspace=workspace),
        "verify-mrst": lambda: verify_all_mrst_manifests(
            workspace=workspace
        ),
        "arm-ab": lambda: run_arm_ab(workspace=workspace),
        "dwsim-confirm": lambda: run_dwsim_confirmation(
            workspace=workspace
        ),
        "aggregate": lambda: aggregate_experiment(workspace=workspace),
        "stage": lambda: stage_experiment(
            workspace=workspace,
            render=not getattr(args, "no_render", False),
        ),
    }
    if command == "dwsim":
        command = "dwsim-confirm"
    if command == "all":
        run_arm_c(workspace=workspace)
        run_mrst_batches(workspace=workspace)
        run_arm_ab(workspace=workspace)
        run_dwsim_confirmation(workspace=workspace)
        aggregate_experiment(workspace=workspace)
        stage_experiment(workspace=workspace)
        return 0
    if command not in actions:
        raise SystemExit(f"unsupported command: {command}")
    result = actions[command]()
    if result is not None:
        print(
            json.dumps(
                result,
                indent=2,
                default=lambda value: (
                    value.model_dump(mode="json")
                    if hasattr(value, "model_dump")
                    else str(value)
                ),
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
