from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from statistics import mean
from typing import Any

import numpy as np
from jsonschema import Draft202012Validator, validate

from jatibarang_ccus.contracts import (
    AnnualEconomicPeriod,
    AnnualUncertainty,
    EconomicBatchRequest,
    EconomicProvenance,
    EconomicUncertaintyProfile,
    FacilityEconomicInput,
    FiscalCase,
    FlatDeliveredSupplyCost,
    PipelineRawSupplyCost,
    PortfolioEconomicInput,
)
from jatibarang_ccus.infrastructure.economic_adapters import (
    assumptions_from_basis,
    basis_provenance,
    carbon_prices_from_basis,
    fiscal_cases_from_basis,
    load_economic_basis,
)
from jatibarang_ccus.infrastructure.economics import M3_TO_BBL, evaluate_economic_batch
from jatibarang_ccus.surrogate.config import REPO_ROOT

DEFAULT_OUTPUT = REPO_ROOT / "paper" / "validation" / "feature004"
DEFAULT_SCHEMA = REPO_ROOT / "specs" / "004-economic-engine" / "contracts" / "economic-engine.schema.json"


def _provenance(source_id: str) -> list[EconomicProvenance]:
    return [
        EconomicProvenance(
            source_class="engineering_assumption",
            source_id=source_id,
            notes="Deterministic Feature 004 validation fixture.",
        )
    ]


def _reference_portfolio(
    *,
    portfolio_id: str,
    oil_m3: list[float],
    injected: list[float],
    produced_back: list[float],
    facility_capex: float,
    pipeline_capex: float,
    oil_error: float,
    co2_error: float,
    project_life: int = 8,
) -> PortfolioEconomicInput:
    provenance = _provenance(portfolio_id)
    density = 1.8685
    fraction = 0.30
    periods = []
    uncertainties = []
    for index, (oil, injection, back) in enumerate(zip(oil_m3, injected, produced_back), start=1):
        gross_gas = back * 1_000.0 / (fraction * density) * 1.02 if back else 0.0
        periods.append(
            AnnualEconomicPeriod(
                year=index,
                injection_hours=1_080,
                production_hours=4_560,
                oil_produced_m3=oil,
                gross_gas_produced_std_m3=gross_gas,
                produced_co2_fraction=fraction,
                co2_standard_density_kg_m3=density,
                injected_co2_tonnes=injection,
                inventory_produced_back_co2_tonnes=back,
                surface_loss_co2_tonnes=injection * 0.005,
                workover_count=1,
            )
        )
        uncertainties.append(
            AnnualUncertainty(
                year=index,
                oil_error_fraction=oil_error,
                gas_error_fraction=oil_error,
                co2_mass_error_fraction=co2_error,
            )
        )
    active = [30_000.0 if index < len(periods) else 0.0 for index in range(project_life)]
    energy = [15_000.0 if index < len(periods) else 0.0 for index in range(project_life)]
    facility_opex = [50_000.0 if index < len(periods) else 0.0 for index in range(project_life)]
    return PortfolioEconomicInput(
        portfolio_id=portfolio_id,
        project_life_years=project_life,
        periods=periods,
        supply=PipelineRawSupplyCost(
            pipeline_capex_usd=pipeline_capex,
            booster_capex_usd=0.1 * pipeline_capex,
            annual_maintenance_usd=active,
            annual_booster_energy_usd=energy,
            commodity_supply_usd_per_tonne=8.0,
            provenance=provenance,
        ),
        facility=FacilityEconomicInput(
            capex_usd=facility_capex,
            annual_opex_usd=facility_opex,
            provenance=provenance,
        ),
        uncertainty=EconomicUncertaintyProfile(
            periods=uncertainties,
            provenance=provenance,
        ),
        terminal_cashflow_usd=-100_000.0,
        provenance=provenance,
    )


