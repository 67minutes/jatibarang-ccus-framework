from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any

import CoolProp.CoolProp as CP

from jatibarang_ccus.surrogate.config import REPO_ROOT

from .arm_c import DEFAULT_WORKSPACE
from .schemas import (
    DwsimConfirmationRow,
    atomic_write_csv,
    atomic_write_json,
    sha256_file,
)


MODEL_PATH = REPO_ROOT / "docs" / "dwsim-validation" / "jatibarang_facility.dwxmz"
BASE_CASES_PATH = (
    REPO_ROOT / "data" / "jatibarang" / "facility_validation_cases.json"
)
PROJECT_PATH = (
    REPO_ROOT
    / "tools"
    / "dwsim"
    / "FacilityValidationRunner"
    / "FacilityValidationRunner.csproj"
)
RUNNER_PATH = PROJECT_PATH.parent / "bin" / "Release" / "FacilityValidationRunner.exe"


def _density(*, pressure_bar: float, temperature_c: float) -> float:
    return float(
        CP.PropsSI(
            "D",
            "P",
            pressure_bar * 1e5,
            "T",
            temperature_c + 273.15,
            "CO2",
        )
    )


def total_design_mass_flow_kg_s(plan: dict[str, Any]) -> float:
    equipment = (
        plan.get("facility", {}).get("equipment", [])
        if isinstance(plan.get("facility"), dict)
        else []
    )
    facility_values = [
        float(item.get("specifications", {}).get("combined_peak_mass_flow_kg_s"))
        for item in equipment
        if item.get("equipment_type") == "injection_pump"
        and item.get("specifications", {}).get(
            "combined_peak_mass_flow_kg_s"
        )
        is not None
    ]
    if len(facility_values) != 1 or facility_values[0] <= 0:
        raise ValueError(
            f"plan {plan.get('plan_id', '<unknown>')} lacks one positive "
            "facility combined-peak mass-flow result"
        )
    facility_total = facility_values[0]
    fixed = json.loads(
        BASE_CASES_PATH.read_text(encoding="utf-8")
    )["fixed"]
    fresh_density = _density(
        pressure_bar=float(fixed["injection_reference_pressure_bar"]),
        temperature_c=float(fixed["injection_reference_temperature_c"]),
    )
    produced_density = _density(
        pressure_bar=float(fixed["produced_gas_reference_pressure_bar"]),
        temperature_c=float(fixed["produced_gas_reference_temperature_c"]),
    )
    fresh = (
        float(plan["schedule"]["injection_rate_m3_day"])
        * fresh_density
        / 86_400.0
    )
    recycled = (
        float(
            plan["prediction_summary"][
                "peak_produced_gas_std_m3_day"
            ]
        )
        * float(plan["produced_co2_mole_fraction"])
        * produced_density
        / 86_400.0
        * float(fixed["recycle_recovery_fraction"])
    )
    recomputed = fresh + recycled
    relative_error = abs(facility_total - recomputed) / max(
        facility_total,
        recomputed,
        1e-12,
    )
    if relative_error > 1e-6:
        raise ValueError(
            f"plan {plan.get('plan_id', '<unknown>')} facility mass flow "
            "does not match the locked Feature 003 case basis"
        )
    return facility_total


def select_throughput_cases(
    plans: list[dict[str, Any]],
) -> list[tuple[str, dict[str, Any], float]]:
    if len(plans) != 5:
        raise ValueError("DWSIM confirmation requires five shortlist plans")
    ranked = sorted(
        (
            total_design_mass_flow_kg_s(plan),
            str(plan["plan_id"]),
            plan,
        )
        for plan in plans
    )
    return [
        ("minimum", ranked[0][2], ranked[0][0]),
        ("median", ranked[2][2], ranked[2][0]),
        ("maximum", ranked[4][2], ranked[4][0]),
    ]


def build_dwsim_case_document(
    selected: list[tuple[str, dict[str, Any], float]],
) -> dict[str, Any]:
    basis = json.loads(BASE_CASES_PATH.read_text(encoding="utf-8"))
    cases = []
    for throughput_class, plan, total_mass in selected:
        cases.append(
            {
                "case_id": str(plan["plan_id"]),
                "injection_rate_std_m3_day": float(
                    plan["schedule"]["injection_rate_m3_day"]
                ),
                "delivery_pressure_bar": float(
                    plan["delivery_pressure_bar"]
                ),
                "peak_produced_gas_std_m3_day": float(
                    plan["prediction_summary"][
                        "peak_produced_gas_std_m3_day"
                    ]
                ),
                "produced_co2_mole_fraction": float(
                    plan["produced_co2_mole_fraction"]
                ),
                "throughput_class": throughput_class,
                "total_design_mass_flow_kg_s": total_mass,
            }
        )
    return {
        "schema_version": "feature007-dwsim-cases-v1",
        "expected_case_count": len(cases),
        "fixed": basis["fixed"],
        "cases": cases,
        "provenance": {
            "fixed_basis": str(BASE_CASES_PATH.relative_to(REPO_ROOT)),
            "fixed_basis_sha256": sha256_file(BASE_CASES_PATH),
            "selection": "minimum_median_maximum_total_facility_inlet_mass_flow",
        },
    }


