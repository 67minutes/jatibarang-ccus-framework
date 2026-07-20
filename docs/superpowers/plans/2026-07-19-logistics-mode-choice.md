# Logistics Mode-Choice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the Feature 002 MILP into a pipeline-vs-trucking mode-choice logistics optimizer so pilot-scale screening produces honest trucking-supplied development plans, add truthful zero-selection provenance, and generate the throughput crossover table for Figure 5(c).

**Architecture:** The Pyomo model gains per-well `p` (pipeline-served) and `t` (trucked) binaries with `z == p + t`; flow balances move from `z` to `p`; a per-well trucking lifecycle term joins the objective. The orchestrator injects per-candidate road distances into the demands and treats trucking-inclusive selections as accepted development (facility, economics, memo, UI). A standalone crossover module sweeps annual throughput across trucking / pipeline-direct / hybrid modes.

**Tech Stack:** FastAPI + pydantic v2 + Pyomo/CBC + networkx/shapely (existing, no new deps); React + zustand + vitest; pytest.

**Spec:** `docs/superpowers/specs/2026-07-19-logistics-mode-choice-design.md`

## Global Constraints

- Do NOT change `min_velocity_m_s`, the diameter catalog, pressure anchors, or any hydraulic assumption. The 1 m/s dense-phase floor stays at 1.0.
- No MRST regeneration, no surrogate retraining; all schedules stay inside `TRAINED_RANGES`.
- `STUDY_MEMO_VERSION` stays **4**; every new memo/API field is optional/additive.
- Trucking provenance strings verbatim: `osm_road_network:<road_network_id>` with roads; `greatcircle_detour_estimate` without. UI copy never says "graph", "PBF", or "OSM extract".
- New Inspector copy verbatim: `Supplied by road transport from the source.`
- Path-taking import routes keep `_require_local_client(request)`; do not touch the loopback guard.
- Back-compat invariant: any `PipelineDesignRequest` whose demands carry no `trucking_distance_km` must solve bit-identically to today (trucking binaries fixed to 0). Feature 002's tracked rational-zero validation case must still return `no_viable_network`.
- Do NOT stage `pipeline_cost_crossover.csv` into `paper/validation/feature007/`; the crossover CLI writes to `output/crossover/` only. Bundle staging happens during the paper execution run.
- After every backend task: `python -m pytest tests -q` → PASS. After every frontend task: `cd frontend && npm test -- --run && npx tsc -b` → PASS.
- Work on branch `008-blank-slate-workbench`; commit after every task with adds scoped to the files the task touched.

---

### Task 1: Contracts — additive mode-choice fields

**Files:**
- Modify: `src/jatibarang_ccus/contracts.py` (`PipelineWellDemand` ~line 49, `WellSelectionDecision` ~line 186, `PipelineDesignResult` ~line 218)
- Test: `tests/infrastructure/test_pipeline_network.py` (append)

**Interfaces:**
- Produces: `PipelineWellDemand.trucking_distance_km: float | None` (default `None`); `WellSelectionDecision.supply_mode: Literal["pipeline","trucking"] | None` (default `None`) and reason literal `"hydraulically_unreachable"`; `PipelineDesignResult.supply_mode_by_well: dict[str, Literal["pipeline","trucking"]]` (default `{}`) and `PipelineDesignResult.trucking_lifecycle_cost_usd: float` (default `0.0`). Tasks 3–6 rely on these exact names.

- [ ] **Step 1: Write the failing test** (append to `tests/infrastructure/test_pipeline_network.py`):

```python
def test_mode_choice_contract_defaults() -> None:
    well = _well("W1", 0.01)
    assert well.trucking_distance_km is None
    trucked = well.model_copy(update={"trucking_distance_km": 78.0})
    assert trucked.trucking_distance_km == 78.0
    decision = WellSelectionDecision(candidate_id="W1", selected=False, reason="hydraulically_unreachable")
    assert decision.supply_mode is None
```

Add `WellSelectionDecision` to the existing `jatibarang_ccus.contracts` import in this file.

- [ ] **Step 2: Run to verify failure** — `python -m pytest tests/infrastructure/test_pipeline_network.py::test_mode_choice_contract_defaults -q` → FAIL (unknown field / invalid literal).

- [ ] **Step 3: Implement.** In `contracts.py`:

```python
class PipelineWellDemand(BaseModel):
    candidate_id: str = Field(min_length=1)
    location: Coordinate
    annual_demand_tonnes: float = Field(gt=0)
    peak_mass_flow_kg_s: float = Field(gt=0)
    pre_logistics_value_usd: float
    influence_radius_m: float = Field(default=500.0, gt=0)
    mandatory: bool = False
    trucking_distance_km: float | None = Field(default=None, gt=0)
    provenance: dict[str, Any] = Field(default_factory=dict)
```

```python
class WellSelectionDecision(BaseModel):
    candidate_id: str
    selected: bool
    reason: Literal[
        "selected",
        "negative_net_value",
        "annual_budget",
        "source_capacity",
        "peak_deliverability",
        "network_cost",
        "mandatory",
        "infeasible",
        "hydraulically_unreachable",
    ]
    supply_mode: Literal["pipeline", "trucking"] | None = None
```

In `PipelineDesignResult`, add two fields (place next to `selected_wells`):

```python
    supply_mode_by_well: dict[str, Literal["pipeline", "trucking"]] = Field(default_factory=dict)
    trucking_lifecycle_cost_usd: float = 0.0
```