def build_reference_request(basis: dict[str, Any]) -> EconomicBatchRequest:
    portfolios = [
        _reference_portfolio(
            portfolio_id="oil_led",
            oil_m3=[5_000, 3_000, 1_000],
            injected=[2_000, 1_000, 500],
            produced_back=[200, 100, 50],
            facility_capex=1_500_000,
            pipeline_capex=500_000,
            oil_error=0.25,
            co2_error=0.10,
        ),
        _reference_portfolio(
            portfolio_id="storage_led",
            oil_m3=[2_500, 1_500, 500],
            injected=[30_000, 20_000, 10_000],
            produced_back=[600, 400, 200],
            facility_capex=1_200_000,
            pipeline_capex=350_000,
            oil_error=0.04,
            co2_error=0.06,
        ),
        _reference_portfolio(
            portfolio_id="balanced",
            oil_m3=[3_400, 2_200, 700],
            injected=[14_000, 8_000, 4_000],
            produced_back=[400, 250, 100],
            facility_capex=1_250_000,
            pipeline_capex=400_000,
            oil_error=0.10,
            co2_error=0.08,
        ),
    ]
    return EconomicBatchRequest(
        portfolios=portfolios,
        carbon_prices=carbon_prices_from_basis(basis),
        fiscal_cases=fiscal_cases_from_basis(basis),
        assumptions=assumptions_from_basis(basis),
        provenance=basis_provenance(basis),
    )


