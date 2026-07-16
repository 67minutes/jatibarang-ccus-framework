from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from shapely.geometry import shape

from jatibarang_ccus.contracts import (
    PipelineDesignRequest,
    RouteLibraryRequest,
    SupplyComparisonRequest,
)
from jatibarang_ccus.infrastructure.pipeline import (
    adapt_legacy_pipeline_inputs,
    solve_pipeline_design,
)
from jatibarang_ccus.infrastructure.routing import build_route_library, load_exclusion_zones, sha256_file
from jatibarang_ccus.infrastructure.supply import compare_supply_scenarios
from jatibarang_ccus.phase1.case_study import (
    DEFAULT_ASSUMPTIONS,
    _candidate_models,
    _evaluate_candidate,
    _scenario_parameters,
    _source_model,
    load_assumptions,
)


REQUIRED_ARTIFACTS = {
    "artifact_manifest.json",
    "route_library.json",
    "route_map.png",
    "exclusion_audit.json",
    "hydraulic_curve_comparison.csv",
    "hydraulic_curve_comparison.png",
    "continuous_pressure_profiles.csv",
    "continuous_pressure_profiles.png",
    "booster_duties.csv",
    "constraint_table.csv",
    "constraint_audit.json",
    "cost_sensitivity.csv",
    "cost_sensitivity.png",
    "solver_report.json",
    "pipeline_design_base.json",
    "rational_zero_selection.json",
    "selected_rejected_wells.csv",
}


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _plot_routes(output: Path, library, design, exclusion_path: str | Path) -> None:
    built = {item.segment_id for item in design.built_segments}
    fig, ax = plt.subplots(figsize=(10, 5.5))
    zones, _ = load_exclusion_zones(exclusion_path)
    for zone in zones:
        geometry = shape(zone.geometry)
        color = "#C94C4C" if zone.routing_mode == "hard" else "#28A6A6"
        if geometry.geom_type == "Polygon":
            x, y = geometry.exterior.xy
            ax.fill(x, y, color=color, alpha=0.2, label=f"{zone.routing_mode} exclusion")
        elif geometry.geom_type == "LineString":
            x, y = geometry.xy
            ax.plot(x, y, color=color, linewidth=2, alpha=0.7, label=f"{zone.routing_mode} crossing")
    for segment in library.segments:
        ax.plot(
            [item.longitude for item in segment.geometry],
            [item.latitude for item in segment.geometry],
            color="#146C94" if segment.id in built else "#B7C4CF",
            linewidth=2.2 if segment.id in built else 0.5,
            alpha=0.95 if segment.id in built else 0.45,
        )
    node_colors = {"source": "#D97706", "well": "#1B9C85", "junction": "#6366F1"}
    for kind in ("source", "well", "junction"):
        nodes = [item for item in library.nodes if item.kind == kind]
        ax.scatter(
            [item.location.longitude for item in nodes],
            [item.location.latitude for item in nodes],
            s=45 if kind != "junction" else 9,
            color=node_colors[kind],
            label=kind,
            zorder=5,
        )
    handles, labels = ax.get_legend_handles_labels()
    unique = dict(zip(labels, handles))
    ax.legend(unique.values(), unique.keys(), frameon=False, ncol=3, fontsize=8)
    ax.set(title="Feature 002 exclusion-aware candidate network", xlabel="Longitude", ylabel="Latitude")
    ax.grid(alpha=0.15)
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def _pressure_artifacts(output_dir: Path, design) -> None:
    rows: list[dict[str, Any]] = []
    fig, (pressure_ax, velocity_ax) = plt.subplots(2, 1, figsize=(9, 7), sharex=False)
    for segment in design.built_segments:
        for point in segment.continuous_profile:
            rows.append(
                {
                    "segment_id": segment.segment_id,
                    "from_node": segment.from_node,
                    "to_node": segment.to_node,
                    **point.model_dump(),
                }
            )
        distances = [item.distance_km for item in segment.continuous_profile]
        pressure_ax.plot(distances, [item.pressure_bar for item in segment.continuous_profile], label=segment.segment_id)
        velocity_ax.plot(distances, [item.velocity_m_s for item in segment.continuous_profile], label=segment.segment_id)
    _write_csv(
        output_dir / "continuous_pressure_profiles.csv",
        ["segment_id", "from_node", "to_node", "distance_km", "elevation_m", "pressure_bar", "hydraulic_head_bar", "density_kg_m3", "velocity_m_s"],
        rows,
    )
    pressure_ax.axhline(80.0, color="#C94C4C", linestyle="--", linewidth=1, label="dense-phase floor")
    pressure_ax.set(ylabel="Pressure (bar)", title="Continuous local-state verification profiles")
    velocity_ax.axhspan(1.0, 5.0, color="#1B9C85", alpha=0.12, label="allowed velocity")
    velocity_ax.set(xlabel="Distance along segment (km)", ylabel="Velocity (m/s)")
    for axis in (pressure_ax, velocity_ax):
        axis.grid(alpha=0.2)
        axis.legend(frameon=False, fontsize=7, ncol=4)
    fig.tight_layout()
    fig.savefig(output_dir / "continuous_pressure_profiles.png", dpi=180)
    plt.close(fig)