- [ ] **Step 4: Run tests** — `python -m pytest tests -q` → PASS (defaults keep every existing constructor valid).
- [ ] **Step 5: Commit** — `git add src/jatibarang_ccus/contracts.py tests/infrastructure/test_pipeline_network.py && git commit -m "feat(contracts): additive mode-choice fields for logistics MILP"`

---

### Task 2: Trucking logistics cost helper

**Files:**
- Modify: `src/jatibarang_ccus/infrastructure/costs.py`
- Test: `tests/infrastructure/test_costs.py` if it exists (locate with `ls tests/infrastructure/`), else append to `tests/infrastructure/test_pipeline_network.py`

**Interfaces:**
- Produces: `trucking_logistics_usd_per_tonne(case: dict[str, Any], distance_km: float) -> float` — per-tonne trucking logistics **excluding** the CO₂ commodity supply price. Tasks 3, 5, 8 call it with the same `case` dict shape used by `pipe_capex_usd` (a `basis["cases"][name]` mapping).

- [ ] **Step 1: Write the failing test:**

```python
from jatibarang_ccus.infrastructure.costs import load_cost_basis, trucking_logistics_usd_per_tonne


def test_trucking_logistics_cost_composition() -> None:
    basis = load_cost_basis("data/jatibarang/pipeline_cost_basis.json")
    case = basis["cases"]["base"]
    at_10 = trucking_logistics_usd_per_tonne(case, 10.0)
    at_80 = trucking_logistics_usd_per_tonne(case, 80.0)
    fixed = (
        float(case["trucking_loading_usd_per_tonne"])
        + float(case["trucking_liquefaction_usd_per_tonne"])
        + float(case["trucking_reconditioning_usd_per_tonne"])
    )
    assert at_10 == fixed + float(case["trucking_usd_per_tonne_km"]) * 10.0
    assert at_80 > at_10
```

- [ ] **Step 2: Run to verify failure** — `python -m pytest tests/infrastructure -q -k trucking_logistics` → FAIL (import error).

- [ ] **Step 3: Implement** in `costs.py` (next to `pipe_capex_usd`, ~line 41):

```python
def trucking_logistics_usd_per_tonne(case: dict[str, Any], distance_km: float) -> float:
    """Per-tonne trucking logistics (loading + liquefaction + reconditioning +
    distance transport), excluding the CO2 commodity supply price."""
    return (
        float(case["trucking_loading_usd_per_tonne"])
        + float(case["trucking_liquefaction_usd_per_tonne"])
        + float(case["trucking_reconditioning_usd_per_tonne"])
        + float(case["trucking_usd_per_tonne_km"]) * float(distance_km)
    )
```

Refactor `_trucking_result` in `infrastructure/supply.py` (lines 18–23) to call this helper instead of re-deriving the four components, keeping `delivered = trucking_logistics_usd_per_tonne(case, request.trucking_distance_km) + supply` and preserving the four per-component result fields (compute them from the same `case` values as today).

- [ ] **Step 4: Run** — `python -m pytest tests -q` → PASS.
- [ ] **Step 5: Commit** — `git add src/jatibarang_ccus/infrastructure/costs.py src/jatibarang_ccus/infrastructure/supply.py tests/infrastructure && git commit -m "feat(costs): shared trucking logistics per-tonne helper"`

---

### Task 3: MILP mode-choice core

**Files:**
- Modify: `src/jatibarang_ccus/infrastructure/pipeline.py` (variables ~line 453, balances ~lines 524–543, objective ~lines 632–646, selection extraction ~line 676)
- Test: `tests/infrastructure/test_pipeline_network.py` (append)

**Interfaces:**
- Consumes: Task 1 fields; Task 2 helper.
- Produces: solved model exposes `selected` (z), `pipeline_served` (p), `trucked` (t) well lists and `trucking_cost_by_well: dict[str, float]` inside `solve_pipeline_design`; Task 5 consumes these locals for result assembly.

- [ ] **Step 1: Write the failing tests** (append; `_well` gains a pass-through kwarg):

```python
def _trucked_well(well_id: str, lon: float, *, peak: float, annual: float, value: float, km: float) -> PipelineWellDemand:
    return _well(well_id, lon, value=value).model_copy(
        update={"peak_mass_flow_kg_s": peak, "annual_demand_tonnes": annual, "trucking_distance_km": km}
    )


def test_pilot_scale_well_is_selected_via_trucking() -> None:
    source = _source("S1", 0.0)
    well = _trucked_well("W1", 0.63, peak=0.195, annual=1_516.0, value=16_200_000.0, km=78.0)
    library = RouteLibrary(
        nodes=[
            RouteNode(id="S1", kind="source", location=source.location, elevation_m=0.0),
            RouteNode(id="W1", kind="well", location=well.location, elevation_m=0.0),
        ],
        segments=[_segment("E1", "S1", "W1", 0.0, 0.63)],
        fingerprint="TRUCK",
        provenance={"terrain_sha256": "TEST"},
    )
    result = solve_pipeline_design(
        PipelineDesignRequest(
            sources=[source],
            well_demands=[well],
            route_library=library,
            annual_co2_budget_tonnes=320_000.0,
            assumptions=_assumptions(),
            objective_mode="max_net_value",
        )
    )
    assert result.domain_status == "accepted"
    assert result.selected_wells == ["W1"]
    assert result.supply_mode_by_well == {"W1": "trucking"}
    assert not result.built_segments
    assert result.trucking_lifecycle_cost_usd > 0


def test_high_flow_short_route_still_prefers_pipeline() -> None:
    source = _source("S1", 0.0)
    well = _well("W1", 0.01).model_copy(update={"trucking_distance_km": 400.0})
    library = RouteLibrary(
        nodes=[
            RouteNode(id="S1", kind="source", location=source.location, elevation_m=0.0),
            RouteNode(id="W1", kind="well", location=well.location, elevation_m=0.0),
        ],
        segments=[_segment("E1", "S1", "W1", 0.0, 0.01)],
        fingerprint="PIPE",
        provenance={"terrain_sha256": "TEST"},
    )
    result = solve_pipeline_design(
        PipelineDesignRequest(
            sources=[source],
            well_demands=[well],
            route_library=library,
            annual_co2_budget_tonnes=100_000.0,
            assumptions=_assumptions(),
            objective_mode="max_net_value",
        )
    )
    assert result.domain_status == "accepted"
    assert result.supply_mode_by_well == {"W1": "pipeline"}
    assert result.built_segments
```

