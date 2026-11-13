from __future__ import annotations

import json
import math
from pathlib import Path
import statistics
from typing import Any, Iterable

import numpy as np

from jatibarang_ccus.contracts import (
    EconomicBatchRequest,
    FacilityPortfolioRequest,
    FacilityProvenance,
    PortfolioEconomicInput,
)
from jatibarang_ccus.infrastructure.economic_adapters import (
    annualize_prediction,
    apply_facility_surface_loss,
    basis_provenance,
    facility_for_well,
    pipeline_raw_supply,
    uncertainty_from_prediction,
)
from jatibarang_ccus.infrastructure.facility import DEFAULT_COST_BASIS, DEFAULT_DESIGN_BASIS
from jatibarang_ccus.infrastructure.facility_costs import (
    load_cost_basis,
    load_design_basis,
)
from jatibarang_ccus.paper.field_scenarios import FieldScenarioExperimentResult
from jatibarang_ccus.screening.adapters import facility_well_from_prediction
from jatibarang_ccus.screening.orchestrator import (
    ScreeningOrchestrator,
    build_default_orchestrator,
)
from jatibarang_ccus.screening.presets import CompactPresetBank
from jatibarang_ccus.screening.schemas import ScreenResult
from jatibarang_ccus.surrogate.config import REPO_ROOT
from jatibarang_ccus.surrogate.runner import load_surrogate

from .arm_ab import (
    TOP5_MANIFEST,
    _entry_path,
    prediction_result_from_mrst,
    verify_all_mrst_manifests,
)
from .arm_c import DEFAULT_WORKSPACE, FULL_PRESET_ID
from .schemas import (
    AbcEconomicsRow,
    AbcRuntimeRow,
    DwsimConfirmationRow,
    TopKConfirmationRow,
    atomic_write_csv,
    atomic_write_json,
    canonical_sha256,
    sha256_file,
)


def _quantile(values: list[float], probability: float) -> float:
    return float(np.quantile(np.asarray(values, dtype=float), probability))


def _finite_mean(values: Iterable[Any]) -> tuple[float | None, int]:
    finite = [
        float(value)
        for value in values
        if value is not None
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    ]
    return (statistics.fmean(finite), len(finite)) if finite else (None, 0)