def _hydraulic_curve_artifacts(output_dir: Path, design) -> None:
    rows: list[dict[str, Any]] = []
    for built in design.built_segments:
        rows.append(
            {
                "segment_id": built.segment_id,
                "diameter_in": built.diameter_in,
                "peak_mass_flow_kg_s": built.peak_mass_flow_kg_s,
                "pwl_pressure_drop_bar": built.pwl_pressure_drop_bar,
                "continuous_pressure_drop_bar": built.pressure_drop_bar,
                "absolute_error_bar": built.pwl_error_bar,
                "acceptance_tolerance_bar": built.pwl_tolerance_bar,
                "passed": built.pwl_error_bar <= built.pwl_tolerance_bar,
            }
        )
    _write_csv(
        output_dir / "hydraulic_curve_comparison.csv",
        ["segment_id", "diameter_in", "peak_mass_flow_kg_s", "pwl_pressure_drop_bar", "continuous_pressure_drop_bar", "absolute_error_bar", "acceptance_tolerance_bar", "passed"],
        rows,
    )
    fig, ax = plt.subplots(figsize=(7, 5))
    x = [item["continuous_pressure_drop_bar"] for item in rows]
    y = [item["pwl_pressure_drop_bar"] for item in rows]
    ax.scatter(x, y, color="#146C94")
    limit = max([1.0, *x, *y])
    ax.plot([0, limit], [0, limit], color="#C94C4C", linestyle="--", linewidth=1)
    ax.set(xlabel="Continuous pressure change (bar)", ylabel="PWL pressure change (bar)", title="PWL versus continuous hydraulics")
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(output_dir / "hydraulic_curve_comparison.png", dpi=180)
    plt.close(fig)