- [ ] **Step 2: Run to verify failure** — `python -m pytest tests/infrastructure/test_pipeline_network.py -q -k "trucking or prefers_pipeline"` → FAIL.

- [ ] **Step 3: Implement.** In `solve_pipeline_design`:

(a) Import the helper — extend the existing `from .costs import ...` (or `from jatibarang_ccus.infrastructure.costs import ...`) line with `trucking_logistics_usd_per_tonne`.

(b) After `model.z = pyo.Var(model.W, domain=pyo.Binary)` (line 453):

```python
    model.p = pyo.Var(model.W, domain=pyo.Binary)
    model.t = pyo.Var(model.W, domain=pyo.Binary)
    model.mode_split = pyo.Constraint(model.W, rule=lambda m, well: m.z[well] == m.p[well] + m.t[well])
    for item in request.well_demands:
        if item.trucking_distance_km is None:
            model.t[item.candidate_id].fix(0)
```

(c) In `peak_balance` (line 530) change `demand_by_id[node].peak_mass_flow_kg_s * m.z[node]` to `... * m.p[node]`; in `annual_balance` (line 539) change `demand_by_id[node].annual_demand_tonnes * m.z[node]` to `... * m.p[node]`. The `annual_budget` constraint and mandatory `z` fixing stay on `z`.

(d) Immediately before the objective (line 640), using the in-scope `cost_case` dict and `pv_factor`:

```python
    trucking_cost_by_well = {
        item.candidate_id: trucking_logistics_usd_per_tonne(cost_case, item.trucking_distance_km)
        * item.annual_demand_tonnes
        * pv_factor
        for item in request.well_demands
        if item.trucking_distance_km is not None
    }
    trucking_expr = sum(cost * model.t[well_id] for well_id, cost in trucking_cost_by_well.items())
```

Objective becomes `... - network_lifecycle_expr - commodity_expr - trucking_expr` (maximize) and `network_lifecycle_expr + commodity_expr + trucking_expr` (minimize branch at line 646).

(e) Selection extraction (line 676) becomes:

```python
    selected = [well for well in model.W if pyo.value(model.z[well]) >= 0.5]
    trucked = [well for well in model.W if pyo.value(model.t[well]) >= 0.5]
    pipeline_served = [well for well in selected if well not in trucked]
```

Downstream code that iterated `selected` to trace built arcs must use `pipeline_served` for network tracing while economics-facing outputs keep `selected` (Task 5 finishes this; for this task make the two tests pass and keep every existing test green — the empty-selection early-return at line 677 still keys on `selected`).

- [ ] **Step 4: Run** — `python -m pytest tests/infrastructure/test_pipeline_network.py -q` → PASS, then `python -m pytest tests -q` → PASS.
- [ ] **Step 5: Commit** — `git add src/jatibarang_ccus/infrastructure/pipeline.py tests/infrastructure/test_pipeline_network.py && git commit -m "feat(milp): joint pipeline-vs-trucking mode choice per well"`

---

### Task 4: Honest zero-selection provenance

**Files:**
- Modify: `src/jatibarang_ccus/infrastructure/pipeline.py` (zero-selection branch ~line 677, `well_decisions` assembly ~line 892)
- Test: `tests/infrastructure/test_pipeline_network.py` (append)

**Interfaces:**
- Produces: `constraint_audit.reason == "below_minimum_hydraulic_flow"` when the velocity floor (not economics) forces the zero; per-well decision reason `"hydraulically_unreachable"`. The screening validation CSVs and paper text rely on these exact strings.

- [ ] **Step 1: Failing test:**

```python
def test_velocity_floor_zero_reports_hydraulic_reason() -> None:
    source = _source("S1", 0.0)
    well = _well("W1", 0.63, value=16_200_000.0).model_copy(
        update={"peak_mass_flow_kg_s": 0.195, "annual_demand_tonnes": 1_516.0}
    )
    library = RouteLibrary(
        nodes=[
            RouteNode(id="S1", kind="source", location=source.location, elevation_m=0.0),
            RouteNode(id="W1", kind="well", location=well.location, elevation_m=0.0),
        ],
        segments=[_segment("E1", "S1", "W1", 0.0, 0.63)],
        fingerprint="FLOOR",
        provenance={"terrain_sha256": "TEST"},
    )
    result = solve_pipeline_design(
        PipelineDesignRequest(
            sources=[source],
            well_demands=[well],
            route_library=library,
            annual_co2_budget_tonnes=320_000.0,
            assumptions=_assumptions(),
            objective_mode="max_net_value",
        )
    )
    assert result.domain_status == "no_viable_network"
    assert result.constraint_audit["reason"] == "below_minimum_hydraulic_flow"
    assert result.well_decisions[0].reason == "hydraulically_unreachable"


def test_negative_value_zero_keeps_economic_reason() -> None:
    result = solve_pipeline_design(_request(value=-1_000_000.0))
    assert result.domain_status == "no_viable_network"
    assert result.constraint_audit["reason"] == "all_wells_negative_after_logistics"
```

