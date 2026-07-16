from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from jatibarang_ccus.phase1.case_study import DEFAULT_ASSUMPTIONS, load_assumptions, run_screening
from jatibarang_ccus.phase1.ledger import LedgerEntry, entry, utc_now_iso
from jatibarang_ccus.phase1.metrics import geology_span, mrst_mean_runtime_seconds, surrogate_metric_summary
from jatibarang_ccus.surrogate.config import REPO_ROOT, UPSTREAM_FINAL_MANIFEST, UPSTREAM_METRICS
from jatibarang_ccus.surrogate.runner import verify_checkpoint


ABSTRACT_KEYS = [
    "geological_realization_count",
    "porosity_min",
    "porosity_max",
    "matrix_permeability_min_md",
    "matrix_permeability_max_md",
    "one_step_pressure_r2",
    "one_step_gas_plume_iou",
    "cumulative_production_error_pct",
    "end_sequence_co2_mass_error_pct",
    "integrated_scenario_count",
    "screening_runtime_minutes",
    "equivalent_compositional_coverage_weeks",
    "current_carbon_price_npv_usd",
    "jcm_bilateral_price_npv_usd",
    "changed_priority_candidate_count",
    "total_candidate_count",
    "break_even_carbon_price_usd_per_tonne",
]


def _rounded(value: float, digits: int) -> float:
    return round(float(value), digits)


def _format_money(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.2f} million"
    return f"${value:,.0f}"


def _entries_by_key(entries: list[LedgerEntry]) -> dict[str, LedgerEntry]:
    return {item.key: item for item in entries}


def _filled_excerpt(entries: list[LedgerEntry]) -> str:
    values = _entries_by_key(entries)
    return (
        "Applied to a Jatibarang-anchored case study with "
        f"{values['geological_realization_count'].value} geological realizations spanning porosity "
        f"{values['porosity_min'].value} to {values['porosity_max'].value} and matrix permeability "
        f"{values['matrix_permeability_min_md'].value} to {values['matrix_permeability_max_md'].value} mD, "
        f"the surrogate achieves one-step pressure R2 of {values['one_step_pressure_r2'].value}, "
        f"gas plume IoU of {values['one_step_gas_plume_iou'].value}, and cumulative production error below "
        f"{values['cumulative_production_error_pct'].value}%, with end-of-sequence CO2 mass error of "
        f"{values['end_sequence_co2_mass_error_pct'].value}%. The framework screens "
        f"{values['integrated_scenario_count'].value} integrated scenarios in "
        f"{values['screening_runtime_minutes'].value} minutes versus "
        f"{values['equivalent_compositional_coverage_weeks'].value} weeks for equivalent compositional coverage. "
        f"Under current carbon pricing the optimal plan yields NPV of "
        f"{_format_money(float(values['current_carbon_price_npv_usd'].value))}; under JCM bilateral pricing NPV rises to "
        f"{_format_money(float(values['jcm_bilateral_price_npv_usd'].value))} and well selection shifts, with "
        f"{values['changed_priority_candidate_count'].value} of {values['total_candidate_count'].value} candidates "
        f"changing priority. The break-even carbon price is "
        f"${values['break_even_carbon_price_usd_per_tonne'].value} per tonne. "
        "These results demonstrate that surrogate-enabled integrated screening materially improves CO2 HnP-CCUS "
        "planning and that Indonesian carbon pricing, even at nascent levels, alters which development strategies "
        "are optimal."
    )