def validate_artifact_bundle(output_dir: Path) -> dict[str, Any]:
    missing = sorted(REQUIRED_ARTIFACTS - {item.name for item in output_dir.iterdir() if item.is_file()})
    if missing:
        raise ValueError(f"Feature 002 artifact bundle is incomplete: {missing}")
    manifest = json.loads((output_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
    if manifest["verdict"] != "pass":
        raise ValueError(f"Feature 002 artifact manifest verdict is {manifest['verdict']!r}.")
    design = json.loads((output_dir / "pipeline_design_base.json").read_text(encoding="utf-8"))
    if design["domain_status"] != "accepted" or not design["hydraulic_verification"]["passed"]:
        raise ValueError("Tracked base pipeline result is not accepted and hydraulically verified.")
    return {"passed": True, "artifact_count": len(manifest["artifacts"]), "selected_well_count": len(design["selected_wells"])}


def generate_validation_bundle(assumptions_path: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    assumptions = load_assumptions(assumptions_path)
    source = _source_model(assumptions)
    candidates = _candidate_models(assumptions)
    params = _scenario_parameters(assumptions["screening_grid"])[0]
    values = [
        _evaluate_candidate(candidate, params, assumptions["economics"], float(assumptions["carbon_prices_usd_per_tonne"]["current_idx"]))
        for candidate in candidates
    ]
    sources, demands = adapt_legacy_pipeline_inputs(
        source=source,
        candidates=candidates,
        well_values=values,
        assumptions=assumptions,
    )
    library = build_route_library(
        RouteLibraryRequest(sources=sources, well_demands=demands, routing_assumptions=assumptions["routing"])
    )
    common = {
        "sources": sources,
        "route_library": library,
        "annual_co2_budget_tonnes": float(assumptions["economics"]["co2_budget_tonnes"]),
        "assumptions": assumptions,
        "solver": str(assumptions["pipeline"].get("solver", "cbc")),
    }
    default_request = PipelineDesignRequest(well_demands=demands, objective_mode="max_net_value", cost_case="base", **common)
    rational_zero = solve_pipeline_design(default_request)
    if rational_zero.domain_status != "no_viable_network":
        raise RuntimeError("The default proxy case was expected to preserve a rational audited zero-selection result.")

    mandatory_demands = [item.model_copy(update={"mandatory": item.candidate_id == "W01"}) for item in demands]
    comparisons = {}
    for case in ("low", "base", "high"):
        design_request = PipelineDesignRequest(
            well_demands=mandatory_demands,
            objective_mode="min_lifecycle_cost",
            cost_case=case,
            **common,
        )
        comparisons[case] = compare_supply_scenarios(
            SupplyComparisonRequest(pipeline_request=design_request, trucking_distance_km=70.0)
        )
        _write_json(output_dir / f"supply_comparison_{case}.json", comparisons[case].model_dump(mode="json"))
    base = comparisons["base"].pipeline
    if not (
        base.domain_status == "accepted"
        and base.hydraulic_verification["passed"]
        and base.constraint_audit["passed"]
        and base.solve_time_seconds <= float(assumptions["pipeline"]["solver_time_limit_seconds"]) + 1.0
        and (base.optimality_gap or 0.0) <= float(assumptions["pipeline"]["solver_ratio_gap"]) + 1e-9
    ):
        raise RuntimeError("Full Feature 002 base-case acceptance gate failed.")

    pipeline_costs = [comparisons[case].pipeline.costs.levelized_delivered_usd_per_tonne for case in ("low", "base", "high")]
    trucking_costs = [comparisons[case].trucking.levelized_delivered_usd_per_tonne for case in ("low", "base", "high")]
    if pipeline_costs != sorted(pipeline_costs) or trucking_costs != sorted(trucking_costs):
        raise RuntimeError("Low/base/high supply costs are not monotonic.")

    _write_json(output_dir / "route_library.json", library.model_dump(mode="json"))
    _write_json(output_dir / "pipeline_design_base.json", base.model_dump(mode="json"))
    _write_json(output_dir / "rational_zero_selection.json", rational_zero.model_dump(mode="json"))
    exclusion_zones, exclusion_metadata = load_exclusion_zones(assumptions["routing"]["exclusion_geojson_path"])
    _write_json(
        output_dir / "exclusion_audit.json",
        {
            "passed": all(not item.hard_exclusion_ids for item in library.segments),
            "metadata": exclusion_metadata,
            "zones": [item.model_dump(mode="json") for item in exclusion_zones],
            "penalized_segments": [
                {"segment_id": item.id, "zone_ids": item.penalty_zone_ids, "penalty_cost": item.penalty_cost}
                for item in library.segments
                if item.penalty_zone_ids
            ],
        },
    )
    _write_json(output_dir / "constraint_audit.json", {"constraints": base.constraint_audit, "hydraulics": base.hydraulic_verification})
    _write_json(
        output_dir / "solver_report.json",
        {
            case: {
                "solver": result.pipeline.solver,
                "solver_status": result.pipeline.solver_status,
                "termination_condition": result.pipeline.termination_condition,
                "objective_value_usd": result.pipeline.objective_value_usd,
                "objective_bound_usd": result.pipeline.objective_bound_usd,
                "optimality_gap": result.pipeline.optimality_gap,
                "solve_time_seconds": result.pipeline.solve_time_seconds,
            }
            for case, result in comparisons.items()
        },
    )
    _write_csv(
        output_dir / "selected_rejected_wells.csv",
        ["candidate_id", "selected", "reason"],
        [item.model_dump() for item in base.well_decisions],
    )
    _write_csv(
        output_dir / "booster_duties.csv",
        ["node_id", "suction_pressure_bar", "discharge_pressure_bar", "lift_bar", "mass_flow_kg_s", "power_kw", "capex_usd", "annual_energy_cost_usd"],
        [item.model_dump() for item in base.boosters],
    )
    constraint_rows = [{"audit": "constraint", "metric": key, "value": value} for key, value in base.constraint_audit.items()]
    constraint_rows += [{"audit": "hydraulic", "metric": key, "value": json.dumps(value) if isinstance(value, (dict, list)) else value} for key, value in base.hydraulic_verification.items()]
    _write_csv(output_dir / "constraint_table.csv", ["audit", "metric", "value"], constraint_rows)
    cost_rows = [
        {
            "cost_case": case,
            "pipeline_levelized_transport_usd_per_tonne": comparisons[case].pipeline.costs.levelized_transport_usd_per_tonne,
            "pipeline_levelized_delivered_usd_per_tonne": comparisons[case].pipeline.costs.levelized_delivered_usd_per_tonne,
            "trucking_levelized_delivered_usd_per_tonne": comparisons[case].trucking.levelized_delivered_usd_per_tonne,
            "cheaper_mode": comparisons[case].cheaper_mode,
            "accounting_basis": comparisons[case].accounting_basis,
        }
        for case in ("low", "base", "high")
    ]
    _write_csv(output_dir / "cost_sensitivity.csv", list(cost_rows[0]), cost_rows)
    fig, ax = plt.subplots(figsize=(7, 4.5))
    positions = np.arange(3)
    ax.plot(positions, pipeline_costs, marker="o", label="Subang pipeline")
    ax.plot(positions, trucking_costs, marker="o", label="Subang trucking")
    ax.set_yscale("log")
    ax.set(xticks=positions, xticklabels=["Low", "Base", "High"], ylabel="Levelized delivered cost (USD/t, log scale)", title="Screening logistics cost sensitivity")
    ax.grid(alpha=0.2)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(output_dir / "cost_sensitivity.png", dpi=180)
    plt.close(fig)
    _plot_routes(output_dir / "route_map.png", library, base, assumptions["routing"]["exclusion_geojson_path"])
    _pressure_artifacts(output_dir, base)
    _hydraulic_curve_artifacts(output_dir, base)

    artifacts = {}
    for path in sorted(output_dir.iterdir()):
        if path.is_file() and path.name != "artifact_manifest.json":
            artifacts[path.name] = {"sha256": sha256_file(path), "bytes": path.stat().st_size}
    manifest = {
        "feature": "002-pipeline-optimizer",
        "verdict": "pass",
        "screening_status": "screening_grade_not_feed_or_vendor_quote",
        "candidate_count": len(candidates),
        "candidate_prefiltering": False,
        "default_net_value_status": rational_zero.domain_status,
        "validated_design_status": base.domain_status,
        "selected_well_count": len(base.selected_wells),
        "route_library_fingerprint": library.fingerprint,
        "solver_time_seconds": base.solve_time_seconds,
        "optimality_gap": base.optimality_gap,
        "maximum_pwl_error_bar": base.hydraulic_verification["maximum_pwl_error_bar"],
        "inputs": {
            "assumptions_path": str(assumptions_path),
            "assumptions_sha256": sha256_file(assumptions_path),
            "terrain_sha256": library.provenance["terrain_sha256"],
            "exclusion_sha256": exclusion_metadata["sha256"],
            "cost_basis_sha256": sha256_file(Path(assumptions["pipeline"]["cost_basis_path"])),
        },
        "artifacts": artifacts,
    }
    _write_json(output_dir / "artifact_manifest.json", manifest)
    return validate_artifact_bundle(output_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the Feature 002 screening validation bundle.")
    parser.add_argument("--assumptions", type=Path, default=DEFAULT_ASSUMPTIONS)
    parser.add_argument("--output", type=Path, default=Path("paper/validation/feature002"))
    args = parser.parse_args()
    print(json.dumps(generate_validation_bundle(args.assumptions, args.output), indent=2))


if __name__ == "__main__":
    main()
