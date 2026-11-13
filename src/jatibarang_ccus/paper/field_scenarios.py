"""Field-scenario correlation bracket for Feature 007 Arm C.

The surrogate rollout bank is evaluated once upstream.  This module only maps
those cached realization/schedule results onto physical wells and orchestrates
the downstream MILP plus economics re-solves for each assignment x carbon-price
cell.  It deliberately has no surrogate runner dependency.
"""

from __future__ import annotations

import hashlib
import math
import statistics
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Literal, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator


AssignmentMode = Literal["independent_limit", "correlated_limit"]


def _stable_order(seed: int, *parts: str) -> int:
    payload = "|".join((str(seed), *parts)).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest(), "big")


class FieldScenarioAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignment_id: str = Field(min_length=1)
    mode: AssignmentMode
    well_to_realization: dict[str, str] = Field(min_length=1)
    replicate_index: int = Field(ge=1)
    seed: int
    shared_realization_id: str | None = None

    @model_validator(mode="after")
    def _mode_contract(self) -> "FieldScenarioAssignment":
        assigned = list(self.well_to_realization.values())
        if self.mode == "independent_limit":
            if len(set(assigned)) != len(assigned):
                raise ValueError("independent assignments must be bijective")
            if self.shared_realization_id is not None:
                raise ValueError("independent assignments cannot name a shared realization")
        else:
            if self.shared_realization_id is None:
                raise ValueError("correlated assignments require a shared realization")
            if set(assigned) != {self.shared_realization_id}:
                raise ValueError("correlated assignments must stamp one realization at every well")
        return self