def _write_outputs(entries: list[LedgerEntry], screening: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "abstract_number_keys": ABSTRACT_KEYS,
        "entries": [item.to_dict() for item in entries],
        "screening_summary": screening,
        "filled_excerpt": _filled_excerpt(entries),
    }

    json_path = output_dir / "abstract_numbers.json"
    csv_path = output_dir / "abstract_numbers.csv"
    md_path = output_dir / "abstract_numbers.md"

    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["key", "value", "units", "source", "method", "timestamp"])
        writer.writeheader()
        for item in entries:
            writer.writerow(item.to_dict())

    lines = [
        "# Abstract Numbers",
        "",
        "| Key | Value | Units | Source | Method |",
        "|---|---:|---|---|---|",
    ]
    for item in entries:
        lines.append(f"| `{item.key}` | {item.value} | {item.units} | {item.source} | {item.method} |")
    lines.extend(["", "## Filled Excerpt", "", payload["filled_excerpt"], ""])
    md_path.write_text("\n".join(lines), encoding="utf-8")

    return {"json": str(json_path), "csv": str(csv_path), "markdown": str(md_path)}


def validate_entries(entries: list[LedgerEntry]) -> None:
    by_key = _entries_by_key(entries)
    missing = [key for key in ABSTRACT_KEYS if key not in by_key]
    if missing:
        raise ValueError(f"Missing abstract-number entries: {missing}")
    for key in ABSTRACT_KEYS:
        item = by_key[key]
        if item.value is None or item.value == "":
            raise ValueError(f"Abstract number {key} has no value.")
        if not item.units:
            raise ValueError(f"Abstract number {key} has no units.")
        if not item.source:
            raise ValueError(f"Abstract number {key} has no source.")
        if not item.method:
            raise ValueError(f"Abstract number {key} has no method.")