def _find_msbuild() -> Path:
    configured = os.environ.get("MSBUILD_EXE_PATH")
    candidates = [
        Path(configured) if configured else None,
        Path(
            "C:/Program Files/Microsoft Visual Studio/2022/"
            "Community/MSBuild/Current/Bin/MSBuild.exe"
        ),
        Path(
            "C:/Program Files/Microsoft Visual Studio/2022/"
            "BuildTools/MSBuild/Current/Bin/MSBuild.exe"
        ),
        Path(
            os.environ.get("WINDIR", "C:/Windows")
        )
        / "Microsoft.NET"
        / "Framework64"
        / "v4.0.30319"
        / "MSBuild.exe",
    ]
    discovered = shutil.which("msbuild")
    if discovered:
        candidates.insert(0, Path(discovered))
    for candidate in candidates:
        if candidate is not None and candidate.exists():
            return candidate
    raise FileNotFoundError(
        "MSBuild was not found; set MSBUILD_EXE_PATH for the .NET 4.7.2 runner"
    )


def build_runner() -> Path:
    msbuild = _find_msbuild()
    completed = subprocess.run(
        [
            str(msbuild),
            str(PROJECT_PATH),
            "/p:Configuration=Release",
            "/nologo",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "DWSIM runner build failed:\n"
            + completed.stdout
            + "\n"
            + completed.stderr
        )
    if not RUNNER_PATH.exists():
        raise FileNotFoundError(RUNNER_PATH)
    return RUNNER_PATH


def _run_cases(cases: Path, output: Path) -> None:
    completed = subprocess.run(
        [
            str(RUNNER_PATH),
            "--model",
            str(MODEL_PATH),
            "--cases",
            str(cases),
            "--output",
            str(output),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "DWSIM automation failed:\n"
            + completed.stdout
            + "\n"
            + completed.stderr
        )


def run_dwsim_confirmation(
    *,
    workspace: Path = DEFAULT_WORKSPACE,
) -> list[DwsimConfirmationRow]:
    plans_path = workspace / "top5_plans.json"
    if not plans_path.exists():
        raise FileNotFoundError(plans_path)
    plans = json.loads(plans_path.read_text(encoding="utf-8"))
    selected = select_throughput_cases(plans)
    document = build_dwsim_case_document(selected)
    cases_path = workspace / "dwsim_top3_cases.json"
    smoke_path = workspace / "dwsim_smoke_case.json"
    atomic_write_json(cases_path, document)
    atomic_write_json(
        smoke_path,
        {
            **document,
            "expected_case_count": 1,
            "cases": document["cases"][:1],
        },
    )
    build_runner()
    _run_cases(smoke_path, workspace / "dwsim_smoke.csv")
    output_path = workspace / "dwsim_top3_raw.csv"
    _run_cases(cases_path, output_path)

    selected_by_id = {
        str(plan["plan_id"]): (throughput_class, total_mass)
        for throughput_class, plan, total_mass in selected
    }
    with output_path.open(encoding="utf-8", newline="") as handle:
        raw_rows = list(csv.DictReader(handle))
    if len(raw_rows) != 3:
        raise ValueError(f"DWSIM returned {len(raw_rows)}/3 confirmation rows")
    model_sha = sha256_file(MODEL_PATH)
    cases_sha = sha256_file(cases_path)
    rows = []
    for raw in raw_rows:
        throughput_class, total_mass = selected_by_id[raw["case_id"]]
        row = DwsimConfirmationRow(
            plan_id=raw["case_id"],
            throughput_class=throughput_class,
            total_design_mass_flow_kg_s=total_mass,
            case_id=raw["case_id"],
            converged=str(raw["converged"]).lower() == "true",
            dwsim_version=raw["dwsim_version"],
            model_sha256=raw["model_sha256"].upper(),
            cases_sha256=raw["cases_sha256"].upper(),
            property_package=raw["property_package"],
            compressor_power_kw=float(raw["compressor_power_kw"]),
            pump_power_kw=float(raw["pump_power_kw"]),
            total_power_kw=float(raw["total_power_kw"]),
            cooling_duty_kw=float(raw["cooling_duty_kw"]),
            separator_gas_std_m3_day=float(
                raw["separator_gas_std_m3_day"]
            ),
            inlet_mass_kg_s=float(raw["inlet_mass_kg_s"]),
            outlet_mass_kg_s=float(raw["outlet_mass_kg_s"]),
            mass_balance_residual_fraction=float(
                raw["mass_balance_residual_fraction"]
            ),
            error_message=raw.get("error_message", ""),
            source_class="dwsim_truth",
        )
        if not row.converged:
            raise ValueError(f"DWSIM case did not converge: {row.plan_id}")
        if row.model_sha256 != model_sha:
            raise ValueError(f"DWSIM model hash mismatch: {row.plan_id}")
        if row.cases_sha256 != cases_sha:
            raise ValueError(f"DWSIM cases hash mismatch: {row.plan_id}")
        if row.property_package != "CoolProp":
            raise ValueError(f"unexpected DWSIM property package: {row.plan_id}")
        rows.append(row)
    atomic_write_csv(
        workspace / "dwsim_topk.csv",
        rows,
        model=DwsimConfirmationRow,
    )
    atomic_write_json(
        workspace / "dwsim_confirmation.json",
        {
            "schema_version": "feature007-dwsim-confirmation-v1",
            "status": "complete",
            "expected_case_count": 3,
            "model_sha256": model_sha,
            "rows": [row.model_dump(mode="json") for row in rows],
        },
    )
    return rows