class FieldScenarioDesign(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed: int
    well_ids: list[str] = Field(min_length=1)
    realization_ids: list[str] = Field(min_length=1)
    independent: list[FieldScenarioAssignment] = Field(min_length=1)
    correlated: list[FieldScenarioAssignment] = Field(min_length=1)


def build_field_scenario_design(
    well_ids: Sequence[str],
    realization_ids: Sequence[str],
    *,
    independent_count: int = 20,
    seed: int = 20260717,
) -> FieldScenarioDesign:
    """Build the locked independent and fully correlated assignment ensembles."""

    wells = sorted(well_ids)
    realizations = sorted(realization_ids)
    if not wells or len(wells) != len(set(wells)):
        raise ValueError("well IDs must be non-empty and unique")
    if len(realizations) != len(set(realizations)):
        raise ValueError("realization IDs must be unique")
    if len(wells) != len(realizations):
        raise ValueError("the independent limit requires equal well and realization counts")
    if independent_count < 1:
        raise ValueError("independent_count must be positive")

    independent: list[FieldScenarioAssignment] = []
    seen: set[tuple[str, ...]] = set()
    nonce = 0
    while len(independent) < independent_count:
        replicate = len(independent) + 1
        ordered = sorted(
            realizations,
            key=lambda realization: _stable_order(
                seed,
                "independent",
                str(replicate),
                str(nonce),
                realization,
            ),
        )
        signature = tuple(ordered)
        nonce += 1
        if signature in seen:
            if nonce > independent_count * 1000:
                raise ValueError("could not construct enough unique independent assignments")
            continue
        seen.add(signature)
        independent.append(
            FieldScenarioAssignment(
                assignment_id=f"independent-{replicate:02d}",
                mode="independent_limit",
                well_to_realization=dict(zip(wells, ordered, strict=True)),
                replicate_index=replicate,
                seed=seed,
            )
        )

    correlated = [
        FieldScenarioAssignment(
            assignment_id=f"correlated-{index:02d}",
            mode="correlated_limit",
            well_to_realization={well: realization for well in wells},
            replicate_index=index,
            seed=seed,
            shared_realization_id=realization,
        )
        for index, realization in enumerate(realizations, start=1)
    ]
    return FieldScenarioDesign(
        seed=seed,
        well_ids=wells,
        realization_ids=realizations,
        independent=independent,
        correlated=correlated,
    )


@dataclass(frozen=True)
class FieldScenarioResolveContext:
    """One downstream re-solve cell backed by references into one rollout cache."""

    assignment: FieldScenarioAssignment
    carbon_price_scenario_id: str
    rollouts_by_well: Mapping[str, Any]


class FieldScenarioSolveRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignment_id: str
    mode: AssignmentMode
    replicate_index: int
    shared_realization_id: str | None = None
    carbon_price_scenario_id: str
    well_to_realization: dict[str, str]
    result: dict[str, Any]


class FieldScenarioExperimentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed: int
    rollout_cache_entries: int = Field(ge=1)
    surrogate_evaluations_during_resolve: Literal[0] = 0
    downstream_resolve_count: int = Field(ge=1)
    independent: list[FieldScenarioSolveRecord]
    correlated: list[FieldScenarioSolveRecord]
    distribution_summary: dict[str, Any]
    provenance: dict[str, Any]


ResolveFieldScenario = Callable[[FieldScenarioResolveContext], Mapping[str, Any]]


def _quantile(sorted_values: list[float], probability: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = probability * (len(sorted_values) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    fraction = position - lower
    return sorted_values[lower] + fraction * (
        sorted_values[upper] - sorted_values[lower]
    )


def _numeric_distribution(
    records: Sequence[FieldScenarioSolveRecord],
    key: str,
) -> dict[str, float | int] | None:
    values = sorted(
        float(value)
        for record in records
        if (value := record.result.get(key)) is not None
        and not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )
    if not values:
        return None
    return {
        "count": len(values),
        "minimum": values[0],
        "p10": _quantile(values, 0.10),
        "median": statistics.median(values),
        "mean": statistics.fmean(values),
        "p90": _quantile(values, 0.90),
        "maximum": values[-1],
    }


def summarize_field_scenario_distributions(
    independent: Sequence[FieldScenarioSolveRecord],
    correlated: Sequence[FieldScenarioSolveRecord],
) -> dict[str, Any]:
    """Summarize declared headline metrics without manufacturing missing regret."""

    output: dict[str, Any] = {}
    for mode, records in (
        ("independent_limit", independent),
        ("correlated_limit", correlated),
    ):
        by_price: dict[str, Any] = {}
        price_ids = sorted({record.carbon_price_scenario_id for record in records})
        for price_id in price_ids:
            cells = [
                record
                for record in records
                if record.carbon_price_scenario_id == price_id
            ]
            metrics = {
                "portfolio_npv_usd": _numeric_distribution(
                    cells, "portfolio_npv_usd"
                ),
                "break_even_carbon_price_usd_per_tonne": _numeric_distribution(
                    cells, "break_even_carbon_price_usd_per_tonne"
                ),
                "regret_usd": _numeric_distribution(cells, "regret_usd"),
            }
            pivot_values = [
                bool(record.result["pivot_observed_within_assignment"])
                for record in cells
                if record.result.get("pivot_observed_within_assignment") is not None
            ]
            by_price[price_id] = {
                **{key: value for key, value in metrics.items() if value is not None},
                **(
                    {
                        "pivot_probability": sum(pivot_values) / len(pivot_values),
                        "pivot_assignment_count": sum(pivot_values),
                        "assignment_count": len(pivot_values),
                    }
                    if pivot_values
                    else {}
                ),
            }
        output[mode] = {"by_carbon_price": by_price}
    return output


def run_field_scenario_resolves(
    design: FieldScenarioDesign,
    carbon_price_scenario_ids: Sequence[str],
    rollout_cache: Mapping[str, Any],
    resolver: ResolveFieldScenario,
    *,
    existing_records: Sequence[FieldScenarioSolveRecord] = (),
    on_record: Callable[[FieldScenarioSolveRecord], None] | None = None,
) -> FieldScenarioExperimentResult:
    """Run only downstream re-solves, grouped by assignment and carbon price.

    ``rollout_cache`` is realization-keyed; each value can itself contain the
    162 schedule rollouts.  Values are passed by reference through read-only
    mappings, so this layer cannot silently manufacture or recompute a rollout.
    """

    prices = list(carbon_price_scenario_ids)
    if not prices or len(prices) != len(set(prices)):
        raise ValueError("carbon-price scenario IDs must be non-empty and unique")
    missing = sorted(set(design.realization_ids) - set(rollout_cache))
    if missing:
        raise ValueError(f"rollout cache is missing realizations: {missing}")
    cache = MappingProxyType(dict(rollout_cache))
    assignments = {
        (assignment.mode, assignment.assignment_id): assignment
        for assignment in [*design.independent, *design.correlated]
    }
    expected_keys = {
        (mode, assignment_id, price_id)
        for mode, assignment_id in assignments
        for price_id in prices
    }
    existing_by_key: dict[
        tuple[AssignmentMode, str, str],
        FieldScenarioSolveRecord,
    ] = {}
    for raw_record in existing_records:
        record = FieldScenarioSolveRecord.model_validate(raw_record)
        key = (
            record.mode,
            record.assignment_id,
            record.carbon_price_scenario_id,
        )
        if key not in expected_keys:
            raise ValueError(f"field-scenario checkpoint has unexpected cell: {key}")
        assignment = assignments[(record.mode, record.assignment_id)]
        if (
            record.replicate_index != assignment.replicate_index
            or record.shared_realization_id != assignment.shared_realization_id
            or record.well_to_realization != assignment.well_to_realization
        ):
            raise ValueError(
                f"field-scenario checkpoint assignment mismatch: {key}"
            )
        if key in existing_by_key:
            raise ValueError(f"field-scenario checkpoint has duplicate cell: {key}")
        existing_by_key[key] = record

    def solve(assignment: FieldScenarioAssignment, price_id: str) -> FieldScenarioSolveRecord:
        key = (assignment.mode, assignment.assignment_id, price_id)
        if key in existing_by_key:
            return existing_by_key[key]
        by_well = MappingProxyType(
            {
                well: cache[realization]
                for well, realization in sorted(assignment.well_to_realization.items())
            }
        )
        result = dict(
            resolver(
                FieldScenarioResolveContext(
                    assignment=assignment,
                    carbon_price_scenario_id=price_id,
                    rollouts_by_well=by_well,
                )
            )
        )
        record = FieldScenarioSolveRecord(
            assignment_id=assignment.assignment_id,
            mode=assignment.mode,
            replicate_index=assignment.replicate_index,
            shared_realization_id=assignment.shared_realization_id,
            carbon_price_scenario_id=price_id,
            well_to_realization=dict(assignment.well_to_realization),
            result=result,
        )
        existing_by_key[key] = record
        if on_record is not None:
            on_record(record)
        return record

    independent = [
        solve(assignment, price_id)
        for assignment in design.independent
        for price_id in prices
    ]
    correlated = [
        solve(assignment, price_id)
        for assignment in design.correlated
        for price_id in prices
    ]
    return FieldScenarioExperimentResult(
        seed=design.seed,
        rollout_cache_entries=len(cache),
        downstream_resolve_count=len(independent) + len(correlated),
        independent=independent,
        correlated=correlated,
        distribution_summary=summarize_field_scenario_distributions(
            independent,
            correlated,
        ),
        provenance={
            "method": "field_scenario_correlation_bracket",
            "independent_limit": "seeded_bijective_well_realization_assignments",
            "correlated_limit": "one_shared_realization_stamped_at_all_wells",
            "grouping": "assignment_x_carbon_price",
            "rollout_policy": "reuse_cache_no_surrogate_calls",
            "regret_policy": "summarize_resolver_supplied_cross_scenario_regret_only",
            "named_well_single_assignment_claim": False,
        },
    )


class CachedOrchestratorFieldScenarioResolver:
    """Bind assignment ensembles to the Feature 005 cache-only re-solve path.

    ``run_field_scenario_resolves`` asks for one record per assignment x price.
    The screening orchestrator naturally resolves every declared carbon price
    together, so this adapter memoizes one downstream run per assignment and
    projects the requested price cell on subsequent calls.
    """

    def __init__(
        self,
        orchestrator: Any,
        base_request: Any,
        realization_to_candidate_id: Mapping[str, str],
        *,
        prediction_cache: Mapping[str, Any] | None = None,
    ) -> None:
        from ..screening.schemas import InlineScreenRequest, PresetScreenRequest

        self.orchestrator = orchestrator
        mode = (
            base_request.get("mode")
            if isinstance(base_request, Mapping)
            else getattr(base_request, "mode", None)
        )
        self._preset_mode = mode == "preset"
        request_type = PresetScreenRequest if self._preset_mode else InlineScreenRequest
        self.base_request = request_type.model_validate(base_request).model_copy(
            update={"detailed_top_k": 0}
        )
        self.realization_to_candidate_id = dict(realization_to_candidate_id)
        self.prediction_cache = prediction_cache
        if not self._preset_mode:
            candidates = {
                item.candidate_id for item in self.base_request.candidates
            }
            missing = sorted(
                set(self.realization_to_candidate_id.values()) - candidates
            )
            if missing:
                raise ValueError(
                    f"realization templates reference unknown candidates: {missing}"
                )
        self._results: dict[str, Any] = {}

    def result_for_assignment(self, assignment_id: str) -> Any:
        try:
            return self._results[assignment_id]
        except KeyError as exc:
            raise KeyError(
                f"assignment has not been resolved: {assignment_id}"
            ) from exc

    def _assigned_request(self, assignment: FieldScenarioAssignment) -> Any:
        if self._preset_mode:
            return self.base_request.model_copy(
                update={
                    "run_id": f"feature007-{assignment.assignment_id}",
                    "detailed_top_k": 0,
                }
            )
        templates = {
            item.candidate_id: item for item in self.base_request.candidates
        }
        candidates = []
        for physical in self.base_request.candidates:
            realization = assignment.well_to_realization.get(physical.candidate_id)
            if realization is None:
                raise ValueError(
                    f"assignment {assignment.assignment_id} omits {physical.candidate_id}"
                )
            template_id = self.realization_to_candidate_id.get(realization)
            if template_id is None:
                raise ValueError(f"no request template is mapped for realization {realization}")
            template = templates[template_id]
            candidates.append(
                physical.model_copy(
                    update={
                        "geology_id": template.geology_id,
                        "seed_by_schedule_fingerprint": dict(
                            template.seed_by_schedule_fingerprint
                        ),
                    }
                )
            )
        return self.base_request.model_copy(
            update={
                "run_id": f"feature007-{assignment.assignment_id}",
                "candidates": candidates,
                "detailed_top_k": 0,
            }
        )

    @staticmethod
    def _merge_prediction_cache(
        rollouts_by_well: Mapping[str, Any],
    ) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for well, realization_cache in sorted(rollouts_by_well.items()):
            if not isinstance(realization_cache, Mapping):
                raise TypeError(f"rollout cache for {well} must be fingerprint-keyed")
            for fingerprint, prediction in realization_cache.items():
                prior = merged.get(fingerprint)
                if prior is not None and prior is not prediction and prior != prediction:
                    raise ValueError(
                        f"conflicting cached prediction for fingerprint {fingerprint}"
                    )
                merged[fingerprint] = prediction
        return merged

    def __call__(self, context: FieldScenarioResolveContext) -> Mapping[str, Any]:
        assignment_id = context.assignment.assignment_id
        if assignment_id not in self._results:
            request = self._assigned_request(context.assignment)
            cache = (
                self.prediction_cache
                if self.prediction_cache is not None
                else self._merge_prediction_cache(context.rollouts_by_well)
            )
            if self._preset_mode:
                candidate_realization_map = {
                    physical: self.realization_to_candidate_id[realization]
                    for physical, realization in (
                        context.assignment.well_to_realization.items()
                    )
                }
                self._results[assignment_id] = (
                    self.orchestrator.run_preset_with_prediction_cache(
                        request,
                        cache,
                        candidate_realization_map=candidate_realization_map,
                    )
                )
            else:
                self._results[assignment_id] = (
                    self.orchestrator.run_with_prediction_cache(
                        request,
                        cache,
                    )
                )
        result = self._results[assignment_id]
        plan = next(
            (
                item
                for item in result.plans
                if item.carbon_price_scenario_id == context.carbon_price_scenario_id
            ),
            None,
        )
        if plan is None:
            raise ValueError(
                f"assignment result has no carbon-price plan {context.carbon_price_scenario_id}"
            )
        aggregate = None
        if plan.economics is not None:
            aggregate = next(
                (
                    item
                    for item in plan.economics.results
                    if item.portfolio_id
                    == f"portfolio--{context.carbon_price_scenario_id}"
                    and item.carbon_price_scenario_id
                    == context.carbon_price_scenario_id
                    and item.fiscal_case_id
                    == self.base_request.selection_fiscal_case_id
                ),
                None,
            )
        npv_by_price: dict[str, float] = {}
        npv_low_by_price: dict[str, float] = {}
        npv_high_by_price: dict[str, float] = {}
        if plan.economics is not None:
            for item in plan.economics.results:
                if (
                    item.portfolio_id
                    == f"portfolio--{context.carbon_price_scenario_id}"
                    and item.fiscal_case_id
                    == self.base_request.selection_fiscal_case_id
                ):
                    npv_by_price[item.carbon_price_scenario_id] = item.npv_usd
                    npv_low_by_price[item.carbon_price_scenario_id] = (
                        item.npv_low_usd
                    )
                    npv_high_by_price[item.carbon_price_scenario_id] = (
                        item.npv_high_usd
                    )
        oracle_by_price: dict[str, float] = {}
        for oracle_plan in result.plans:
            if oracle_plan.economics is None:
                continue
            realized_price = oracle_plan.carbon_price_scenario_id
            oracle = next(
                (
                    item
                    for item in oracle_plan.economics.results
                    if item.portfolio_id
                    == f"portfolio--{realized_price}"
                    and item.carbon_price_scenario_id == realized_price
                    and item.fiscal_case_id
                    == self.base_request.selection_fiscal_case_id
                ),
                None,
            )
            if oracle is not None:
                oracle_by_price[realized_price] = oracle.npv_usd
        regret_by_price = {
            realized_price: max(
                0.0,
                oracle_npv - npv_by_price[realized_price],
            )
            for realized_price, oracle_npv in oracle_by_price.items()
            if realized_price in npv_by_price
        }
        return {
            "run_id": result.run_id,
            "downstream_total_seconds": float(
                getattr(getattr(result, "timings", None), "total_seconds", 0.0)
            ),
            "domain_status": plan.domain_status,
            "audit_reason": str(
                getattr(
                    plan.pipeline,
                    "hydraulic_verification",
                    {},
                ).get("reason")
                or getattr(
                    plan.pipeline,
                    "constraint_audit",
                    {},
                ).get("reason")
                or plan.domain_status
            ),
            "selected_wells": list(plan.selected_wells),
            "portfolio_signature": "|".join(sorted(plan.selected_wells)),
            "selected_scenario_ids": sorted(
                strategy.scenario_id
                for strategy in getattr(plan, "well_strategies", [])
                if strategy.selected
            ),
            "pipeline_objective_usd": plan.pipeline.objective_value_usd,
            "portfolio_npv_usd": aggregate.npv_usd if aggregate is not None else None,
            "portfolio_npv_low_usd": (
                aggregate.npv_low_usd if aggregate is not None else None
            ),
            "portfolio_npv_high_usd": (
                aggregate.npv_high_usd if aggregate is not None else None
            ),
            "npv_by_carbon_price_usd": npv_by_price,
            "npv_low_by_carbon_price_usd": npv_low_by_price,
            "npv_high_by_carbon_price_usd": npv_high_by_price,
            "regret_by_realized_price_usd": regret_by_price,
            "regret_usd": (
                statistics.fmean(regret_by_price.values())
                if regret_by_price
                else None
            ),
            "break_even_carbon_price_usd_per_tonne": (
                aggregate.break_even_carbon_price.value
                if aggregate is not None
                else None
            ),
            "irr": aggregate.irr.value if aggregate is not None else None,
            "payback_years": (
                aggregate.discounted_payback.value
                if aggregate is not None
                else None
            ),
            "break_even_oil_usd_per_bbl": (
                aggregate.break_even_oil_price.value
                if aggregate is not None
                else None
            ),
            "pivot_observed_within_assignment": result.cross_price_comparison.pivot_observed,
            "surrogate_evaluations_during_resolve": 0,
        }


def assignment_rows(design: FieldScenarioDesign) -> list[dict[str, Any]]:
    """Flatten the design for the Feature 007 bundle's auditable CSV table."""

    rows: list[dict[str, Any]] = []
    for assignment in [*design.independent, *design.correlated]:
        for well, realization in sorted(assignment.well_to_realization.items()):
            rows.append(
                {
                    "assignment_id": assignment.assignment_id,
                    "mode": assignment.mode,
                    "replicate_index": assignment.replicate_index,
                    "seed": assignment.seed,
                    "shared_realization_id": assignment.shared_realization_id or "",
                    "well_id": well,
                    "realization_id": realization,
                }
            )
    return rows
