from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from jatibarang_ccus.infrastructure.facility_validation import run_validation, verify_artifact_manifest

from .helpers import COST_BASIS, DESIGN_BASIS, VALIDATION_CASES


def _reference_from_runtime(runtime_csv: Path, reference_csv: Path, *, converged: bool = True) -> None:
    runtime_rows = list(csv.DictReader(runtime_csv.open(encoding="utf-8", newline="")))
    fields = [
        "case_id",
        "converged",
        "dwsim_version",
        "model_sha256",
        "cases_sha256",
        "property_package",
        "compressor_power_kw",
        "pump_power_kw",
        "total_power_kw",
        "cooling_duty_kw",
        "separator_gas_std_m3_day",
        "inlet_mass_kg_s",
        "outlet_mass_kg_s",
        "mass_balance_residual_fraction",
    ]
    cases_sha = json.loads((runtime_csv.parent / "artifact_manifest.json").read_text())["inputs"][
        "cases_sha256"
    ]
    with reference_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for index, row in enumerate(runtime_rows):
            inlet_mass = float(row["runtime_fresh_mass_flow_kg_s"]) + float(
                row["runtime_produced_co2_mass_flow_kg_s"]
            )
            writer.writerow(
                {
                    "case_id": row["case_id"],
                    "converged": str(converged or index > 0).lower(),
                    "dwsim_version": "test-fixture-only",
                    "model_sha256": "1" * 64,
                    "cases_sha256": cases_sha,
                    "property_package": "CoolProp",
                    "compressor_power_kw": row["runtime_compressor_power_kw"],
                    "pump_power_kw": row["runtime_pump_power_kw"],
                    "total_power_kw": row["runtime_total_power_kw"],
                    "cooling_duty_kw": row["runtime_cooling_duty_kw"],
                    "separator_gas_std_m3_day": row["peak_produced_gas_std_m3_day"],
                    "inlet_mass_kg_s": inlet_mass,
                    "outlet_mass_kg_s": inlet_mass,
                    "mass_balance_residual_fraction": 0.0,
                }
            )


def test_runtime_only_bundle_is_complete_hashed_and_unvalidated(tmp_path: Path) -> None:
    summary = run_validation(
        mode="runtime-only",
        cases_path=VALIDATION_CASES,
        design_basis_path=DESIGN_BASIS,
        cost_basis_path=COST_BASIS,
        output_dir=tmp_path,
    )
    assert summary["case_count"] == 8
    assert summary["mechanical_verdict"] == "PASS"
    assert summary["engineering_validation_verdict"] == "UNVALIDATED"
    expected = {
        "runtime_comparison.csv",
        "process_mass_balance.csv",
        "equipment_cost_curve.csv",
        "correlation_error_summary.json",
        "facility_validation.png",
        "facility_cost_curve.png",
        "artifact_manifest.json",
    }
    assert expected <= {item.name for item in tmp_path.iterdir()}
    assert verify_artifact_manifest(tmp_path / "artifact_manifest.json") == []


def test_compare_mode_passes_exact_test_fixture_and_records_separate_verdicts(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    compare_dir = tmp_path / "compare"
    run_validation(
        mode="runtime-only",
        cases_path=VALIDATION_CASES,
        design_basis_path=DESIGN_BASIS,
        cost_basis_path=COST_BASIS,
        output_dir=runtime_dir,
    )
    reference = tmp_path / "test_reference.csv"
    _reference_from_runtime(runtime_dir / "runtime_comparison.csv", reference)
    summary = run_validation(
        mode="compare",
        cases_path=VALIDATION_CASES,
        design_basis_path=DESIGN_BASIS,
        cost_basis_path=COST_BASIS,
        output_dir=compare_dir,
        dwsim_reference_path=reference,
    )
    assert summary["mechanical_verdict"] == "PASS"
    assert summary["engineering_validation_verdict"] == "PASS"
    assert summary["gates"]["power_mape_at_most_5_pct"] is True
    assert summary["gates"]["max_power_error_at_most_10_pct"] is True
    assert verify_artifact_manifest(compare_dir / "artifact_manifest.json") == []


def test_compare_mode_rejects_missing_or_nonconverged_reference(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    run_validation(
        mode="runtime-only",
        cases_path=VALIDATION_CASES,
        design_basis_path=DESIGN_BASIS,
        cost_basis_path=COST_BASIS,
        output_dir=runtime_dir,
    )
    with pytest.raises(ValueError, match="reference"):
        run_validation(
            mode="compare",
            cases_path=VALIDATION_CASES,
            design_basis_path=DESIGN_BASIS,
            cost_basis_path=COST_BASIS,
            output_dir=tmp_path / "missing",
        )

    reference = tmp_path / "nonconverged.csv"
    _reference_from_runtime(runtime_dir / "runtime_comparison.csv", reference, converged=False)
    with pytest.raises(ValueError, match="converged"):
        run_validation(
            mode="compare",
            cases_path=VALIDATION_CASES,
            design_basis_path=DESIGN_BASIS,
            cost_basis_path=COST_BASIS,
            output_dir=tmp_path / "failed",
            dwsim_reference_path=reference,
        )


def test_manifest_verifier_detects_tampering(tmp_path: Path) -> None:
    run_validation(
        mode="runtime-only",
        cases_path=VALIDATION_CASES,
        design_basis_path=DESIGN_BASIS,
        cost_basis_path=COST_BASIS,
        output_dir=tmp_path,
    )
    with (tmp_path / "runtime_comparison.csv").open("a", encoding="utf-8") as handle:
        handle.write("tampered\n")
    assert "runtime_comparison.csv" in verify_artifact_manifest(tmp_path / "artifact_manifest.json")