- [ ] **Step 2: Run to verify failure** — `python -m pytest tests/infrastructure/test_pipeline_network.py -q -k "floor or economic_reason"` → FAIL.

- [ ] **Step 3: Implement.** Before the zero-selection early return, compute per-well reachability from the already-built `hydraulics` and `directed_arcs`:

```python
    def _min_admissible_inflow_kg_s(well_id: str) -> float:
        incident = [arc for arc in directed_arcs if arc[2] == well_id]
        if not incident:
            return float("inf")
        return min(
            hydraulics[(arc[0], arc[1], arc[2])].diameters[float(arc[3])].minimum_flow_kg_s
            for arc in incident
        )

    hydraulically_unreachable = {
        well_id: demand_by_id[well_id].peak_mass_flow_kg_s < _min_admissible_inflow_kg_s(well_id)
        for well_id in demand_by_id
    }
```

In the `if not selected:` branch, choose the audit reason:

```python
        zero_reason = (
            "below_minimum_hydraulic_flow"
            if hydraulically_unreachable and all(hydraulically_unreachable.values())
            else "all_wells_negative_after_logistics"
        )
```

and pass `reason=zero_reason` to `_empty_result`. In the `well_decisions` assembly (both the empty branch inside `_empty_result` callers and the accepted-path assembly at ~line 892), unselected wells report `"hydraulically_unreachable"` when `hydraulically_unreachable[well_id]` is true and the well had no trucking option, else the existing `"negative_net_value"` / `"network_cost"` logic. Note: `_empty_result` itself builds generic decisions; set the refined decisions on the returned object in the zero-selection branch (`empty.well_decisions = [...]`), mirroring how `objective_value_usd` is already patched there (line 679).

- [ ] **Step 4: Run** — `python -m pytest tests -q` → PASS. Feature 002's validation expectation (rational zero) is unaffected because its case is economic (`all_wells_negative_after_logistics` requires at least one reachable well); if `tests` include the validation bundle test, confirm it still passes.
- [ ] **Step 5: Commit** — `git add src/jatibarang_ccus/infrastructure/pipeline.py tests/infrastructure/test_pipeline_network.py && git commit -m "feat(milp): distinguish hydraulic-floor zeros from economic zeros"`

---

### Task 5: Result assembly for trucked wells

**Files:**
- Modify: `src/jatibarang_ccus/infrastructure/pipeline.py` (post-solve assembly, ~lines 684–948)
- Test: `tests/infrastructure/test_pipeline_network.py` (extend `test_pilot_scale_well_is_selected_via_trucking`)

**Interfaces:**
- Consumes: Task 3 locals (`selected`, `pipeline_served`, `trucked`, `trucking_cost_by_well`).
- Produces: `PipelineDesignResult.supply_mode_by_well`, `trucking_lifecycle_cost_usd`, allocations and delivered costs covering trucked wells; hydraulic verification passes vacuously with zero built segments. Task 6 consumes the result unchanged.

- [ ] **Step 1: Extend the failing test** (append assertions to `test_pilot_scale_well_is_selected_via_trucking`):

```python
    assert result.per_well_allocated_cost_usd["W1"] == pytest.approx(result.trucking_lifecycle_cost_usd)
    assert result.delivered_cost_usd_per_tonne["W1"] > result.costs.commodity_supply_usd_per_tonne
    assert result.hydraulic_verification["passed"] is True
    assert result.well_decisions[0].supply_mode == "trucking"
```

Add `import pytest` at the top of the file if missing.

- [ ] **Step 2: Run to verify failure** — `python -m pytest tests/infrastructure/test_pipeline_network.py -q -k pilot_scale` → FAIL.

- [ ] **Step 3: Implement.** Read the assembly section first (lines 684–948) and make these changes, matching surrounding style:

(a) Network tracing, built-segment construction, booster extraction, and the PWL-vs-continuous verification loop iterate only pipeline-served flow; with `pipeline_served == []` they no-op and `hydraulic_verification` reports `{"passed": True, "reason": "no_built_segments", "refinement_attempts": 0}`.

(b) After pipeline allocations are computed (allocation loop ending ~line 850), add trucked wells:

```python
    for well_id in trucked:
        allocations[well_id] = trucking_cost_by_well[well_id]
```

Keep the `allocation_relative_residual` check (lines 850–854) computed over pipeline-served wells only — trucked allocations are not pipeline transport.

(c) Delivered cost per well (~line 838): pipeline-served wells keep the existing formula; trucked wells use:

```python
    supply_usd = float(cost_case["co2_supply_usd_per_tonne"])
    delivered[well_id] = supply_usd + trucking_cost_by_well[well_id] / max(
        demand_by_id[well_id].annual_demand_tonnes * pv_factor, 1e-9
    )
```

(d) Result construction gains:

```python
        supply_mode_by_well={well_id: ("trucking" if well_id in trucked else "pipeline") for well_id in selected},
        trucking_lifecycle_cost_usd=sum(trucking_cost_by_well[w] for w in trucked),
```

