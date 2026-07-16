from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import threading
from time import sleep
from typing import Any

import psutil
import yaml

from jatibarang_ccus.api.app import create_app
from jatibarang_ccus.surrogate.runner import load_surrogate

from .orchestrator import build_default_orchestrator
from .schemas import PresetScreenRequest, ScreenResult


DEFAULT_OUTPUT = Path("paper/validation/feature005")


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    columns = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _artifact_manifest(output: Path) -> dict[str, Any]:
    entries = []
    for path in sorted(output.iterdir(), key=lambda item: item.name):
        if not path.is_file() or path.name == "artifact_manifest.json":
            continue
        entries.append({"path": path.name, "sha256": _sha256(path), "bytes": path.stat().st_size})
    payload = {"schema_version": "1.0", "hash_algorithm": "SHA-256", "artifacts": entries}
    _write_json(output / "artifact_manifest.json", payload)
    return payload


def verify_artifacts(output: Path) -> list[str]:
    manifest_path = output / "artifact_manifest.json"
    if not manifest_path.exists():
        return ["artifact_manifest.json is missing"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors = []
    for entry in manifest.get("artifacts", []):
        path = output / entry["path"]
        if not path.exists():
            errors.append(f"missing artifact: {entry['path']}")
        elif _sha256(path) != entry["sha256"]:
            errors.append(f"SHA-256 mismatch: {entry['path']}")
    return errors


def _compact_result(result: ScreenResult) -> dict[str, Any]:
    plans = []
    for plan in result.plans:
        aggregate = None
        if plan.economics is not None:
            portfolio_id = f"portfolio--{plan.carbon_price_scenario_id}"
            aggregate = [
                {
                    "portfolio_id": item.portfolio_id,
                    "carbon_price_scenario_id": item.carbon_price_scenario_id,
                    "fiscal_case_id": item.fiscal_case_id,
                    "npv_usd": item.npv_usd,
                    "net_stored_co2_tonnes": item.storage.primary_net_stored_co2_tonnes,
                    "reconciliation_passed": item.reconciliation_passed,
                }
                for item in plan.economics.results
                if item.portfolio_id == portfolio_id
            ]
        plans.append(
            {
                "carbon_price_scenario_id": plan.carbon_price_scenario_id,
                "domain_status": plan.domain_status,
                "selected_wells": plan.selected_wells,
                "objective_value_usd": plan.pipeline.objective_value_usd,
                "pipeline_costs": plan.pipeline.costs.model_dump(mode="json"),
                "facility_total_capex_usd": (
                    plan.facility.total_capex_usd if plan.facility is not None else None
                ),
                "aggregate_economics": aggregate,
                "trucking_delivered_cost_usd_per_tonne": (
                    plan.trucking_counterfactual.supply.levelized_delivered_usd_per_tonne
                    if plan.trucking_counterfactual is not None
                    else None
                ),
                "flag_codes": [item.code for item in plan.flags],
            }
        )
    return {
        "run_id": result.run_id,
        "request_fingerprint": result.request_fingerprint,
        "status": result.status,
        "logical_scenario_count": result.logical_scenario_count,
        "unique_inference_count": result.unique_inference_count,
        "inference_cache_hits": result.inference_cache_hits,
        "plans": plans,
        "cross_price_comparison": result.cross_price_comparison.model_dump(mode="json"),
        "shortlist": [item.model_dump(mode="json") for item in result.shortlist],
        "timings": result.timings.model_dump(mode="json"),
        "warnings": result.warnings,
        "provenance_catalog": result.provenance_catalog,
    }


def run_validation(preset_id: str, output: Path) -> int:
    output.mkdir(parents=True, exist_ok=True)
    runner = load_surrogate()
    orchestrator = build_default_orchestrator(runner)
    health = orchestrator.health()
    _write_json(output / "dependency_report.json", health.model_dump(mode="json"))
    preset = next(item for item in health.presets if item.preset_id == preset_id)
    _write_json(output / "preset_hash_report.json", preset.model_dump(mode="json"))
    generated_openapi = create_app().openapi()
    contract = yaml.safe_load(
        Path("specs/005-screening-api/contracts/openapi.yaml").read_text(encoding="utf-8")
    )
    schema_report = {
        "info_parity": generated_openapi["info"] == contract["info"],
        "expected_paths": sorted(contract["paths"]),
        "generated_paths": sorted(generated_openapi["paths"]),
        "feature005_path_parity": all(path in generated_openapi["paths"] for path in contract["paths"]),
    }
    _write_json(output / "schema_report.json", schema_report)
    if not preset.ready:
        summary = {
            "mechanical_verdict": "BLOCKED",
            "scientific_promotion": "NOT_RUN",
            "preset_id": preset_id,
            "reason": preset.reason,
            "fabricated_result": False,
        }
        _write_json(output / "validation_summary.json", summary)
        (output / "README.md").write_text(
            "# Feature 005 validation\n\n"
            "Mechanical promotion is blocked because the derived MRST preset payload is not present. "
            "No result was fabricated. Generate the fixed seed bank with the upstream exporter, import it, "
            "and rerun this command. A bounded one-seed exporter smoke, when present, validates only the "
            "offline producer and does not make the preset ready. Scientific and paper promotion remain "
            "Feature 007 work.\n",
            encoding="utf-8",
        )
        _artifact_manifest(output)
        return 2

    request = PresetScreenRequest(mode="preset", preset_id=preset_id, run_id="feature005-promotion")
    _write_json(output / "request.json", request.model_dump(mode="json"))
    process = psutil.Process()
    peak_rss = process.memory_info().rss
    monitoring = True

    def monitor() -> None:
        nonlocal peak_rss
        while monitoring:
            peak_rss = max(peak_rss, process.memory_info().rss)
            sleep(0.05)

    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    events = list(orchestrator.stream(request))
    monitoring = False
    thread.join(timeout=1.0)
    with (output / "sse_trace.jsonl").open("w", encoding="utf-8") as handle:
        for item in events:
            payload = item.model_dump(mode="json")
            if item.event == "result":
                payload["payload"] = {"result_reference": "result_compact.json"}
            handle.write(json.dumps(payload, separators=(",", ":")) + "\n")
    terminal = events[-1]
    if terminal.event != "result":
        _write_json(
            output / "validation_summary.json",
            {
                "mechanical_verdict": "FAIL",
                "scientific_promotion": "NOT_RUN",
                "terminal_event": terminal.model_dump(mode="json"),
            },
        )
        _artifact_manifest(output)
        return 1
    result = ScreenResult.model_validate(terminal.payload["result"])
    _write_json(output / "result_compact.json", _compact_result(result))
    _write_json(
        output / "performance_report.json",
        {
            "total_seconds": result.timings.total_seconds,
            "peak_rss_bytes": peak_rss,
            "peak_rss_gib": peak_rss / (1024**3),
            "demo_under_600_seconds": result.timings.total_seconds <= 600,
            "under_4_gib": peak_rss <= 4 * 1024**3,
            "milp_solve_seconds": result.timings.milp_solve_seconds,
        },
    )
    reconciliation_rows = []
    discrepancy_rows = []
    interference_rows = []
    trucking_rows = []
    for plan in result.plans:
        reconciliation_rows.append(
            {
                "carbon_price": plan.carbon_price_scenario_id,
                "pipeline_allocated_usd": sum(plan.pipeline.per_well_allocated_cost_usd.values()),
                "pipeline_lifecycle_usd": plan.pipeline.costs.present_value_lifecycle_cost_usd,
                "facility_reconciled": (
                    plan.facility.reconciliation_passed if plan.facility is not None else ""
                ),
                "economic_accounting_verdict": (
                    plan.economics.accounting_verdict if plan.economics is not None else ""
                ),
            }
        )
        if plan.discrepancy_audit is not None:
            discrepancy_rows.append(
                {
                    "carbon_price": plan.carbon_price_scenario_id,
                    "original_selected": "|".join(plan.discrepancy_audit.original_selected_wells),
                    "audit_selected": "|".join(plan.discrepancy_audit.audit_selected_wells),
                    "entrants": "|".join(plan.discrepancy_audit.entrants),
                    "exits": "|".join(plan.discrepancy_audit.exits),
                }
            )
        interference_rows.extend(
            {
                "carbon_price": plan.carbon_price_scenario_id,
                **item.model_dump(mode="json"),
            }
            for item in plan.interference.flagged_pairs
        )
        if plan.trucking_counterfactual is not None:
            trucking_rows.append(
                {
                    "carbon_price": plan.carbon_price_scenario_id,
                    "selected_wells": "|".join(plan.selected_wells),
                    "pipeline_delivered_usd_per_tonne": plan.pipeline.costs.levelized_delivered_usd_per_tonne,
                    "trucking_delivered_usd_per_tonne": plan.trucking_counterfactual.supply.levelized_delivered_usd_per_tonne,
                }
            )
    _write_csv(output / "module_reconciliation.csv", reconciliation_rows)
    _write_csv(output / "selection_discrepancy.csv", discrepancy_rows)
    _write_csv(output / "interference_pairs.csv", interference_rows)
    _write_csv(output / "trucking_counterfactual.csv", trucking_rows)
    summary = {
        "mechanical_verdict": "PASS",
        "scientific_promotion": "DEFERRED_TO_FEATURE007",
        "preset_id": preset_id,
        "status": result.status,
        "schema_parity": schema_report["info_parity"] and schema_report["feature005_path_parity"],
        "performance_gates_passed": result.timings.total_seconds <= 600 and peak_rss <= 4 * 1024**3,
        "pivot_observed": result.cross_price_comparison.pivot_observed,
    }
    _write_json(output / "validation_summary.json", summary)
    (output / "README.md").write_text(
        "# Feature 005 validation\n\n"
        "This directory records the mechanical API promotion run for the derived demo preset. "
        "A PASS here does not promote scientific or paper-facing numbers; Feature 007 owns that decision.\n",
        encoding="utf-8",
    )
    _artifact_manifest(output)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Promote or verify Feature 005 mechanical evidence.")
    parser.add_argument("--preset", default="jatibarang_demo_v1")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verify-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.verify_only:
        errors = verify_artifacts(args.output)
        print(json.dumps({"verdict": "PASS" if not errors else "FAIL", "errors": errors}))
        return 0 if not errors else 1
    return run_validation(args.preset, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