def _metric_request(basis: dict[str, Any]) -> EconomicBatchRequest:
    provenance = _provenance("closed-form-metrics")
    assumptions = assumptions_from_basis(basis).model_copy(
        update={
            "discount_rate": 0.0,
            "oil_price_usd_per_bbl": 1.0,
            "gas_price_usd_per_mmbtu": 0.0,
            "lifting_cost_usd_per_bbl": 0.0,
            "workover_cost_usd_per_cycle": 0.0,
            "mrv_cost_usd_per_tonne": 0.0,
        }
    )

    def portfolio(portfolio_id: str, cashflows: list[float]) -> PortfolioEconomicInput:
        periods = [
            AnnualEconomicPeriod(
                year=year,
                oil_produced_m3=max(value, 0.0) / M3_TO_BBL,
                inventory_produced_back_co2_tonnes=0.0,
            )
            for year, value in enumerate(cashflows[1:], start=1)
        ]
        opex = [max(-value, 0.0) for value in cashflows[1:]]
        return PortfolioEconomicInput(
            portfolio_id=portfolio_id,
            project_life_years=len(cashflows) - 1,
            periods=periods,
            supply=FlatDeliveredSupplyCost(
                delivered_cost_usd_per_tonne=0.0,
                provenance=provenance,
            ),
            facility=FacilityEconomicInput(
                capex_usd=-cashflows[0],
                annual_opex_usd=opex,
                provenance=provenance,
            ),
            uncertainty=EconomicUncertaintyProfile(provenance=provenance),
            provenance=provenance,
        )

    return EconomicBatchRequest(
        portfolios=[
            portfolio("known_irr", [-100.0, 60.0, 60.0]),
            portfolio("multiple_irr", [-100.0, 230.0, -132.0]),
            portfolio("no_root", [-100.0, -10.0, -10.0]),
        ],
        carbon_prices=carbon_prices_from_basis(basis),
        fiscal_cases=[FiscalCase(case_id="pre_tax", mode="pre_tax", provenance=provenance)],
        assumptions=assumptions,
        provenance=provenance,
    )


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"No rows supplied for {path.name}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _benchmark_request(reference: EconomicBatchRequest) -> EconomicBatchRequest:
    templates = reference.portfolios
    portfolios = []
    for index in range(200):
        template = templates[index % len(templates)]
        # Benchmark the three active campaign years with the normal screening
        # default of no terminal cash flow, and perturb ownership CAPEX so all
        # 200 cash-flow vectors are genuinely distinct.
        facility = template.facility.model_copy(
            update={
                "capex_usd": template.facility.capex_usd + index * 137.0,
                "annual_opex_usd": template.facility.annual_opex_usd[:3],
            }
        )
        supply = template.supply.model_copy(
            update={
                "annual_maintenance_usd": template.supply.annual_maintenance_usd[:3],
                "annual_booster_energy_usd": template.supply.annual_booster_energy_usd[:3],
            }
        )
        portfolios.append(
            template.model_copy(
                update={
                    "portfolio_id": f"benchmark_{index:03d}",
                    "project_life_years": 3,
                    "supply": supply,
                    "facility": facility,
                    "terminal_cashflow_usd": 0.0,
                }
            )
        )
    return reference.model_copy(update={"portfolios": portfolios})


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_artifact_manifest(output: Path) -> Path:
    manifest_path = output / "artifact_manifest.json"
    artifacts = []
    for path in sorted(output.iterdir(), key=lambda item: item.name):
        if not path.is_file() or path == manifest_path:
            continue
        artifacts.append(
            {
                "path": path.name,
                "sha256": _sha256(path),
                "bytes": path.stat().st_size,
            }
        )
    manifest = {
        "schema_version": "1.0",
        "feature": "004-economic-engine",
        "algorithm": "SHA-256",
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def verify_artifact_manifest(manifest: str | Path) -> list[str]:
    manifest_path = Path(manifest)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors = []
    for artifact in payload["artifacts"]:
        path = manifest_path.parent / artifact["path"]
        if not path.exists():
            errors.append(f"missing:{artifact['path']}")
        elif path.stat().st_size != artifact["bytes"]:
            errors.append(f"size:{artifact['path']}")
        elif _sha256(path) != artifact["sha256"]:
            errors.append(f"sha256:{artifact['path']}")
    return errors


def generate_evidence(basis_path: Path, output: Path, performance_runs: int = 5) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    basis = load_economic_basis(basis_path)
    reference = build_reference_request(basis)
    result = evaluate_economic_batch(reference)

    cashflow_rows = []
    for scenario in result.results:
        if scenario.fiscal_case_id != "pre_tax":
            continue
        for row in scenario.annual_cashflows:
            cashflow_rows.append(
                {
                    "portfolio_id": scenario.portfolio_id,
                    "carbon_price_scenario_id": scenario.carbon_price_scenario_id,
                    **row.model_dump(),
                }
            )
    _write_csv(output / "reference_cashflows.csv", cashflow_rows)

    reconciliation_rows = [
        {
            "portfolio_id": item.portfolio_id,
            "carbon_price_scenario_id": item.carbon_price_scenario_id,
            "fiscal_case_id": item.fiscal_case_id,
            "accounting_reconciliation_usd": item.accounting_reconciliation_usd,
            "storage_divergence_tonnes": item.storage.absolute_divergence_tonnes,
            "storage_divergence_fraction": item.storage.divergence_fraction_of_injected,
            "storage_mass_balance_residual_tonnes": item.storage.mass_balance_residual_tonnes,
            "storage_mass_balance_passed": item.storage.mass_balance_passed,
            "passed": item.reconciliation_passed,
        }
        for item in result.results
    ]
    _write_csv(output / "accounting_reconciliation.csv", reconciliation_rows)

    sensitivity_rows = [
        {
            "portfolio_id": item.portfolio_id,
            "carbon_price_scenario_id": item.carbon_price_scenario_id,
            "carbon_price_usd_per_tonne": next(
                price.carbon_price_usd_per_tonne
                for price in reference.carbon_prices
                if price.scenario_id == item.carbon_price_scenario_id
            ),
            "fiscal_case_id": item.fiscal_case_id,
            "npv_usd": item.npv_usd,
            "npv_low_usd": item.npv_low_usd,
            "npv_high_usd": item.npv_high_usd,
            "break_even_carbon_price_usd_per_tonne": item.break_even_carbon_price.value,
        }
        for item in result.results
    ]
    _write_csv(output / "carbon_price_sensitivity.csv", sensitivity_rows)

    ranking_rows = [
        {
            "carbon_price_scenario_id": item.carbon_price_scenario_id,
            "fiscal_case_id": item.fiscal_case_id,
            "base_order": ">".join(item.base_order),
            "downside_order": ">".join(item.downside_order),
            "upside_order": ">".join(item.upside_order),
            "stable_across_bounds": item.stable_across_bounds,
        }
        for item in result.rankings
    ]
    _write_csv(output / "uncertainty_ranking.csv", ranking_rows)

    metric_result = evaluate_economic_batch(_metric_request(basis))
    metric_by_id = {
        item.portfolio_id: item
        for item in metric_result.results
        if item.carbon_price_scenario_id == metric_result.results[0].carbon_price_scenario_id
    }
    metric_payload = {
        "known_irr": {
            "expected": 0.1306623863,
            "actual": metric_by_id["known_irr"].irr.value,
            "absolute_error": abs(metric_by_id["known_irr"].irr.value - 0.1306623863),
            "status": metric_by_id["known_irr"].irr.status,
        },
        "fractional_discounted_payback": {
            "expected_years": 1.6666666667,
            "actual_years": metric_by_id["known_irr"].discounted_payback.value,
        },
        "multiple_root_status": metric_by_id["multiple_irr"].irr.status,
        "no_root_status": metric_by_id["no_root"].irr.status,
        "accounting_verdict": metric_result.accounting_verdict,
        "passed": (
            abs(metric_by_id["known_irr"].irr.value - 0.1306623863) < 1e-8
            and metric_by_id["multiple_irr"].irr.status == "multiple_roots"
            and metric_by_id["no_root"].irr.status == "no_root"
        ),
    }
    (output / "metric_verification.json").write_text(
        json.dumps(metric_payload, indent=2) + "\n", encoding="utf-8"
    )

    schema = json.loads(DEFAULT_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validate(reference.model_dump(mode="json"), schema)
    validate(result.model_dump(mode="json"), schema)
    schema_payload = {
        "schema": str(DEFAULT_SCHEMA.relative_to(REPO_ROOT)).replace("\\", "/"),
        "draft": "2020-12",
        "request_valid": True,
        "result_valid": True,
    }
    (output / "schema_validation.json").write_text(
        json.dumps(schema_payload, indent=2) + "\n", encoding="utf-8"
    )

    benchmark = _benchmark_request(reference)
    evaluate_economic_batch(benchmark)
    timings = [evaluate_economic_batch(benchmark).elapsed_seconds for _ in range(performance_runs)]
    p95 = float(np.percentile(timings, 95))
    performance_payload = {
        "portfolio_count": 200,
        "carbon_price_count": 4,
        "fiscal_mode_count": 3,
        "scenario_count": 2_400,
        "project_life_years": 3,
        "distinct_cashflow_vectors": 200,
        "terminal_cashflow_usd": 0.0,
        "warmed_runs_seconds": timings,
        "mean_seconds": mean(timings),
        "p95_seconds": p95,
        "threshold_seconds": 1.0,
        "passed": p95 <= 1.0,
        "machine_scope": "presentation_machine_local_run",
    }
    (output / "performance_benchmark.json").write_text(
        json.dumps(performance_payload, indent=2) + "\n", encoding="utf-8"
    )

    summary = {
        "economic_basis_version": result.economic_basis_version,
        "scenario_count": result.scenario_count,
        "accounting_verdict": result.accounting_verdict,
        "maximum_accounting_residual_usd": max(
            item.accounting_reconciliation_usd for item in result.results
        ),
        "maximum_storage_divergence_fraction": max(
            item.storage.divergence_fraction_of_injected for item in result.results
        ),
        "maximum_storage_mass_balance_residual_tonnes": max(
            item.storage.mass_balance_residual_tonnes for item in result.results
        ),
        "ranking_pivot_across_carbon_prices": len(
            {
                tuple(item.base_order)
                for item in result.rankings
                if item.fiscal_case_id == "pre_tax"
            }
        )
        > 1,
        "uncertainty_ranking_instability_present": any(
            not item.stable_across_bounds for item in result.rankings
        ),
        "metric_checks_passed": metric_payload["passed"],
        "schema_validation_passed": True,
        "performance_passed": performance_payload["passed"],
        "qualification": result.qualification,
        "promotion_verdict": "PASS"
        if result.accounting_verdict == "PASS"
        and metric_payload["passed"]
        and performance_payload["passed"]
        else "FAIL",
    }
    (output / "validation_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    manifest = write_artifact_manifest(output)
    errors = verify_artifact_manifest(manifest)
    if errors:
        raise RuntimeError(f"Artifact manifest verification failed: {errors}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate and verify Feature 004 evidence.")
    parser.add_argument("--basis", type=Path, default=Path("data/jatibarang/economic_basis.json"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--performance-runs", type=int, default=5)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.verify_only:
        errors = verify_artifact_manifest(args.output / "artifact_manifest.json")
        if errors:
            raise SystemExit("\n".join(errors))
        print("Feature 004 artifact manifest: PASS")
        return
    summary = generate_evidence(args.basis, args.output, args.performance_runs)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