def generate_abstract_numbers(
    *,
    assumptions_path: Path = DEFAULT_ASSUMPTIONS,
    output_dir: Path = REPO_ROOT / "paper" / "tables",
) -> dict[str, Any]:
    timestamp = utc_now_iso()
    verify_checkpoint()
    assumptions = load_assumptions(assumptions_path)
    geology = geology_span(assumptions)
    surrogate = surrogate_metric_summary()
    mrst_runtime = mrst_mean_runtime_seconds()
    screening = run_screening(
        assumptions,
        mrst_mean_seconds=mrst_runtime,
        surrogate_uncertainty={
            "production_error_pct": float(surrogate["cumulative_production_error_pct"]),
            "co2_mass_error_pct": float(surrogate["end_sequence_co2_mass_error_pct"]),
        },
    )

    entries = [
        entry(
            "geological_realization_count",
            int(geology["geological_realization_count"]),
            "count",
            "boreyes2026 promoted split + final manifest",
            "Count accepted train/validation/test realizations used by the promoted checkpoint.",
            timestamp,
        ),
        entry(
            "porosity_min",
            _rounded(float(geology["porosity_min"]), 3),
            "fraction",
            "boreyes2026 final manifest",
            "Minimum poro_mean across accepted promoted-split realizations.",
            timestamp,
        ),
        entry(
            "porosity_max",
            _rounded(float(geology["porosity_max"]), 3),
            "fraction",
            "boreyes2026 final manifest",
            "Maximum poro_mean across accepted promoted-split realizations.",
            timestamp,
        ),
        entry(
            "matrix_permeability_min_md",
            _rounded(float(geology["matrix_permeability_min_md"]), 1),
            "mD",
            "data/jatibarang/case_study_assumptions.json",
            "Literature-anchored matrix permeability lower bound before fracture multiplier.",
            timestamp,
        ),
        entry(
            "matrix_permeability_max_md",
            _rounded(float(geology["matrix_permeability_max_md"]), 1),
            "mD",
            "data/jatibarang/case_study_assumptions.json",
            "Literature-anchored matrix permeability upper bound before fracture multiplier.",
            timestamp,
        ),
        entry(
            "one_step_pressure_r2",
            _rounded(float(surrogate["one_step_pressure_r2"]), 4),
            "R2",
            str(UPSTREAM_METRICS),
            "Read promoted production_v2 one-step metric and round for abstract reporting.",
            timestamp,
        ),
        entry(
            "one_step_gas_plume_iou",
            _rounded(float(surrogate["one_step_gas_plume_iou"]), 4),
            "IoU",
            str(UPSTREAM_METRICS),
            "Read promoted production_v2 one-step gas saturation plume IoU.",
            timestamp,
        ),
        entry(
            "cumulative_production_error_pct",
            _rounded(float(surrogate["cumulative_production_error_pct"]), 2),
            "percent",
            str(UPSTREAM_METRICS),
            "Use last-rollout cumulative raw oil relative MAE as the abstract production error bound.",
            timestamp,
        ),
        entry(
            "end_sequence_co2_mass_error_pct",
            _rounded(float(surrogate["end_sequence_co2_mass_error_pct"]), 2),
            "percent",
            str(UPSTREAM_METRICS),
            "Use last-rollout z_co2 mass error from the promoted metrics.",
            timestamp,
        ),
        entry(
            "integrated_scenario_count",
            int(screening["scenario_count"]),
            "count",
            "data/jatibarang/case_study_assumptions.json",
            "Candidate count multiplied by operational-grid combinations.",
            timestamp,
        ),
        entry(
            "screening_runtime_minutes",
            max(_rounded(float(screening["screening_runtime_minutes"]), 4), 0.0001),
            "minutes",
            "Phase 1 screening CLI",
            "Measured wall-clock time for A* route build, CoolProp precompute/facility, Pyomo/CBC MILP, and economics.",
            timestamp,
        ),
        entry(
            "equivalent_compositional_coverage_weeks",
            _rounded(float(screening["equivalent_mrst_weeks"]), 2),
            "weeks",
            str(UPSTREAM_FINAL_MANIFEST),
            "Scenario count multiplied by mean MRST manifest runtime; Phase 1 runs only curated validation subset.",
            timestamp,
        ),
        entry(
            "current_carbon_price_npv_usd",
            _rounded(float(screening["by_price"]["current_idx"]["portfolio_npv_usd"]), 2),
            "USD",
            "Phase 1 real infrastructure economics model",
            "Final portfolio NPV using A* routes, CoolProp facility costs, Pyomo/CBC well selection, and delivered costs.",
            timestamp,
        ),
        entry(
            "jcm_bilateral_price_npv_usd",
            _rounded(float(screening["by_price"]["jcm_bilateral"]["portfolio_npv_usd"]), 2),
            "USD",
            "Phase 1 real infrastructure economics model",
            "Final portfolio NPV using A* routes, CoolProp facility costs, Pyomo/CBC well selection, and delivered costs.",
            timestamp,
        ),
        entry(
            "changed_priority_candidate_count",
            int(screening["changed_priority_count"]),
            "count",
            "Phase 1 MILP/economics ranking comparison",
            "Count candidates whose integrated MILP/economics ranking shifts by at least the configured rank-delta threshold.",
            timestamp,
        ),
        entry(
            "total_candidate_count",
            int(screening["candidate_count"]),
            "count",
            "data/jatibarang/case_study_assumptions.json",
            "Candidate well count in the Phase 1 case-study assumptions.",
            timestamp,
        ),
        entry(
            "break_even_carbon_price_usd_per_tonne",
            _rounded(float(screening["break_even_carbon_price_usd_per_tonne"]), 2),
            "USD/tonne CO2",
            "Phase 1 real infrastructure economics model",
            "Carbon price required to bring the current-price Pyomo/CBC-selected portfolio to zero NPV before carbon revenue.",
            timestamp,
        ),
    ]
    validate_entries(entries)
    outputs = _write_outputs(entries, screening, output_dir)
    return {
        "entries": [item.to_dict() for item in entries],
        "screening_summary": screening,
        "outputs": outputs,
        "filled_excerpt": _filled_excerpt(entries),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Phase 1 abstract-number ledger.")
    parser.add_argument("--assumptions", type=Path, default=DEFAULT_ASSUMPTIONS)
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "paper" / "tables")
    args = parser.parse_args()

    result = generate_abstract_numbers(assumptions_path=args.assumptions, output_dir=args.output_dir)
    print(json.dumps(result["outputs"], indent=2))
    print(result["filled_excerpt"])


if __name__ == "__main__":
    main()