def _metric_value(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("value")
    if value is None or not math.isfinite(float(value)):
        return None
    return float(value)


def _designated_economic(plan: dict[str, Any]) -> dict[str, Any]:
    price_id = plan["carbon_price_scenario_id"]
    economics = plan.get("economics")
    if economics is None:
        raise ValueError(f"plan {price_id} has no final economics")
    matches = [
        row
        for row in economics["results"]
        if row["portfolio_id"] == f"portfolio--{price_id}"
        and row["carbon_price_scenario_id"] == price_id
        and row["fiscal_case_id"] == "pre_tax"
    ]
    if len(matches) != 1:
        raise ValueError(f"plan {price_id} lacks one designated aggregate")
    return matches[0]


def economics_rows_from_screen_result(
    arm: str,
    result: dict[str, Any],
) -> list[AbcEconomicsRow]:
    source_class = (
        "arm_c_integrated_result"
        if arm == "C"
        else "mrst_and_surrogate_integrated_result"
    )
    rows = []
    for plan in result["plans"]:
        economic = _designated_economic(plan)
        irr = _metric_value(economic["irr"])
        payback = _metric_value(economic["discounted_payback"])
        break_even_carbon = _metric_value(
            economic["break_even_carbon_price"]
        )
        break_even_oil = _metric_value(
            economic["break_even_oil_price"]
        )
        rows.append(
            AbcEconomicsRow(
                arm=arm,
                carbon_price_usd_per_tonne=float(
                    plan["carbon_price_usd_per_tonne"]
                ),
                npv_usd=float(economic["npv_usd"]),
                npv_low_usd=float(economic["npv_low_usd"]),
                npv_high_usd=float(economic["npv_high_usd"]),
                irr=irr,
                payback_years=payback,
                breakeven_carbon_usd_per_tonne=break_even_carbon,
                breakeven_oil_usd_per_bbl=break_even_oil,
                fiscal_case="pre_tax",
                valid_metric_count=1,
                npv_valid_count=1,
                irr_valid_count=int(irr is not None),
                payback_valid_count=int(payback is not None),
                breakeven_carbon_valid_count=int(
                    break_even_carbon is not None
                ),
                breakeven_oil_valid_count=int(
                    break_even_oil is not None
                ),
                source_class=source_class,
                carbon_price_scenario_id=plan[
                    "carbon_price_scenario_id"
                ],
            )
        )
    return rows


def economics_rows_from_field_scenarios(
    arm_c: dict[str, Any],
) -> list[AbcEconomicsRow]:
    experiment = FieldScenarioExperimentResult.model_validate(
        arm_c["field_scenario"]
    )
    prices = {
        plan["carbon_price_scenario_id"]: float(
            plan["carbon_price_usd_per_tonne"]
        )
        for plan in arm_c["screen_result"]["plans"]
    }
    expected_assignments = int(
        arm_c.get("independent_assignment_count", 20)
    )
    if expected_assignments < 1:
        raise ValueError("Arm C independent assignment count must be positive")
    rows = []
    for price_id, price in sorted(prices.items(), key=lambda item: item[1]):
        records = [
            record
            for record in experiment.independent
            if record.carbon_price_scenario_id == price_id
            and record.result.get("portfolio_npv_usd") is not None
        ]
        if len(records) != expected_assignments:
            raise ValueError(
                f"Arm C price {price_id} has "
                f"{len(records)}/{expected_assignments} independent results"
            )
        npv = [float(record.result["portfolio_npv_usd"]) for record in records]
        irr, irr_count = _finite_mean(record.result.get("irr") for record in records)
        payback, payback_count = _finite_mean(
            record.result.get("payback_years") for record in records
        )
        break_even_carbon, break_even_carbon_count = _finite_mean(
            record.result.get(
                "break_even_carbon_price_usd_per_tonne"
            )
            for record in records
        )
        break_even_oil, break_even_oil_count = _finite_mean(
            record.result.get("break_even_oil_usd_per_bbl")
            for record in records
        )
        rows.append(
            AbcEconomicsRow(
                arm="C",
                carbon_price_usd_per_tonne=price,
                npv_usd=statistics.fmean(npv),
                npv_low_usd=_quantile(npv, 0.10),
                npv_high_usd=_quantile(npv, 0.90),
                irr=irr,
                payback_years=payback,
                breakeven_carbon_usd_per_tonne=break_even_carbon,
                breakeven_oil_usd_per_bbl=break_even_oil,
                fiscal_case="pre_tax",
                valid_metric_count=len(npv),
                npv_valid_count=len(npv),
                irr_valid_count=irr_count,
                payback_valid_count=payback_count,
                breakeven_carbon_valid_count=break_even_carbon_count,
                breakeven_oil_valid_count=break_even_oil_count,
                source_class="arm_c_integrated_result",
                carbon_price_scenario_id=price_id,
                independent_assignment_count=expected_assignments,
            )
        )
    return rows


def _runtime_summary(manifest: Any) -> tuple[float, int, float]:
    elapsed = sum(float(entry.runtime_seconds) for entry in manifest.entries)
    failed = sum(
        float(entry.runtime_seconds)
        for entry in manifest.entries
        if entry.status == "failed"
    )
    return elapsed, len(manifest.entries), failed


def runtime_rows(
    arm_c: dict[str, Any],
    manifests: dict[str, Any],
) -> list[AbcRuntimeRow]:
    accepted_runtimes = [
        float(entry.runtime_seconds)
        for manifest in manifests.values()
        for entry in manifest.entries
        if entry.status == "accepted"
    ]
    if len(accepted_runtimes) != 47:
        raise ValueError(
            f"runtime equivalence requires 47 accepted full-MRST runs, got {len(accepted_runtimes)}"
        )
    equivalent_weeks = (
        3240 * statistics.fmean(accepted_runtimes) / (7 * 86_400)
    )
    arm_a_seconds, arm_a_attempts, arm_a_failed = _runtime_summary(
        manifests["arm_a"]
    )
    arm_b_seconds, arm_b_attempts, arm_b_failed = _runtime_summary(
        manifests["arm_b"]
    )
    assignment_times: dict[str, float] = {}
    for record in (
        arm_c["field_scenario"]["independent"]
        + arm_c["field_scenario"]["correlated"]
    ):
        assignment_times.setdefault(
            record["assignment_id"],
            float(record["result"].get("downstream_total_seconds", 0.0)),
        )
    downstream_seconds = sum(assignment_times.values())
    screen_seconds = float(
        arm_c.get("timings", {}).get(
            "initial_screen_seconds",
            arm_c["screen_result"]["timings"]["total_seconds"],
        )
    )
    return [
        AbcRuntimeRow(
            arm="A",
            wall_clock_seconds=arm_a_seconds,
            scenarios_evaluated=2,
            economics_scenarios=20,
            accepted_runs=2,
            attempted_runs=arm_a_attempts,
            failed_attempt_seconds=arm_a_failed,
            runtime_kind="measured_full_mrst_confirmations",
            source_class="measured_runtime",
        ),
        AbcRuntimeRow(
            arm="B",
            wall_clock_seconds=arm_b_seconds,
            scenarios_evaluated=40,
            economics_scenarios=40,
            accepted_runs=40,
            attempted_runs=arm_b_attempts,
            failed_attempt_seconds=arm_b_failed,
            runtime_kind="measured_full_mrst_search",
            source_class="measured_runtime",
        ),
        AbcRuntimeRow(
            arm="C",
            wall_clock_seconds=screen_seconds,
            scenarios_evaluated=3240,
            economics_scenarios=3240,
            accepted_runs=0,
            attempted_runs=0,
            downstream_resolve_seconds=downstream_seconds,
            mrst_equivalence_weeks=equivalent_weeks,
            runtime_kind="measured_surrogate_screen_plus_labeled_mrst_equivalence",
            source_class="measured_runtime",
        ),
    ]


def _top5_mrst_value(
    *,
    plan_record: dict[str, Any],
    mrst_prediction: Any,
    screen_result: ScreenResult,
    orchestrator: ScreeningOrchestrator,
    bank: CompactPresetBank,
) -> float:
    price_id = str(plan_record["designated_carbon_price_scenario_id"])
    plan = next(
        item
        for item in screen_result.plans
        if item.carbon_price_scenario_id == price_id
    )
    candidate_id = str(plan_record["candidate_id"])
    if candidate_id not in plan.selected_wells:
        raise ValueError(
            f"top-five plan {plan_record['plan_id']} is not selected at {price_id}"
        )
    strategy = next(
        item
        for item in plan.well_strategies
        if item.scenario_id == plan_record["scenario_id"]
    )
    produced = next(
        item.produced_co2
        for item in bank.metadata.candidates
        if item.candidate_id == candidate_id
    )
    load = facility_well_from_prediction(
        mrst_prediction,
        candidate_id=candidate_id,
        schedule=strategy.schedule,
        delivery_pressure_bar=max(
            80.0,
            float(plan.pipeline.node_pressures_bar[candidate_id]),
        ),
        produced_co2_fraction=produced.mole_fraction,
        project_life_years=bank.metadata.project_life_years,
        assumptions=orchestrator.assumptions,
    )
    design_basis = load_design_basis(DEFAULT_DESIGN_BASIS)
    cost_basis = load_cost_basis(DEFAULT_COST_BASIS)
    facility = orchestrator.services.facility_evaluator(
        FacilityPortfolioRequest(
            portfolio_id=f"mrst-confirmation--{plan_record['plan_id']}",
            cost_case="base",
            design_basis_version=design_basis.version,
            cost_basis_version=cost_basis.version,
            wells=[load],
            provenance=[
                FacilityProvenance(
                    source_class="mrst_truth",
                    source_id=mrst_prediction.scenario_id,
                    notes="Offline top-five full-physics confirmation.",
                )
            ],
        )
    )
    periods = annualize_prediction(
        mrst_prediction,
        project_life_years=bank.metadata.project_life_years,
        produced_co2_fraction=produced.mole_fraction,
    )
    facility_well = facility.well_results[0]
    periods = apply_facility_surface_loss(periods, facility_well)
    allocation_total = sum(
        plan.pipeline.per_well_allocated_cost_usd.get(item, 0.0)
        for item in plan.selected_wells
    )
    if allocation_total > 0:
        allocation = (
            plan.pipeline.per_well_allocated_cost_usd.get(candidate_id, 0.0)
            / allocation_total
        )
    else:
        allocation = 1.0 / len(plan.selected_wells)
    portfolio = PortfolioEconomicInput(
        portfolio_id=f"mrst-confirmation--{plan_record['plan_id']}",
        evaluation_stage="final",
        project_life_years=bank.metadata.project_life_years,
        periods=periods,
        supply=pipeline_raw_supply(
            plan.pipeline,
            periods,
            bank.metadata.project_life_years,
            allocation_fraction=allocation,
        ),
        facility=facility_for_well(
            facility_well,
            periods,
            bank.metadata.project_life_years,
        ),
        uncertainty=uncertainty_from_prediction(
            mrst_prediction,
            periods,
            orchestrator.economic_basis,
        ),
        provenance=[produced.provenance],
    )
    batch = orchestrator.services.economic_evaluator(
        EconomicBatchRequest(
            portfolios=[portfolio],
            carbon_prices=bank.metadata.carbon_prices,
            fiscal_cases=bank.metadata.fiscal_cases,
            assumptions=bank.metadata.economic_assumptions,
            provenance=basis_provenance(orchestrator.economic_basis),
        )
    )
    result = next(
        item
        for item in batch.results
        if item.portfolio_id == portfolio.portfolio_id
        and item.carbon_price_scenario_id == price_id
        and item.fiscal_case_id == "pre_tax"
    )
    return float(result.npv_usd)


def topk_rows(
    *,
    workspace: Path,
    arm_c: dict[str, Any],
    top5_manifest: Any,
    orchestrator: ScreeningOrchestrator,
) -> list[TopKConfirmationRow]:
    plans = json.loads(
        (workspace / "top5_plans.json").read_text(encoding="utf-8")
    )
    dwsim_payload = json.loads(
        (workspace / "dwsim_confirmation.json").read_text(encoding="utf-8")
    )
    dwsim = {
        row["plan_id"]: DwsimConfirmationRow.model_validate(row)
        for row in dwsim_payload["rows"]
    }
    entries = {
        entry.slot_id: entry
        for entry in top5_manifest.entries
        if entry.status == "accepted"
    }
    screen_result = ScreenResult.model_validate(arm_c["screen_result"])
    preset_dir = (
        REPO_ROOT / "data" / "screening_presets" / FULL_PRESET_ID
    )
    manifest = json.loads(
        (preset_dir / "manifest.json").read_text(encoding="utf-8")
    )
    bank = CompactPresetBank(preset_dir / manifest["payload_file"])
    rows = []
    try:
        for plan in sorted(plans, key=lambda item: int(item["rank"])):
            entry = entries[str(plan["plan_id"])]
            prediction = prediction_result_from_mrst(
                _entry_path(TOP5_MANIFEST, entry),
                scenario_id=str(plan["scenario_id"]),
            )
            mrst_value = _top5_mrst_value(
                plan_record=plan,
                mrst_prediction=prediction,
                screen_result=screen_result,
                orchestrator=orchestrator,
                bank=bank,
            )
            surrogate_value = float(plan["surrogate_value"])
            relative = (surrogate_value - mrst_value) / max(
                abs(mrst_value),
                1.0,
            )
            confirmation = dwsim.get(str(plan["plan_id"]))
            rows.append(
                TopKConfirmationRow(
                    plan_id=str(plan["plan_id"]),
                    designated_carbon_price_scenario_id=str(
                        plan["designated_carbon_price_scenario_id"]
                    ),
                    carbon_price_usd_per_tonne=float(
                        plan["carbon_price_usd_per_tonne"]
                    ),
                    fiscal_case="pre_tax",
                    surrogate_value=surrogate_value,
                    mrst_value=mrst_value,
                    relative_error=relative,
                    absolute_relative_error=abs(relative),
                    throughput_class=(
                        confirmation.throughput_class
                        if confirmation is not None
                        else None
                    ),
                    dwsim_converged=(
                        confirmation.converged
                        if confirmation is not None
                        else None
                    ),
                    dwsim_total_power_kw=(
                        confirmation.total_power_kw
                        if confirmation is not None
                        else None
                    ),
                    dwsim_cooling_duty_kw=(
                        confirmation.cooling_duty_kw
                        if confirmation is not None
                        else None
                    ),
                    dwsim_mass_balance_residual_fraction=(
                        confirmation.mass_balance_residual_fraction
                        if confirmation is not None
                        else None
                    ),
                    source_class="mrst_truth_and_surrogate_prediction",
                )
            )
    finally:
        bank.close()
    if len(rows) != 5 or sum(row.dwsim_converged is True for row in rows) != 3:
        raise ValueError("top-five confirmation must contain five MRST and three DWSIM rows")
    return rows


def aggregate_experiment(
    *,
    workspace: Path = DEFAULT_WORKSPACE,
    orchestrator: ScreeningOrchestrator | None = None,
) -> dict[str, Any]:
    arm_c_audit = json.loads(
        (workspace / "arm_c_screening.json").read_text(encoding="utf-8")
    )
    arm_c_internal = json.loads(
        (workspace / "arm_c_internal.json").read_text(encoding="utf-8")
    )
    if canonical_sha256(arm_c_internal["screen_result"]) != str(
        arm_c_audit.get("screen_result_summary", {}).get(
            "result_sha256",
            "",
        )
    ).upper():
        raise ValueError("Arm C internal screen result does not match its audit hash")
    if canonical_sha256(arm_c_internal["field_scenario"]) != str(
        arm_c_audit.get("field_scenario_summary", {}).get(
            "result_sha256",
            "",
        )
    ).upper():
        raise ValueError(
            "Arm C internal field-scenario result does not match its audit hash"
        )
    arm_c = {
        **arm_c_audit,
        "screen_result": arm_c_internal["screen_result"],
        "field_scenario": arm_c_internal["field_scenario"],
    }
    arm_ab = json.loads(
        (workspace / "arm_ab_results.json").read_text(encoding="utf-8")
    )
    manifests = verify_all_mrst_manifests(workspace=workspace)
    if orchestrator is None:
        orchestrator = build_default_orchestrator(load_surrogate())
    economics = [
        *economics_rows_from_screen_result("A", arm_ab["arm_a"]),
        *economics_rows_from_screen_result("B", arm_ab["arm_b"]),
        *economics_rows_from_field_scenarios(arm_c),
    ]
    runtime = runtime_rows(arm_c, manifests)
    confirmations = topk_rows(
        workspace=workspace,
        arm_c=arm_c,
        top5_manifest=manifests["top5"],
        orchestrator=orchestrator,
    )
    atomic_write_csv(
        workspace / "abc_economics.csv",
        economics,
        model=AbcEconomicsRow,
    )
    atomic_write_csv(
        workspace / "abc_runtime.csv",
        runtime,
        model=AbcRuntimeRow,
    )
    atomic_write_csv(
        workspace / "topk_confirmation.csv",
        confirmations,
        model=TopKConfirmationRow,
    )
    payload = {
        "schema_version": "feature007-abc-aggregate-v1",
        "status": "complete",
        "economics_rows": len(economics),
        "runtime_rows": len(runtime),
        "topk_rows": len(confirmations),
        "artifacts": {
            name: {
                "sha256": sha256_file(workspace / name),
            }
            for name in (
                "abc_economics.csv",
                "abc_runtime.csv",
                "topk_confirmation.csv",
            )
        },
        "mechanical_validation": "PASS",
        "scientific_promotion": "PENDING_BUNDLE_REVIEW",
    }
    atomic_write_json(workspace / "aggregate_manifest.json", payload)
    return payload