(e) `well_decisions` (~line 892): selected wells carry `supply_mode="trucking" if item.candidate_id in trucked else "pipeline"`; unselected wells carry `supply_mode=None`.

- [ ] **Step 4: Run** — `python -m pytest tests -q` → PASS.
- [ ] **Step 5: Commit** — `git add src/jatibarang_ccus/infrastructure/pipeline.py tests/infrastructure/test_pipeline_network.py && git commit -m "feat(milp): trucked wells carry allocations, delivered cost, and mode provenance"`

---

### Task 6: Orchestrator — trucking-inclusive development plans

**Files:**
- Modify: `src/jatibarang_ccus/screening/schemas.py` (`CarbonPricePlan` ~line 261)
- Modify: `src/jatibarang_ccus/screening/orchestrator.py` (route stage ~line 969, demand build ~line 1003, plan branch ~line 1039, plan assembly ~line 1393)
- Test: `tests/screening/test_orchestration_integration.py` (append; extend the `pipeline_result` fixture ~line 93)

**Interfaces:**
- Consumes: Tasks 1–5 result fields.
- Produces: `CarbonPricePlan.logistics_mode: Literal["pipeline","trucking","hybrid","none"]` (default `"none"`); accepted trucking plans flow through facility + economics; `trucking_route_preview` also populated for accepted plans' trucked wells; info flag `pipeline_hydraulically_inadmissible`. Tasks 7 and 9 rely on the field names.

