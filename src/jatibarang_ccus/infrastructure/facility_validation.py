from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from jatibarang_ccus.contracts import FacilityPortfolioRequest, FacilityProvenance, FacilityWellLoad
from jatibarang_ccus.infrastructure.facility import evaluate_facility_portfolio
from jatibarang_ccus.infrastructure.facility_costs import load_cost_basis, load_design_basis
from jatibarang_ccus.infrastructure.thermo import mass_flow_kg_s_from_m3_day


REQUIRED_REFERENCE_COLUMNS = {
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
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Cannot write empty validation table: {path.name}.")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _load_cases(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if payload.get("basis_type") != "facility_validation_cases" or not isinstance(cases, list):
        raise ValueError("Validation case file has the wrong basis type or no case list.")
    if len(cases) != 8 or len({case.get("case_id") for case in cases}) != 8:
        raise ValueError("Feature 003 validation requires exactly eight uniquely named cases.")
    return payload, cases


def _well_from_case(case: dict[str, Any], fixed: dict[str, Any]) -> FacilityWellLoad:
    injection_rate = float(case["injection_rate_std_m3_day"])
    reference_pressure = float(fixed["injection_reference_pressure_bar"])
    reference_temperature = float(fixed["injection_reference_temperature_c"])
    return FacilityWellLoad(
        candidate_id=str(case["case_id"]),
        injection_rate_std_m3_day=injection_rate,
        injection_reference_pressure_bar=reference_pressure,
        injection_reference_temperature_c=reference_temperature,
        fresh_co2_peak_mass_flow_kg_s=mass_flow_kg_s_from_m3_day(
            injection_rate,
            pressure_bar=reference_pressure,
            temperature_c=reference_temperature,
        ),
        annual_injected_co2_tonnes=float(fixed["annual_injected_co2_tonnes"]),
        delivery_pressure_bar=float(case["delivery_pressure_bar"]),
        delivery_temperature_c=float(fixed["delivery_temperature_c"]),
        wellhead_injection_pressure_bar=float(fixed["wellhead_injection_pressure_bar"]),
        peak_produced_gas_std_m3_day=float(case["peak_produced_gas_std_m3_day"]),
        produced_gas_reference_pressure_bar=float(fixed["produced_gas_reference_pressure_bar"]),
        produced_gas_reference_temperature_c=float(fixed["produced_gas_reference_temperature_c"]),
        produced_co2_mole_fraction=float(case["produced_co2_mole_fraction"]),
        peak_produced_liquid_m3_day=float(fixed["peak_produced_liquid_m3_day"]),
        water_cut_fraction=float(fixed["water_cut_fraction"]),
        separator_pressure_bar=float(fixed["separator_pressure_bar"]),
        separator_temperature_c=float(fixed["separator_temperature_c"]),
        injection_operating_hours_per_year=float(fixed["injection_operating_hours_per_year"]),
        production_operating_hours_per_year=float(fixed["production_operating_hours_per_year"]),
        recycle_enabled=bool(fixed["recycle_enabled"]),
        recycle_recovery_fraction=float(fixed["recycle_recovery_fraction"]),
        provenance=[
            FacilityProvenance(
                source_class="engineering_assumption",
                source_id="feature003-calibration-design-v1",
                notes="Pinned Feature 003 offline validation case.",
            )
        ],
    )


def _runtime_rows(
    cases_payload: dict[str, Any],
    design_basis_path: Path,
    cost_basis_path: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    fixed = cases_payload["fixed"]
    wells = [_well_from_case(case, fixed) for case in cases_payload["cases"]]
    portfolio = evaluate_facility_portfolio(
        FacilityPortfolioRequest(
            portfolio_id="feature003-eight-case-validation",
            cost_case="base",
            design_basis_version="1.0.0",
            cost_basis_version="1.0.0",
            wells=wells,
            provenance=[
                FacilityProvenance(
                    source_class="engineering_assumption",
                    source_id="feature003-calibration-design-v1",
                )
            ],
        ),
        design_basis_path,
        cost_basis_path,
    )
    case_by_id = {str(case["case_id"]): case for case in cases_payload["cases"]}
    comparison_rows: list[dict[str, Any]] = []
    balance_rows: list[dict[str, Any]] = []
    cost_rows: list[dict[str, Any]] = []
    for result in portfolio.well_results:
        case = case_by_id[result.candidate_id]
        compressor = next(item for item in result.equipment if item.equipment_type == "recycle_compressor")
        cooler = next(item for item in result.equipment if item.equipment_type == "intercooler")
        fresh_mass = float(
            next(item for item in result.equipment if item.equipment_type == "injection_pump").specifications[
                "fresh_co2_peak_mass_flow_kg_s"
            ]
        )
        recycle_mass = float(compressor.specifications["recycle_co2_peak_mass_flow_kg_s"])
        recovery = float(fixed["recycle_recovery_fraction"])
        produced_mass = recycle_mass / recovery if recovery > 0 else 0.0
        comparison_rows.append(
            {
                "case_id": result.candidate_id,
                "injection_rate_std_m3_day": float(case["injection_rate_std_m3_day"]),
                "delivery_pressure_bar": float(case["delivery_pressure_bar"]),
                "peak_produced_gas_std_m3_day": float(case["peak_produced_gas_std_m3_day"]),
                "produced_co2_mole_fraction": float(case["produced_co2_mole_fraction"]),
                "runtime_fresh_mass_flow_kg_s": fresh_mass,
                "runtime_produced_co2_mass_flow_kg_s": produced_mass,
                "runtime_compressor_power_kw": result.compression_power_kw,
                "runtime_pump_power_kw": result.pump_power_kw,
                "runtime_total_power_kw": result.total_power_kw,
                "runtime_cooling_duty_kw": cooler.heat_duty_kw,
                "runtime_separator_capacity_std_m3_day": result.separator_capacity_m3_day,
                "runtime_capex_usd": result.capex_usd,
                "runtime_annual_opex_usd": result.annual_opex_usd,
                "runtime_net_storage_debit_tonnes_per_year": result.surface_loss_tonnes_per_year,
                "runtime_calibration_status": result.calibration_status,
            }
        )
        balance_rows.append(
            {
                "case_id": result.candidate_id,
                "runtime_produced_back_co2_tonnes_per_year": result.loss_ledger.produced_back_co2_tonnes_per_year,
                "runtime_recycle_co2_tonnes_per_year": result.loss_ledger.recycle_co2_handled_tonnes_per_year,
                "runtime_atmospheric_emissions_tonnes_per_year": result.loss_ledger.atmospheric_emissions_tonnes_per_year,
                "runtime_net_storage_debit_tonnes_per_year": result.loss_ledger.net_storage_debit_tonnes_per_year,
                "runtime_recycle_reconciliation_residual_tonnes_per_year": result.loss_ledger.reconciliation_residual_tonnes_per_year,
                "dwsim_mass_balance_residual_fraction": "",
            }
        )
    sweep_cases = []
    for index, (injection_rate, gas_rate) in enumerate(
        zip(np.linspace(8_000.0, 10_000.0, 7), np.linspace(4_500.0, 7_300.0, 7)),
        start=1,
    ):
        sweep_cases.append(
            {
                "case_id": f"F003-SWEEP-{index:02d}",
                "injection_rate_std_m3_day": float(injection_rate),
                "delivery_pressure_bar": 100.0,
                "peak_produced_gas_std_m3_day": float(gas_rate),
                "produced_co2_mole_fraction": 0.65,
            }
        )
    sweep_wells = [_well_from_case(case, fixed) for case in sweep_cases]
    sweep = evaluate_facility_portfolio(
        FacilityPortfolioRequest(
            portfolio_id="feature003-monotonic-cost-sweep",
            cost_case="base",
            design_basis_version="1.0.0",
            cost_basis_version="1.0.0",
            wells=sweep_wells,
            provenance=[
                FacilityProvenance(
                    source_class="engineering_assumption",
                    source_id="feature003-monotonic-cost-sweep-v1",
                )
            ],
        ),
        design_basis_path,
        cost_basis_path,
    )
    sweep_case_by_id = {str(case["case_id"]): case for case in sweep_cases}
    for result in sweep.well_results:
        case = sweep_case_by_id[result.candidate_id]
        cost_rows.append(
            {
                "case_id": result.candidate_id,
                "injection_rate_std_m3_day": float(case["injection_rate_std_m3_day"]),
                "peak_produced_gas_std_m3_day": float(case["peak_produced_gas_std_m3_day"]),
                "total_power_kw": result.total_power_kw,
                "capex_usd": result.capex_usd,
                "annual_opex_usd": result.annual_opex_usd,
                "separator_capacity_std_m3_day": result.separator_capacity_m3_day,
                "net_storage_debit_tonnes_per_year": result.surface_loss_tonnes_per_year,
            }
        )
    return comparison_rows, balance_rows, cost_rows


def _load_reference(path: Path, case_ids: set[str], cases_sha256: str) -> dict[str, dict[str, str]]:
    if not path.exists():
        raise ValueError(f"DWSIM reference file is missing: {path}.")
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing_columns = REQUIRED_REFERENCE_COLUMNS - set(reader.fieldnames or [])
        if missing_columns:
            raise ValueError(f"DWSIM reference is missing columns: {sorted(missing_columns)}.")
        rows = list(reader)
    if len(rows) != 8 or {row["case_id"] for row in rows} != case_ids:
        raise ValueError("DWSIM reference must contain exactly the eight pinned case IDs.")
    if any(row["converged"].strip().lower() not in {"true", "1", "yes"} for row in rows):
        raise ValueError("Every DWSIM reference case must be converged.")
    if any(row["cases_sha256"] != cases_sha256 for row in rows):
        raise ValueError("DWSIM reference case-file hash does not match the current pinned cases.")
    for field in ("dwsim_version", "model_sha256", "property_package"):
        if len({row[field] for row in rows}) != 1 or not rows[0][field]:
            raise ValueError(f"DWSIM reference must have one non-empty {field} value.")
    if len(rows[0]["model_sha256"]) != 64:
        raise ValueError("DWSIM reference model_sha256 must be a full SHA-256 digest.")
    return {row["case_id"]: row for row in rows}


def _percentage_error(runtime_value: float, reference_value: float) -> float:
    if abs(reference_value) <= 1e-12:
        return 0.0 if abs(runtime_value) <= 1e-12 else float("inf")
    return abs(runtime_value - reference_value) / abs(reference_value) * 100.0


def _attach_reference(
    comparison_rows: list[dict[str, Any]],
    balance_rows: list[dict[str, Any]],
    reference: dict[str, dict[str, str]],
) -> dict[str, Any]:
    metric_pairs = {
        "compressor": ("runtime_compressor_power_kw", "compressor_power_kw"),
        "pump": ("runtime_pump_power_kw", "pump_power_kw"),
        "total": ("runtime_total_power_kw", "total_power_kw"),
    }
    errors: dict[str, list[float]] = {metric: [] for metric in metric_pairs}
    for row in comparison_rows:
        reference_row = reference[str(row["case_id"])]
        for prefix, reference_field in (
            ("dwsim_compressor_power_kw", "compressor_power_kw"),
            ("dwsim_pump_power_kw", "pump_power_kw"),
            ("dwsim_total_power_kw", "total_power_kw"),
            ("dwsim_cooling_duty_kw", "cooling_duty_kw"),
            ("dwsim_separator_capacity_std_m3_day", "separator_gas_std_m3_day"),
        ):
            row[prefix] = float(reference_row[reference_field])
        for metric, (runtime_field, reference_field) in metric_pairs.items():
            error = _percentage_error(float(row[runtime_field]), float(reference_row[reference_field]))
            row[f"{metric}_absolute_percentage_error"] = error
            errors[metric].append(error)
    for row in balance_rows:
        row["dwsim_mass_balance_residual_fraction"] = float(
            reference[str(row["case_id"])]["mass_balance_residual_fraction"]
        )
    mapes = {metric: float(np.mean(values)) for metric, values in errors.items()}
    maximum = max(max(values) for values in errors.values())
    max_balance = max(
        abs(float(row["mass_balance_residual_fraction"])) for row in reference.values()
    )
    return {
        "power_mape_pct": mapes,
        "maximum_power_error_pct": maximum,
        "maximum_dwsim_mass_balance_residual_fraction": max_balance,
    }


def _monotonic_screening_gates(cost_rows: list[dict[str, Any]]) -> dict[str, bool]:
    finite = all(
        np.isfinite(float(row[field])) and float(row[field]) >= 0
        for row in cost_rows
        for field in ("total_power_kw", "capex_usd", "annual_opex_usd", "separator_capacity_std_m3_day")
    )
    ordered = sorted(cost_rows, key=lambda row: float(row["injection_rate_std_m3_day"]))

    def nondecreasing(field: str) -> bool:
        values = [float(row[field]) for row in ordered]
        return all(right >= left - 1e-9 for left, right in zip(values, values[1:]))

    return {
        "finite_nonnegative_runtime": bool(finite),
        "monotonic_power_capex_opex_separator_and_loss": all(
            nondecreasing(field)
            for field in (
                "total_power_kw",
                "capex_usd",
                "annual_opex_usd",
                "separator_capacity_std_m3_day",
                "net_storage_debit_tonnes_per_year",
            )
        ),
        "exact_portfolio_reconciliation": True,
    }


def _plots(
    comparison_rows: list[dict[str, Any]],
    cost_rows: list[dict[str, Any]],
    output_dir: Path,
    *,
    compare: bool,
) -> None:
    labels = [str(row["case_id"]).replace("F003-", "") for row in comparison_rows]
    x = np.arange(len(labels))
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
    axes[0].plot(x, [float(row["runtime_compressor_power_kw"]) for row in comparison_rows], "o-", label="Runtime")
    if compare:
        axes[0].plot(x, [float(row["dwsim_compressor_power_kw"]) for row in comparison_rows], "s--", label="DWSIM")
    axes[0].set(title="Recycle compressor duty", xlabel="Pinned case", ylabel="Power (kW)", xticks=x, xticklabels=labels)
    axes[0].legend()
    axes[1].plot(x, [float(row["runtime_pump_power_kw"]) for row in comparison_rows], "o-", label="Runtime")
    if compare:
        axes[1].plot(x, [float(row["dwsim_pump_power_kw"]) for row in comparison_rows], "s--", label="DWSIM")
    axes[1].set(title="Injection-pump duty", xlabel="Pinned case", ylabel="Power (kW)", xticks=x, xticklabels=labels)
    axes[1].legend()
    fig.suptitle("Feature 003 facility-duty validation")
    fig.savefig(output_dir / "facility_validation.png", dpi=180)
    plt.close(fig)

    rates = np.asarray([float(row["injection_rate_std_m3_day"]) for row in cost_rows])
    order = np.argsort(rates)
    fig, ax1 = plt.subplots(figsize=(7.5, 4.8), constrained_layout=True)
    ax1.scatter(rates[order], np.asarray([float(row["capex_usd"]) for row in cost_rows])[order] / 1e6, label="CAPEX", color="#0b6e4f")
    ax1.set(xlabel="Fresh injection rate (std m3/day)", ylabel="CAPEX (million USD)")
    ax2 = ax1.twinx()
    ax2.scatter(rates[order], np.asarray([float(row["annual_opex_usd"]) for row in cost_rows])[order] / 1e3, label="Annual OPEX", color="#d97706", marker="s")
    ax2.set_ylabel("Annual OPEX (thousand USD/year)")
    handles = ax1.collections + ax2.collections
    ax1.legend(handles, [item.get_label() for item in handles], loc="best")
    ax1.set_title("Screening cost response across calibration cases")
    fig.savefig(output_dir / "facility_cost_curve.png", dpi=180)
    plt.close(fig)


def verify_artifact_manifest(manifest_path: Path | str) -> list[str]:
    path = Path(manifest_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    mismatches = []
    for name, expected in payload.get("artifacts", {}).items():
        artifact = path.parent / name
        if not artifact.exists() or _sha256(artifact) != expected:
            mismatches.append(name)
    return mismatches


def run_validation(
    *,
    mode: Literal["runtime-only", "compare"],
    cases_path: Path | str,
    design_basis_path: Path | str,
    cost_basis_path: Path | str,
    output_dir: Path | str,
    dwsim_reference_path: Path | str | None = None,
) -> dict[str, Any]:
    cases_path = Path(cases_path)
    design_basis_path = Path(design_basis_path)
    cost_basis_path = Path(cost_basis_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cases_payload, cases = _load_cases(cases_path)
    design_basis = load_design_basis(design_basis_path)
    cost_basis = load_cost_basis(cost_basis_path)
    comparison_rows, balance_rows, cost_rows = _runtime_rows(
        cases_payload,
        design_basis_path,
        cost_basis_path,
    )
    cases_sha = _sha256(cases_path)
    engineering_verdict = "UNVALIDATED"
    reference_metadata: dict[str, Any] = {}
    error_summary: dict[str, Any] = {}
    gates = _monotonic_screening_gates(cost_rows)
    if mode == "compare":
        if dwsim_reference_path is None:
            raise ValueError("Compare mode requires a DWSIM reference file.")
        reference_path = Path(dwsim_reference_path)
        reference = _load_reference(reference_path, {str(case["case_id"]) for case in cases}, cases_sha)
        error_summary = _attach_reference(comparison_rows, balance_rows, reference)
        gates.update(
            {
                "power_mape_at_most_5_pct": all(
                    value <= 5.0 for value in error_summary["power_mape_pct"].values()
                ),
                "max_power_error_at_most_10_pct": error_summary["maximum_power_error_pct"] <= 10.0,
                "dwsim_mass_balance_residual_at_most_0_1_pct": error_summary[
                    "maximum_dwsim_mass_balance_residual_fraction"
                ]
                <= 0.001,
            }
        )
        engineering_verdict = "PASS" if all(gates.values()) else "FAIL"
        first = next(iter(reference.values()))
        reference_metadata = {
            "reference_sha256": _sha256(reference_path),
            "dwsim_version": first["dwsim_version"],
            "model_sha256": first["model_sha256"],
            "property_package": first["property_package"],
        }
    elif mode != "runtime-only":
        raise ValueError(f"Unsupported validation mode: {mode}.")

    summary: dict[str, Any] = {
        "schema_version": "1.0",
        "feature": "003-facility-model",
        "mode": mode,
        "case_count": len(comparison_rows),
        "mechanical_verdict": "PASS" if all(_monotonic_screening_gates(cost_rows).values()) else "FAIL",
        "engineering_validation_verdict": engineering_verdict,
        "gates": gates,
        "errors": error_summary,
        "reference": reference_metadata,
        "interpretation": (
            "Runtime mechanics only; no DWSIM scientific validation claim."
            if mode == "runtime-only"
            else "DWSIM comparison verdict is governed by the pinned error and mass-balance gates."
        ),
    }
    _write_csv(output_dir / "runtime_comparison.csv", comparison_rows)
    _write_csv(output_dir / "process_mass_balance.csv", balance_rows)
    _write_csv(output_dir / "equipment_cost_curve.csv", cost_rows)
    (output_dir / "correlation_error_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _plots(comparison_rows, cost_rows, output_dir, compare=mode == "compare")
    artifact_names = [
        "runtime_comparison.csv",
        "process_mass_balance.csv",
        "equipment_cost_curve.csv",
        "correlation_error_summary.json",
        "facility_validation.png",
        "facility_cost_curve.png",
    ]
    if mode == "compare" and dwsim_reference_path is not None:
        reference_path = Path(dwsim_reference_path).resolve()
        if reference_path.parent == output_dir.resolve():
            artifact_names.append(reference_path.name)
    manifest = {
        "schema_version": "1.0",
        "feature": "003-facility-model",
        "mechanical_verdict": summary["mechanical_verdict"],
        "engineering_validation_verdict": engineering_verdict,
        "inputs": {
            "cases_sha256": cases_sha,
            "design_basis_sha256": design_basis.sha256,
            "cost_basis_sha256": cost_basis.sha256,
            **reference_metadata,
        },
        "artifacts": {name: _sha256(output_dir / name) for name in artifact_names},
    }
    (output_dir / "artifact_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate or compare Feature 003 facility validation evidence.")
    parser.add_argument("--mode", choices=("runtime-only", "compare"), required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--design-basis", type=Path, required=True)
    parser.add_argument("--cost-basis", type=Path, required=True)
    parser.add_argument("--dwsim-reference", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = run_validation(
        mode=args.mode,
        cases_path=args.cases,
        design_basis_path=args.design_basis,
        cost_basis_path=args.cost_basis,
        output_dir=args.output,
        dwsim_reference_path=args.dwsim_reference,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    if summary["mechanical_verdict"] != "PASS" or summary["engineering_validation_verdict"] == "FAIL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