- [ ] **Step 1: Failing test** (append; reuse the file's stub-services pattern):

```python
def test_trucking_selection_is_development(monkeypatch) -> None:
    request = inline_request()
    # Follow this file's existing orchestrator-construction pattern (see the
    # neighboring tests): build ScreeningServices with route_builder=route_library
    # and pipeline_solver stubbed as below, then run the orchestrator to completion.
    def trucking_solver(design_request):
        result = pipeline_result(design_request, selected=["W01", "W02"])
        return result.model_copy(
            update={
                "supply_mode_by_well": {"W01": "trucking", "W02": "trucking"},
                "trucking_lifecycle_cost_usd": 500_000.0,
                "per_well_allocated_cost_usd": {"W01": 250_000.0, "W02": 250_000.0},
                "built_segments": [],
            }
        )
    # ... run screening with pipeline_solver=trucking_solver ...
    plan = result.plans[0]
    assert plan.logistics_mode == "trucking"
    assert plan.selected_wells == ["W01", "W02"]
    assert plan.economics is not None
    assert plan.facility is not None
    assert plan.trucking_route_preview is not None and len(plan.trucking_route_preview.legs) == 2
    assert not any(flag.code == "no_viable_network" for flag in plan.flags)
    assert any(flag.code == "pipeline_hydraulically_inadmissible" for flag in plan.flags)
```

Replace the two `# ...` comments with this file's actual harness calls (copy the invocation from the nearest existing test that runs a full screen with stubbed services — same fixtures, different `pipeline_solver`).

- [ ] **Step 2: Run to verify failure** — `python -m pytest tests/screening/test_orchestration_integration.py -q -k trucking_selection` → FAIL.

- [ ] **Step 3: Implement.**

(a) `schemas.py` — `CarbonPricePlan` gains:

```python
    logistics_mode: Literal["pipeline", "trucking", "hybrid", "none"] = "none"
```

(add `Literal` to the imports if absent).

(b) `orchestrator.py`, after `route_library = ...` (line 975), compute per-candidate road distances once per run:

```python
        _, trucking_distance_provenance, road_distance_legs = compute_trucking_legs(
            request.sources,
            routing_demands,
            road_graph,
        )
        trucking_km_by_candidate = {leg.candidate_id: leg.distance_km for leg in road_distance_legs}
```

(c) In the per-carbon demand build (after the loop ending line 1018):

```python
            demands = [
                item.model_copy(update={"trucking_distance_km": trucking_km_by_candidate.get(item.candidate_id)})
                for item in demands
            ]
```

(d) The plan branch keeps `selected = list(pipeline.selected_wells) if pipeline.domain_status == "accepted" else []`. In the accepted path, derive the mode and preview:

```python
                trucked_ids = [w for w in selected if pipeline.supply_mode_by_well.get(w) == "trucking"]
                if trucked_ids:
                    flags.append(
                        ScreenFlag(
                            code="pipeline_hydraulically_inadmissible",
                            severity="info",
                            source_module="feature002",
                            message="Pipeline supply is below the minimum admissible hydraulic flow; selected wells are supplied by road transport.",
                        )
                    )
                    _, preview_provenance, preview_legs = compute_trucking_legs(
                        design_request.sources,
                        [d for d in demands if d.candidate_id in trucked_ids],
                        road_graph,
                    )
                    trucking_route_preview = TruckingRoutePreview(
                        distance_provenance=preview_provenance,
                        legs=preview_legs,
                    )
```

(If `ScreenFlag.severity` has no `"info"` literal, extend that literal additively in `schemas.py` in this task.)

(e) Plan assembly (line 1393) gains:

```python
                    logistics_mode=(
                        "none"
                        if not selected
                        else (
                            "hybrid"
                            if 0 < len([w for w in selected if pipeline.supply_mode_by_well.get(w) == "trucking"]) < len(selected)
                            else ("trucking" if pipeline.supply_mode_by_well.get(selected[0]) == "trucking" else "pipeline")
                        )
                    ),
```

(f) Extend the integration fixture `pipeline_result` with a `supply_mode_by_well` passthrough so existing tests stay valid (default `{}` → wells read as pipeline).

- [ ] **Step 4: Run** — `python -m pytest tests -q` → PASS.
- [ ] **Step 5: Commit** — `git add src/jatibarang_ccus/screening tests/screening/test_orchestration_integration.py && git commit -m "feat(screening): trucking-supplied selections are development plans"`

---

### Task 7: API/memo plumbing and contract test

**Files:**
- Modify: `specs/005-screening-api/contracts/openapi.yaml` (CarbonPricePlan schema — additive `logistics_mode`; PipelineDesignResult — additive `supply_mode_by_well`, `trucking_lifecycle_cost_usd`)
- Test: `tests/screening/test_schemas_presets.py` (append)

**Interfaces:**
- Produces: serialized plan JSON carries `logistics_mode` and the pipeline result carries `supply_mode_by_well`; the study memo (v4) picks these up automatically because it embeds the result payload.

- [ ] **Step 1: Failing test:**

```python
def test_plan_serializes_logistics_mode() -> None:
    from jatibarang_ccus.screening.schemas import CarbonPricePlan
    fields = CarbonPricePlan.model_fields
    assert "logistics_mode" in fields
    assert fields["logistics_mode"].default == "none"
```

- [ ] **Step 2: Run to verify failure only if Task 6 skipped** — with Task 6 landed this passes immediately; keep it as a regression pin. Run `python -m pytest tests/screening/test_schemas_presets.py -q` → PASS.
- [ ] **Step 3: Update `openapi.yaml`** — add to the CarbonPricePlan component: `logistics_mode: {type: string, enum: [pipeline, trucking, hybrid, none], default: none}`; add to PipelineDesignResult: `supply_mode_by_well: {type: object, additionalProperties: {type: string, enum: [pipeline, trucking]}}` and `trucking_lifecycle_cost_usd: {type: number, default: 0}`. Follow the file's existing schema style.
- [ ] **Step 4: Run the contract test** — `python -m pytest tests -q` → PASS (the API contract test validates responses against the YAML; additive fields with defaults must not break it).
- [ ] **Step 5: Commit** — `git add specs/005-screening-api/contracts/openapi.yaml tests/screening/test_schemas_presets.py && git commit -m "feat(api): expose logistics mode in screening contract"`

---

### Task 8: Crossover sweep module + CLI

**Files:**
- Create: `src/jatibarang_ccus/infrastructure/crossover.py`
- Test: `tests/infrastructure/test_crossover.py`

**Interfaces:**
- Consumes: `load_cost_basis`, `pipe_capex_usd`, `annuity_present_value_factor`, `trucking_logistics_usd_per_tonne` from `costs.py`; `_diameter_flow_kg_s` from `hydraulics.py`; `load_assumptions(DEFAULT_ASSUMPTIONS)`.
- Produces: `crossover_table(...) -> list[dict]` and a `main()` CLI writing `output/crossover/pipeline_cost_crossover.csv`. Figure 5(c) consumes the CSV at paper time (staging out of scope).

- [ ] **Step 1: Failing test:**

```python
from jatibarang_ccus.infrastructure.crossover import crossover_table


def test_crossover_modes_and_admissibility() -> None:
    rows = crossover_table(
        annual_tonnes_grid=[30_000.0, 1_000_000.0],
        trunk_km=68.0,
        lastmile_km=5.0,
        full_route_km=78.0,
        per_well_annual_tonnes=1_516.0,
        cost_case="base",
    )
    by_key = {(row["annual_tonnes"], row["mode"]): row for row in rows}
    pilot_truck = by_key[(30_000.0, "trucking")]
    pilot_pipe = by_key[(30_000.0, "pipeline_direct")]
    pilot_hybrid = by_key[(30_000.0, "hybrid_trunk_truck")]
    assert pilot_truck["hydraulically_admissible"] is True
    assert pilot_pipe["hydraulically_admissible"] is False
    assert pilot_hybrid["hydraulically_admissible"] is False
    assert pilot_truck["levelized_usd_per_tonne"] < pilot_hybrid["levelized_usd_per_tonne"]
    scale_hybrid = by_key[(1_000_000.0, "hybrid_trunk_truck")]
    scale_truck = by_key[(1_000_000.0, "trucking")]
    assert scale_hybrid["hydraulically_admissible"] is True
    assert scale_hybrid["levelized_usd_per_tonne"] < scale_truck["levelized_usd_per_tonne"]
    assert by_key[(1_000_000.0, "pipeline_direct")]["hydraulically_admissible"] is False
```

- [ ] **Step 2: Run to verify failure** — `python -m pytest tests/infrastructure/test_crossover.py -q` → FAIL (module missing).

- [ ] **Step 3: Implement `crossover.py`:**

```python
"""Throughput crossover for CO2 supply modes (Figure 5c input).

Pure cost-basis arithmetic: no MRST, no surrogate, no scenario bank. Booster
costs are deliberately excluded (screening lower bound that favors pipelines,
so a trucking-wins conclusion is conservative). Commodity supply is excluded
from every mode (pure transport comparison on the levelized_transport basis).
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from jatibarang_ccus.infrastructure.costs import (
    annuity_present_value_factor,
    load_cost_basis,
    pipe_capex_usd,
    trucking_logistics_usd_per_tonne,
)
from jatibarang_ccus.infrastructure.hydraulics import _diameter_flow_kg_s
from jatibarang_ccus.phase1.case_study import DEFAULT_ASSUMPTIONS, load_assumptions

SECONDS_PER_YEAR = 365.0 * 86_400.0


def _diameter_flow_window_kg_s(pipe: dict, diameter_in: float) -> tuple[float, float]:
    anchors = [float(v) for v in pipe["pressure_anchors_bar"]]
    temperature = float(pipe["ground_temperature_c"])
    minimum = max(
        _diameter_flow_kg_s(diameter_in=diameter_in, pressure_bar=a, temperature_c=temperature,
                            velocity_m_s=float(pipe["min_velocity_m_s"]))
        for a in anchors
    )
    maximum = min(
        _diameter_flow_kg_s(diameter_in=diameter_in, pressure_bar=a, temperature_c=temperature,
                            velocity_m_s=float(pipe["max_velocity_m_s"]))
        for a in anchors
    )
    return minimum, maximum


def _cheapest_admissible_diameter(pipe: dict, flow_kg_s: float) -> float | None:
    admissible = []
    for entry in pipe["pipe_diameters"]:
        diameter = float(entry["diameter_in"])
        low, high = _diameter_flow_window_kg_s(pipe, diameter)
        if low <= flow_kg_s <= high:
            admissible.append(diameter)
    return min(admissible) if admissible else None


def _trunk_levelized_usd_per_tonne(pipe: dict, case: dict, trunk_km: float,
                                   annual_tonnes: float, pv_factor: float,
                                   diameter_in: float) -> float:
    capex = pipe_capex_usd(diameter_in=diameter_in, length_km=trunk_km, case=case)
    lifecycle = capex * (1.0 + float(case["pipeline_maintenance_fraction"]) * pv_factor)
    return lifecycle / (annual_tonnes * pv_factor)


def crossover_table(
    *,
    annual_tonnes_grid: list[float],
    trunk_km: float,
    lastmile_km: float,
    full_route_km: float,
    per_well_annual_tonnes: float,
    cost_case: str,
) -> list[dict]:
    assumptions = load_assumptions(DEFAULT_ASSUMPTIONS)
    pipe = assumptions["pipeline"]
    basis = load_cost_basis(pipe["cost_basis_path"])
    case = basis["cases"][cost_case]
    economics = assumptions["economics"]
    pv_factor = annuity_present_value_factor(
        float(economics["discount_rate"]), int(economics["project_life_years"])
    )
    fallback_diameter = min(float(entry["diameter_in"]) for entry in pipe["pipe_diameters"])
    rows: list[dict] = []
    for annual_tonnes in annual_tonnes_grid:
        trunk_flow = annual_tonnes * 1_000.0 / SECONDS_PER_YEAR
        per_well_flow = per_well_annual_tonnes * 1_000.0 / SECONDS_PER_YEAR
        trunk_diameter = _cheapest_admissible_diameter(pipe, trunk_flow)
        lateral_diameter = _cheapest_admissible_diameter(pipe, per_well_flow)
        rows.append({
            "annual_tonnes": annual_tonnes,
            "mode": "trucking",
            "levelized_usd_per_tonne": trucking_logistics_usd_per_tonne(case, full_route_km),
            "hydraulically_admissible": True,
            "diameter_in": None,
        })
        pipe_diameter = trunk_diameter if trunk_diameter is not None else fallback_diameter
        rows.append({
            "annual_tonnes": annual_tonnes,
            "mode": "pipeline_direct",
            "levelized_usd_per_tonne": _trunk_levelized_usd_per_tonne(
                pipe, case, trunk_km, annual_tonnes, pv_factor, pipe_diameter
            ),
            "hydraulically_admissible": trunk_diameter is not None and lateral_diameter is not None,
            "diameter_in": pipe_diameter,
        })
        rows.append({
            "annual_tonnes": annual_tonnes,
            "mode": "hybrid_trunk_truck",
            "levelized_usd_per_tonne": _trunk_levelized_usd_per_tonne(
                pipe, case, trunk_km, annual_tonnes, pv_factor, pipe_diameter
            )
            + trucking_logistics_usd_per_tonne(case, lastmile_km),
            "hydraulically_admissible": trunk_diameter is not None,
            "diameter_in": pipe_diameter,
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="output/crossover/pipeline_cost_crossover.csv")
    parser.add_argument("--trunk-km", type=float, default=68.0)
    parser.add_argument("--lastmile-km", type=float, default=5.0)
    parser.add_argument("--full-route-km", type=float, default=78.0)
    parser.add_argument("--per-well-annual-tonnes", type=float, default=1_516.0)
    parser.add_argument("--cost-case", default="base", choices=["low", "base", "high"])
    args = parser.parse_args()
    grid = [10_000.0 * (10 ** (i / 8.0)) for i in range(0, 17)]  # 10 kt/yr -> 1 Mt/yr, log-spaced
    rows = crossover_table(
        annual_tonnes_grid=grid,
        trunk_km=args.trunk_km,
        lastmile_km=args.lastmile_km,
        full_route_km=args.full_route_km,
        per_well_annual_tonnes=args.per_well_annual_tonnes,
        cost_case=args.cost_case,
    )
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} rows -> {target}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run** — `python -m pytest tests/infrastructure/test_crossover.py -q` → PASS; smoke the CLI: `python -m jatibarang_ccus.infrastructure.crossover` → CSV written under `output/crossover/`.
- [ ] **Step 5: Commit** — `git add src/jatibarang_ccus/infrastructure/crossover.py tests/infrastructure/test_crossover.py && git commit -m "feat(crossover): trucking/pipeline/hybrid throughput sweep for fig 5c"`

---

### Task 9: Frontend — mode provenance and trucked development routes

**Files:**
- Modify: `frontend/src/api/types.ts` (plan + pipeline result additive fields)
- Modify: `frontend/src/viewport/scene.ts` (trucking-route arm, ~lines 113–130)
- Modify: `frontend/src/layout/Inspector.tsx` (trucking provenance line — locate with `grep -n "great-circle" frontend/src/layout/Inspector.tsx`)
- Test: `frontend/src/viewport/scene.test.ts` (append)

**Interfaces:**
- Consumes: Task 6/7 fields (`logistics_mode`, `supply_mode_by_well`).
- Produces: dashed trucking routes render for trucked wells on **accepted** plans; Inspector shows the verbatim line `Supplied by road transport from the source.` for trucking-mode development plans.

- [ ] **Step 1: Failing scene test** — append a case: an accepted plan (`domain_status: "accepted"`, `selected_wells: ["W02"]`, `logistics_mode: "trucking"`, `supply_mode_by_well: {W02: "trucking"}`) with `trucking_route_preview.legs = [{candidate_id: "W02", distance_km: 78, annual_mass_tonnes: 1516, route: [[-6.5, 107.0], [-6.4, 107.1], [-6.5, 107.2]]}]` produces a `SceneRoute` with `mode: "trucking"` and a 3-point path for W02. Copy the shape of the existing "plan without network" trucking test in this file and change only the acceptance fields.

- [ ] **Step 2: Run to verify failure** — `cd frontend && npm test -- --run src/viewport/scene.test.ts` → FAIL (accepted plans currently draw pipeline routes only).

- [ ] **Step 3: Implement.**

(a) `types.ts`: add `logistics_mode?: "pipeline" | "trucking" | "hybrid" | "none"` to the plan type and `supply_mode_by_well?: Record<string, "pipeline" | "trucking">` to the pipeline result type (verify exact type names with `grep -n "trucking_route_preview" frontend/src/api/types.ts` and place the fields beside it).

(b) `scene.ts`: in the route-building branch, wells whose `plan.pipeline.supply_mode_by_well?.[wellId] === "trucking"` take the trucking-leg path (same leg-lookup code as the `networkAccepted === false` arm) even when the network is accepted; pipeline-served wells keep pipeline routes.

(c) `Inspector.tsx`: where the trucking provenance line renders, add the accepted-trucking case rendering exactly `Supplied by road transport from the source.` (keep the existing two lines for preview/fallback provenance unchanged and verbatim).

- [ ] **Step 4: Run** — `cd frontend && npm test -- --run && npx tsc -b` → PASS.
- [ ] **Step 5: Commit** — `git add frontend/src && git commit -m "feat(frontend): trucked development routes and supply-mode provenance"`

---

### Task 10: Final verification, docs, and QA re-run

**Files:**
- Modify: `ABSTRACT_STATE_TO_FULL_PAPER_IMPLEMENTATION_GAP.md` (executive verdict + Feature 002/005 rows: note the mode-choice logistics MILP and honest hydraulic-floor provenance)
- Modify: `docs/superpowers/specs/2026-07-19-logistics-mode-choice-design.md` (append an implementation record section with dates and any deviations)

**Steps:**

- [ ] **Step 1: Full verification** — `python -m pytest tests -q` → PASS; `cd frontend && npm test -- --run && npx tsc -b && npm run build` → PASS.
- [ ] **Step 2: End-to-end QA** — start the app, open the saved 20-well study (`output/playwright/jatibarang-20well-final.study.json`), run a screen, and verify: all four carbon-price plans report `logistics_mode: "trucking"` with 20 selected wells, positive economics, the `pipeline_hydraulically_inadmissible` info flag, road-following dashed routes, and the Inspector line `Supplied by road transport from the source.` Record whether plan composition or best schedules differ across the four carbon prices (the pivot check for vault Move 6) — report the observation either way; never tune assumptions to force it.
- [ ] **Step 3: Docs** — update the gap audit rows and append the spec's implementation record.
- [ ] **Step 4: Commit** — `git add -A && git commit -m "docs: logistics mode-choice implementation record and gap-audit update"`

---

## Self-Review Notes

- **Spec coverage:** §3 MILP formulation → Tasks 1–5; §3 honest reasons → Task 4; §4 orchestrator → Task 6; §4 memo/API → Task 7; §5 crossover → Task 8; §6 frontend → Task 9; §7 verification + pivot observation → per-task + Task 10; §2 non-goals encoded as Global Constraints (no hydraulic changes, no bundle staging, no hub node type).
- **Deliberate judgment points:** the integration-test harness invocation (Task 6 Step 1 — copy the neighboring test's construction), the post-solve assembly section internals (Task 5 Step 3 instructs reading lines 684–948 first), the `types.ts` type names and scene key path (Task 9 — named greps). Each is a bounded look-and-match instruction.
- **Type consistency:** `trucking_distance_km` / `supply_mode_by_well` / `trucking_lifecycle_cost_usd` / `logistics_mode` / `hydraulically_unreachable` / `below_minimum_hydraulic_flow` / `pipeline_hydraulically_inadmissible` are used with identical spelling across Tasks 1, 3–9. `trucking_logistics_usd_per_tonne(case, distance_km)` signature matches Tasks 2, 3, 5, 8.
- **Back-compat pins:** Task 3 keeps `t` fixed at 0 without distances (legacy tests bit-identical); Task 4's economic-zero test pins the rational-zero validation contract; Task 6 extends the integration fixture with a default that preserves existing tests.
