from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any

import networkx as nx
import numpy as np
import pyomo.environ as pyo
from pyomo.opt import SolverStatus, TerminationCondition

from jatibarang_ccus.contracts import (
    BoosterStation,
    BuiltSegment,
    CandidateWell,
    CO2Source,
    NetworkCostBreakdown,
    PipelineDesignRequest,
    PipelineDesignResult,
    PipelineWellDemand,
    RouteLibraryRequest,
    RouteSegment,
    ScreenedWellValue,
    WellSelectionDecision,
)
from jatibarang_ccus.infrastructure.costs import (
    annuity_present_value_factor,
    booster_capex_usd,
    build_cost_breakdown,
    load_cost_basis,
    pipe_capex_usd,
    trucking_logistics_usd_per_tonne,
)
from jatibarang_ccus.infrastructure.hydraulics import (
    SegmentHydraulics,
    booster_power_kw,
    integrate_route_profile,
    precompute_hydraulics,
)
from jatibarang_ccus.infrastructure.thermo import mass_flow_kg_s_from_m3_day


_HYDRAULIC_CACHE: dict[str, dict[tuple[str, str, str], SegmentHydraulics]] = {}


def adapt_legacy_pipeline_inputs(
    *,
    source: CO2Source,
    candidates: list[CandidateWell],
    well_values: list[ScreenedWellValue],
    assumptions: dict[str, Any],
) -> tuple[list[CO2Source], list[PipelineWellDemand]]:
    """Translate the temporary Phase 1 proxy payload into the Feature 002 boundary."""

    values = {item.candidate_id: item for item in well_values}
    pipeline = assumptions["pipeline"]
    economics = assumptions["economics"]
    demands: list[PipelineWellDemand] = []
    for index, candidate in enumerate(candidates):
        value = values.get(candidate.id)
        if value is None:
            annual_mass = 20_000.0 + 500.0 * index
            peak_flow = 80.0
            project_value = 2_000_000.0
            provenance = {"source_class": "test_or_route_only_default"}
        else:
            # The Phase 1 proxy stores campaign/cycle tonnes, not tonnes/year.
            # Annualize over the configured project horizon while retaining the
            # peak injection rate independently for pipe sizing.
            annual_mass = max(
                float(value.injected_co2_tonnes) / float(economics["project_life_years"]),
                1.0,
            )
            rate = float(value.parameters.get("injection_rate_m3_day", 9_000.0))
            peak_flow = mass_flow_kg_s_from_m3_day(
                rate,
                float(pipeline["reference_pressure_bar"]),
                float(pipeline["ground_temperature_c"]),
            )
            project_value = float(value.preliminary_npv_usd) + annual_mass * float(economics["delivered_co2_cost_usd_per_tonne"])
            provenance = {
                "source_class": "legacy_phase1_proxy_adapter",
                "replacement_feature": "005",
                "annualization": "campaign_injected_tonnes_divided_by_project_life_years",
                "peak_sizing_basis": "injection_rate_m3_day_at_reference_dense_phase_state",
            }
        demands.append(
            PipelineWellDemand(
                candidate_id=candidate.id,
                location=candidate.location,
                annual_demand_tonnes=annual_mass,
                peak_mass_flow_kg_s=peak_flow,
                pre_logistics_value_usd=project_value,
                influence_radius_m=candidate.influence_radius_m,
                provenance=provenance,
            )
        )
    return [source], demands


def assert_solver_available(solver: str = "cbc") -> None:
    factory = pyo.SolverFactory(solver)
    if not factory.available(False):
        raise EnvironmentError(
            f"MILP solver '{solver}' is not available. Install CBC and make cbc.exe visible on PATH, "
            "or explicitly configure an available Pyomo MILP solver."
        )


def _reverse_segment(segment: RouteSegment) -> RouteSegment:
    return segment.model_copy(
        update={
            "id": f"{segment.id}__REVERSE",
            "from_node": segment.to_node,
            "to_node": segment.from_node,
            "geometry": list(reversed(segment.geometry)),
            "elevation_m": list(reversed(segment.elevation_m)),
            "min_slope": -segment.max_slope,
            "max_slope": -segment.min_slope,
        }
    )


def _directed_hydraulics(
    segments: dict[str, RouteSegment], assumptions: dict[str, Any]
) -> dict[tuple[str, str, str], SegmentHydraulics]:
    cache_payload = {
        "segments": [segments[key].model_dump(mode="json") for key in sorted(segments)],
        "assumptions": assumptions,
    }
    cache_key = hashlib.sha256(
        json.dumps(cache_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if cache_key in _HYDRAULIC_CACHE:
        return _HYDRAULIC_CACHE[cache_key]
    forward = precompute_hydraulics(segments=list(segments.values()), assumptions=assumptions)
    reversed_segments = [_reverse_segment(segment) for segment in segments.values()]
    reverse = precompute_hydraulics(segments=reversed_segments, assumptions=assumptions)
    result: dict[tuple[str, str, str], SegmentHydraulics] = {}
    for edge_id, segment in segments.items():
        result[(edge_id, segment.from_node, segment.to_node)] = forward[edge_id]
        result[(edge_id, segment.to_node, segment.from_node)] = reverse[f"{edge_id}__REVERSE"]
    _HYDRAULIC_CACHE[cache_key] = result
    return result


def _numeric(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _empty_costs(request: PipelineDesignRequest, cost_basis: dict[str, Any]) -> NetworkCostBreakdown:
    economics = request.assumptions["economics"]
    return build_cost_breakdown(
        cost_basis=cost_basis,
        cost_case=request.cost_case,
        pipeline_capex_usd_value=0.0,
        booster_capex_usd_value=0.0,
        annual_booster_energy_usd=0.0,
        annual_mass_tonnes=0.0,
        discount_rate=float(economics["discount_rate"]),
        project_life_years=int(economics["project_life_years"]),
    )


def _request_provenance(request: PipelineDesignRequest) -> dict[str, Any]:
    assumptions_fingerprint = hashlib.sha256(
        json.dumps(request.assumptions, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest().upper()
    return {
        **request.route_library.provenance,
        "route_library_fingerprint": request.route_library.fingerprint,
        "assumptions_fingerprint_sha256": assumptions_fingerprint,
        "solver_configuration": {
            "solver": request.solver,
            "time_limit_seconds": request.assumptions.get("pipeline", {}).get("solver_time_limit_seconds"),
            "ratio_gap": request.assumptions.get("pipeline", {}).get("solver_ratio_gap"),
        },
    }


def _empty_result(
    request: PipelineDesignRequest,
    *,
    cost_basis: dict[str, Any],
    domain_status: str,
    solver_status: str,
    termination: str,
    reason: str,
    solve_time: float = 0.0,
) -> PipelineDesignResult:
    costs = _empty_costs(request, cost_basis)
    return PipelineDesignResult(
        domain_status=domain_status,
        solver=request.solver,
        solver_status=solver_status,
        termination_condition=termination,
        objective_mode=request.objective_mode,
        selected_wells=[],
        well_decisions=[WellSelectionDecision(candidate_id=item.candidate_id, selected=False, reason="infeasible" if domain_status == "infeasible" else "negative_net_value") for item in request.well_demands],
        built_segments=[],
        boosters=[],
        node_pressures_bar={},
        source_annual_flows_tonnes={item.id: 0.0 for item in request.sources},
        source_peak_flows_kg_s={item.id: 0.0 for item in request.sources},
        delivered_cost_usd_per_tonne={},
        per_well_allocated_cost_usd={},
        costs=costs,
        constraint_audit={"passed": domain_status == "no_viable_network", "reason": reason},
        hydraulic_verification={"passed": domain_status == "no_viable_network", "reason": reason, "refinement_attempts": 0},
        solve_time_seconds=solve_time,
        route_provenance=_request_provenance(request),
        pipeline_capex_usd=0.0,
        booster_capex_usd=0.0,
        annual_opex_usd=0.0,
        total_network_cost_usd=0.0,
    )


def _constraint_violation(model: pyo.ConcreteModel) -> float:
    maximum = 0.0
    for constraint in model.component_data_objects(pyo.Constraint, active=True):
        body = pyo.value(constraint.body, exception=False)
        if body is None:
            continue
        if constraint.lower is not None:
            maximum = max(maximum, float(pyo.value(constraint.lower)) - float(body))
        if constraint.upper is not None:
            maximum = max(maximum, float(body) - float(pyo.value(constraint.upper)))
    return max(0.0, maximum)


def _mass_balance_relative_residual(model: pyo.ConcreteModel, node_ids: list[str]) -> tuple[float, float]:
    """Return independently scaled peak and annual node-balance residuals.

    CBC's absolute algebraic feasibility tolerance is not a meaningful proxy for
    mass conservation when annual tonnes and peak kg/s share one model.  Audit
    both balance systems explicitly and scale by their respective total source
    throughput.
    """

    peak_scale = max(1.0, sum(abs(float(pyo.value(model.source_peak[source]))) for source in model.S))
    annual_scale = max(1.0, sum(abs(float(pyo.value(model.source_annual[source]))) for source in model.S))
    peak = max((abs(float(pyo.value(model.peak_balance[node].body))) for node in node_ids), default=0.0)
    annual = max((abs(float(pyo.value(model.annual_balance[node].body))) for node in node_ids), default=0.0)
    return peak / peak_scale, annual / annual_scale


def _flow_based_allocations(
    *,
    selected: list[str],
    demands: dict[str, PipelineWellDemand],
    active_rows: list[tuple[str, str, str, float, float]],
    segment_lifecycle_cost: dict[str, float],
    booster_lifecycle_cost: dict[str, float],
) -> dict[str, float]:
    allocation = {well: 0.0 for well in selected}
    graph = nx.DiGraph()
    for edge_id, from_node, to_node, _diameter, _peak in active_rows:
        graph.add_edge(from_node, to_node, edge_id=edge_id)
    for edge_id, _from_node, to_node, _diameter, _peak in active_rows:
        downstream = ({to_node} | nx.descendants(graph, to_node)) & set(selected)
        total = sum(demands[well].annual_demand_tonnes for well in downstream)
        if total > 0:
            for well in downstream:
                allocation[well] += segment_lifecycle_cost[edge_id] * demands[well].annual_demand_tonnes / total
    for node, cost in booster_lifecycle_cost.items():
        downstream = ({node} | nx.descendants(graph, node)) & set(selected)
        total = sum(demands[well].annual_demand_tonnes for well in downstream)
        if total > 0:
            for well in downstream:
                allocation[well] += cost * demands[well].annual_demand_tonnes / total
    return allocation


def _minimum_cost_mandatory_corridor(
    segments: dict[str, RouteSegment],
    *,
    source_ids: set[str],
    mandatory_wells: set[str],
) -> dict[str, RouteSegment]:
    """Keep audited shortest route-library corridors for provably inactive optional wells.

    In minimum-cost mode without a delivery target, optional wells can only add
    positive network and commodity cost, so their selection variables are fixed
    to zero.  Restricting hydraulic disjunctions to the shortest audited
    source-to-mandatory corridors is therefore an exact screening presolve, not
    candidate prefiltering.
    """

    if not mandatory_wells:
        return segments
    graph = nx.Graph()
    for edge_id, segment in segments.items():
        graph.add_edge(
            segment.from_node,
            segment.to_node,
            edge_id=edge_id,
            weight=max(float(segment.route_cost), 1e-9),
        )
    retained: set[str] = set()
    for well in sorted(mandatory_wells):
        candidates: list[tuple[float, list[str]]] = []
        for source in source_ids:
            if nx.has_path(graph, source, well):
                candidates.append(
                    (
                        float(nx.shortest_path_length(graph, source, well, weight="weight")),
                        nx.shortest_path(graph, source, well, weight="weight"),
                    )
                )
        if not candidates:
            raise ValueError(f"No route-library corridor connects a source to mandatory well {well!r}.")
        _cost, path = min(candidates, key=lambda item: (item[0], item[1]))
        for first, second in zip(path, path[1:]):
            retained.add(str(graph.edges[first, second]["edge_id"]))
    return {edge_id: segment for edge_id, segment in segments.items() if edge_id in retained}


def solve_pipeline_design(
    request: PipelineDesignRequest,
    *,
    _refinement_attempt: int = 0,
    _cumulative_solve_time: float = 0.0,
) -> PipelineDesignResult:
    assumptions = request.assumptions["pipeline"]
    economics = request.assumptions["economics"]
    solver_name = request.solver or str(assumptions.get("solver", "cbc"))
    assert_solver_available(solver_name)
    cost_basis = load_cost_basis(assumptions["cost_basis_path"])
    cost_case = cost_basis["cases"][request.cost_case]
    demand_by_id = {item.candidate_id: item for item in request.well_demands}
    source_by_id = {item.id: item for item in request.sources}
    mandatory_annual = sum(item.annual_demand_tonnes for item in request.well_demands if item.mandatory)
    mandatory_peak = sum(item.peak_mass_flow_kg_s for item in request.well_demands if item.mandatory)
    if mandatory_annual > min(request.annual_co2_budget_tonnes, sum(item.capacity_tonnes_per_year for item in request.sources)) + 1e-9 or mandatory_peak > sum(item.max_mass_flow_kg_s for item in request.sources) + 1e-9:
        return _empty_result(
            request,
            cost_basis=cost_basis,
            domain_status="infeasible",
            solver_status="not_run",
            termination="preflight_infeasible",
            reason="mandatory_annual_demand_exceeds_budget_or_capacity",
        )

    all_segments = {item.id: item for item in request.route_library.segments}
    route_node_ids = {item.id for item in request.route_library.nodes}
    missing = (set(demand_by_id) | set(source_by_id)) - route_node_ids
    if missing:
        raise ValueError(f"Route library is missing source/well nodes: {sorted(missing)}")
    mandatory_wells = {item.candidate_id for item in request.well_demands if item.mandatory}
    exact_mandatory_presolve = request.objective_mode == "min_lifecycle_cost" and request.delivery_target_tonnes_per_year is None
    segments = (
        _minimum_cost_mandatory_corridor(
            all_segments,
            source_ids=set(source_by_id),
            mandatory_wells=mandatory_wells,
        )
        if exact_mandatory_presolve
        else all_segments
    )
    node_ids = sorted(
        set(source_by_id)
        | mandatory_wells
        | {segment.from_node for segment in segments.values()}
        | {segment.to_node for segment in segments.values()}
    )
    hydraulics = _directed_hydraulics(segments, assumptions)
    diameters = [float(item["diameter_in"]) for item in assumptions["pipe_diameters"]]
    oriented_corridor = exact_mandatory_presolve and len(source_by_id) == 1
    direction_pairs: dict[str, tuple[tuple[str, str], ...]] = {}
    if oriented_corridor:
        corridor_graph = nx.Graph()
        for edge_id, segment in segments.items():
            corridor_graph.add_edge(
                segment.from_node,
                segment.to_node,
                edge_id=edge_id,
                weight=max(float(segment.route_cost), 1e-9),
            )
        source_id = next(iter(source_by_id))
        distances = nx.single_source_dijkstra_path_length(corridor_graph, source_id, weight="weight")
        for edge_id, segment in segments.items():
            endpoints = sorted(
                (segment.from_node, segment.to_node),
                key=lambda node: (float(distances.get(node, math.inf)), node),
            )
            direction_pairs[edge_id] = ((endpoints[0], endpoints[1]),)
    else:
        direction_pairs = {
            edge_id: ((segment.from_node, segment.to_node), (segment.to_node, segment.from_node))
            for edge_id, segment in segments.items()
        }
    fixed_peak_flow_by_edge: dict[str, float] = {}
    fixed_annual_flow_by_edge: dict[str, float] = {}
    if oriented_corridor:
        for edge_id, ((from_node, to_node),) in direction_pairs.items():
            downstream = {to_node} | nx.descendants(nx.DiGraph([(pair[0], pair[1]) for pairs in direction_pairs.values() for pair in pairs]), to_node)
            fixed_peak_flow_by_edge[edge_id] = sum(
                demand_by_id[well].peak_mass_flow_kg_s for well in mandatory_wells if well in downstream
            )
            fixed_annual_flow_by_edge[edge_id] = sum(
                demand_by_id[well].annual_demand_tonnes for well in mandatory_wells if well in downstream
            )
    directed_arcs = [
        (edge_id, from_node, to_node, diameter)
        for edge_id, segment in segments.items()
        for from_node, to_node in direction_pairs[edge_id]
        for diameter in diameters
        if (
            not oriented_corridor
            or hydraulics[(edge_id, from_node, to_node)].diameters[diameter].minimum_flow_kg_s
            <= fixed_peak_flow_by_edge[edge_id]
            <= hydraulics[(edge_id, from_node, to_node)].diameters[diameter].maximum_flow_kg_s
        )
    ]
    if oriented_corridor and any(not any(arc[0] == edge_id for arc in directed_arcs) for edge_id in segments):
        return _empty_result(
            request,
            cost_basis=cost_basis,
            domain_status="infeasible",
            solver_status="not_run",
            termination="preflight_infeasible",
            reason="mandatory_peak_flow_has_no_velocity_compliant_diameter",
        )
    total_annual = sum(item.annual_demand_tonnes for item in request.well_demands)
    total_peak = sum(item.peak_mass_flow_kg_s for item in request.well_demands)
    dense_min = float(assumptions["dense_phase_min_pressure_bar"])
    max_pressure = float(assumptions["max_pressure_bar"])
    lift_options = [float(value) for value in assumptions["booster_lift_options_bar"]]
    max_lift = max(lift_options, default=0.0)
    big_m_pressure = max_pressure + max_lift + 200.0
    discount_rate = float(economics["discount_rate"])
    project_life = int(economics["project_life_years"])
    pv_factor = annuity_present_value_factor(discount_rate, project_life)
    operating_hours = float(request.assumptions["facility"]["operating_hours_per_year"])

    model = pyo.ConcreteModel("feature002_pipeline_network")
    model.N = pyo.Set(initialize=node_ids)
    model.W = pyo.Set(initialize=list(demand_by_id))
    model.S = pyo.Set(initialize=list(source_by_id))
    model.E = pyo.Set(initialize=list(segments))
    model.D = pyo.Set(initialize=diameters)
    model.L = pyo.Set(initialize=lift_options)
    model.A = pyo.Set(dimen=4, initialize=directed_arcs)
    model.z = pyo.Var(model.W, domain=pyo.Binary)
    model.p = pyo.Var(model.W, domain=pyo.Binary)
    model.t = pyo.Var(model.W, domain=pyo.Binary)
    model.mode_split = pyo.Constraint(model.W, rule=lambda m, well: m.z[well] == m.p[well] + m.t[well])
    for item in request.well_demands:
        if item.trucking_distance_km is None:
            model.t[item.candidate_id].fix(0)
    model.a = pyo.Var(model.A, domain=pyo.Binary)
    model.f_peak = pyo.Var(
        model.A,
        domain=pyo.NonNegativeReals,
        bounds=lambda _m, edge, from_node, to_node, diameter: (0.0, hydraulics[(edge, from_node, to_node)].diameters[float(diameter)].maximum_flow_kg_s),
    )
    model.f_annual = pyo.Var(model.A, domain=pyo.NonNegativeReals, bounds=(0.0, max(total_annual, 1.0)))
    model.loss = pyo.Var(model.A, domain=pyo.Reals)
    model.source_peak = pyo.Var(model.S, domain=pyo.NonNegativeReals)
    model.source_annual = pyo.Var(model.S, domain=pyo.NonNegativeReals)
    model.pressure = pyo.Var(model.N, domain=pyo.NonNegativeReals, bounds=(dense_min, max_pressure))
    model.booster = pyo.Var(model.N, model.L, domain=pyo.Binary)
    model.boost_flow = pyo.Var(model.N, model.L, domain=pyo.NonNegativeReals, bounds=(0.0, max(total_peak, 1.0)))

    model.one_direction = pyo.Constraint(
        model.E,
        rule=lambda m, edge: sum(m.a[arc] for arc in m.A if arc[0] == edge) <= 1,
    )
    model.peak_activation_upper = pyo.Constraint(
        model.A,
        rule=lambda m, edge, from_node, to_node, diameter: m.f_peak[edge, from_node, to_node, diameter]
        <= hydraulics[(edge, from_node, to_node)].diameters[float(diameter)].maximum_flow_kg_s * m.a[edge, from_node, to_node, diameter],
    )
    model.peak_activation_lower = pyo.Constraint(
        model.A,
        rule=lambda m, edge, from_node, to_node, diameter: m.f_peak[edge, from_node, to_node, diameter]
        >= hydraulics[(edge, from_node, to_node)].diameters[float(diameter)].minimum_flow_kg_s * m.a[edge, from_node, to_node, diameter],
    )
    model.annual_activation = pyo.Constraint(
        model.A,
        rule=lambda m, edge, from_node, to_node, diameter: m.f_annual[edge, from_node, to_node, diameter] <= max(total_annual, 1.0) * m.a[edge, from_node, to_node, diameter],
    )
    pw_points = {
        arc: hydraulics[(arc[0], arc[1], arc[2])].diameters[float(arc[3])].flow_breakpoints_kg_s for arc in directed_arcs
    }
    pw_values = {
        arc: hydraulics[(arc[0], arc[1], arc[2])].diameters[float(arc[3])].pressure_drop_breakpoints_bar for arc in directed_arcs
    }
    if oriented_corridor:
        fixed_pwl_drop = {
            arc: float(np.interp(fixed_peak_flow_by_edge[arc[0]], pw_points[arc], pw_values[arc]))
            for arc in directed_arcs
        }
        model.fixed_peak_flow = pyo.Constraint(
            model.A,
            rule=lambda m, edge, from_node, to_node, diameter: m.f_peak[edge, from_node, to_node, diameter]
            == fixed_peak_flow_by_edge[edge] * m.a[edge, from_node, to_node, diameter],
        )
        model.fixed_annual_flow = pyo.Constraint(
            model.A,
            rule=lambda m, edge, from_node, to_node, diameter: m.f_annual[edge, from_node, to_node, diameter]
            == fixed_annual_flow_by_edge[edge] * m.a[edge, from_node, to_node, diameter],
        )
        model.fixed_pwl_loss = pyo.Constraint(
            model.A,
            rule=lambda m, edge, from_node, to_node, diameter: m.loss[edge, from_node, to_node, diameter]
            == fixed_pwl_drop[edge, from_node, to_node, diameter] * m.a[edge, from_node, to_node, diameter],
        )
    else:
        model.piecewise_loss = pyo.Piecewise(
            model.A,
            model.loss,
            model.f_peak,
            pw_pts=pw_points,
            f_rule=pw_values,
            pw_constr_type="EQ",
            pw_repn="DCC",
            force_pw=True,
        )

    def peak_balance(m: pyo.ConcreteModel, node: str):
        inflow = sum(m.f_peak[arc] for arc in m.A if arc[2] == node)
        outflow = sum(m.f_peak[arc] for arc in m.A if arc[1] == node)
        if node in source_by_id:
            return outflow - inflow == m.source_peak[node]
        if node in demand_by_id:
            return inflow - outflow == demand_by_id[node].peak_mass_flow_kg_s * m.p[node]
        return inflow == outflow

    def annual_balance(m: pyo.ConcreteModel, node: str):
        inflow = sum(m.f_annual[arc] for arc in m.A if arc[2] == node)
        outflow = sum(m.f_annual[arc] for arc in m.A if arc[1] == node)
        if node in source_by_id:
            return outflow - inflow == m.source_annual[node]
        if node in demand_by_id:
            return inflow - outflow == demand_by_id[node].annual_demand_tonnes * m.p[node]
        return inflow == outflow

    model.peak_balance = pyo.Constraint(model.N, rule=peak_balance)
    model.annual_balance = pyo.Constraint(model.N, rule=annual_balance)
    model.source_peak_capacity = pyo.Constraint(model.S, rule=lambda m, source: m.source_peak[source] <= source_by_id[source].max_mass_flow_kg_s)
    model.source_annual_capacity = pyo.Constraint(model.S, rule=lambda m, source: m.source_annual[source] <= source_by_id[source].capacity_tonnes_per_year)
    model.annual_budget = pyo.Constraint(expr=sum(demand_by_id[well].annual_demand_tonnes * model.z[well] for well in model.W) <= request.annual_co2_budget_tonnes)
    for well in request.well_demands:
        if well.mandatory:
            model.z[well.candidate_id].fix(1)
        elif exact_mandatory_presolve:
            model.z[well.candidate_id].fix(0)
    if request.delivery_target_tonnes_per_year is not None:
        model.delivery_target = pyo.Constraint(expr=sum(demand_by_id[well].annual_demand_tonnes * model.z[well] for well in model.W) >= request.delivery_target_tonnes_per_year)
    max_selected = economics.get("max_selected_wells")
    if max_selected is not None:
        model.max_selected = pyo.Constraint(expr=sum(model.z[well] for well in model.W) <= int(max_selected))

    for source in request.sources:
        model.pressure[source.id].fix(source.outlet_pressure_bar)
    model.one_booster = pyo.Constraint(model.N, rule=lambda m, node: sum(m.booster[node, lift] for lift in m.L) <= 1)

    def outgoing_peak(m: pyo.ConcreteModel, node: str):
        return sum(m.f_peak[arc] for arc in m.A if arc[1] == node)

    model.boost_flow_selected = pyo.Constraint(model.N, model.L, rule=lambda m, node, lift: m.boost_flow[node, lift] <= max(total_peak, 1.0) * m.booster[node, lift])
    model.boost_flow_upper = pyo.Constraint(model.N, model.L, rule=lambda m, node, lift: m.boost_flow[node, lift] <= outgoing_peak(m, node))
    model.boost_flow_lower = pyo.Constraint(model.N, model.L, rule=lambda m, node, lift: m.boost_flow[node, lift] >= outgoing_peak(m, node) - max(total_peak, 1.0) * (1 - m.booster[node, lift]))
    model.booster_discharge = pyo.Constraint(model.N, rule=lambda m, node: m.pressure[node] + sum(lift * m.booster[node, lift] for lift in m.L) <= max_pressure)

    def pressure_upper(m: pyo.ConcreteModel, edge: str, from_node: str, to_node: str, diameter: float):
        boost = sum(lift * m.booster[from_node, lift] for lift in m.L)
        return m.pressure[to_node] - m.pressure[from_node] - boost + m.loss[edge, from_node, to_node, diameter] <= big_m_pressure * (1 - m.a[edge, from_node, to_node, diameter])

    def pressure_lower(m: pyo.ConcreteModel, edge: str, from_node: str, to_node: str, diameter: float):
        boost = sum(lift * m.booster[from_node, lift] for lift in m.L)
        return m.pressure[to_node] - m.pressure[from_node] - boost + m.loss[edge, from_node, to_node, diameter] >= -big_m_pressure * (1 - m.a[edge, from_node, to_node, diameter])

    model.pressure_upper = pyo.Constraint(model.A, rule=pressure_upper)
    model.pressure_lower = pyo.Constraint(model.A, rule=pressure_lower)
    model.maop_inlet = pyo.Constraint(
        model.A,
        rule=lambda m, edge, from_node, to_node, diameter: m.pressure[from_node] + sum(lift * m.booster[from_node, lift] for lift in m.L)
        <= hydraulics[(edge, from_node, to_node)].diameters[float(diameter)].maop_bar + big_m_pressure * (1 - m.a[edge, from_node, to_node, diameter]),
    )
    model.maop_outlet = pyo.Constraint(
        model.A,
        rule=lambda m, edge, from_node, to_node, diameter: m.pressure[to_node]
        <= hydraulics[(edge, from_node, to_node)].diameters[float(diameter)].maop_bar + big_m_pressure * (1 - m.a[edge, from_node, to_node, diameter]),
    )
    global_curve_anchors = [float(value) for value in assumptions.get("pressure_anchors_bar", [dense_min, max_pressure])]
    segment_curve_anchors = assumptions.get("segment_pressure_anchors_bar", {})

    def curve_inlet_bounds(edge: str) -> tuple[float, float]:
        anchors = [float(value) for value in segment_curve_anchors.get(edge, global_curve_anchors)]
        return min(anchors), max(anchors)

    minimum_curve_inlet = float(assumptions.get("hydraulic_curve_min_inlet_pressure_bar", min(global_curve_anchors)))
    model.minimum_active_inlet_pressure = pyo.Constraint(
        model.A,
        rule=lambda m, edge, from_node, to_node, diameter: m.pressure[from_node]
        + sum(lift * m.booster[from_node, lift] for lift in m.L)
        >= max(minimum_curve_inlet, curve_inlet_bounds(edge)[0])
        - big_m_pressure * (1 - m.a[edge, from_node, to_node, diameter]),
    )
    model.maximum_active_inlet_pressure = pyo.Constraint(
        model.A,
        rule=lambda m, edge, from_node, to_node, diameter: m.pressure[from_node]
        + sum(lift * m.booster[from_node, lift] for lift in m.L)
        <= curve_inlet_bounds(edge)[1]
        + big_m_pressure * (1 - m.a[edge, from_node, to_node, diameter]),
    )

    pipe_capex = {
        arc: pipe_capex_usd(diameter_in=arc[3], length_km=segments[arc[0]].length_km, case=cost_case) for arc in directed_arcs
    }
    pipe_lifecycle = {arc: value * (1.0 + float(cost_case["pipeline_maintenance_fraction"]) * pv_factor) for arc, value in pipe_capex.items()}
    booster_power_per_flow = {
        lift: booster_power_kw(
            mass_flow_kg_s=1.0,
            lift_bar=lift,
            pressure_bar=float(assumptions["reference_pressure_bar"]),
            temperature_c=float(assumptions["ground_temperature_c"]),
            efficiency=float(assumptions["booster_efficiency"]),
        )
        for lift in lift_options
    }
    booster_variable_lifecycle_per_flow = {
        lift: booster_power_per_flow[lift]
        * (float(cost_case["booster_variable_capex_usd_per_kw"]) + float(cost_case["electricity_usd_per_kwh"]) * operating_hours * pv_factor)
        for lift in lift_options
    }
    network_lifecycle_expr = (
        sum(pipe_lifecycle[arc] * model.a[arc] for arc in model.A)
        + sum(float(cost_case["booster_fixed_capex_usd"]) * model.booster[node, lift] for node in model.N for lift in model.L)
        + sum(booster_variable_lifecycle_per_flow[lift] * model.boost_flow[node, lift] for node in model.N for lift in model.L)
    )
    commodity_expr = sum(
        demand_by_id[well].annual_demand_tonnes * float(cost_case["co2_supply_usd_per_tonne"]) * pv_factor * model.z[well] for well in model.W
    )
    trucking_cost_by_well = {
        item.candidate_id: trucking_logistics_usd_per_tonne(cost_case, item.trucking_distance_km)
        * item.annual_demand_tonnes
        * pv_factor
        for item in request.well_demands
        if item.trucking_distance_km is not None
    }
    trucking_expr = sum(cost * model.t[well_id] for well_id, cost in trucking_cost_by_well.items())
    if request.objective_mode == "max_net_value":
        model.objective = pyo.Objective(
            expr=sum(demand_by_id[well].pre_logistics_value_usd * model.z[well] for well in model.W) - network_lifecycle_expr - commodity_expr - trucking_expr,
            sense=pyo.maximize,
        )
    else:
        model.objective = pyo.Objective(expr=network_lifecycle_expr + commodity_expr + trucking_expr, sense=pyo.minimize)

    solver = pyo.SolverFactory(solver_name)
    solver.options["seconds"] = float(assumptions.get("solver_time_limit_seconds", 30))
    solver.options["ratioGap"] = float(assumptions.get("solver_ratio_gap", 0.02))
    start = time.perf_counter()
    result = solver.solve(model, tee=False, load_solutions=False)
    solve_time = time.perf_counter() - start
    cumulative_solve_time = _cumulative_solve_time + solve_time
    termination = result.solver.termination_condition
    solver_status = result.solver.status
    has_solution = len(result.solution) > 0
    if termination == TerminationCondition.infeasible:
        return _empty_result(request, cost_basis=cost_basis, domain_status="infeasible", solver_status=str(solver_status), termination=str(termination), reason="solver_infeasible", solve_time=cumulative_solve_time)
    acceptable_termination = termination in {TerminationCondition.optimal, TerminationCondition.feasible, TerminationCondition.maxTimeLimit}
    if solver_status not in {SolverStatus.ok, SolverStatus.warning, SolverStatus.aborted} or not acceptable_termination or not has_solution:
        return _empty_result(request, cost_basis=cost_basis, domain_status="not_solved_to_tolerance", solver_status=str(solver_status), termination=str(termination), reason="no_acceptable_incumbent", solve_time=cumulative_solve_time)
    model.solutions.load_from(result)
    objective_value = float(pyo.value(model.objective))
    lower_bound = _numeric(getattr(result.problem, "lower_bound", None))
    upper_bound = _numeric(getattr(result.problem, "upper_bound", None))
    if termination == TerminationCondition.optimal:
        objective_bound = objective_value
        gap = 0.0
    else:
        objective_bound = upper_bound if request.objective_mode == "max_net_value" else lower_bound
        gap = None if objective_bound is None else abs(objective_bound - objective_value) / max(1.0, abs(objective_value))
    if termination != TerminationCondition.optimal and (gap is None or gap > float(assumptions.get("solver_ratio_gap", 0.02)) + 1e-9):
        return _empty_result(request, cost_basis=cost_basis, domain_status="not_solved_to_tolerance", solver_status=str(solver_status), termination=str(termination), reason="incumbent_gap_exceeds_limit", solve_time=cumulative_solve_time)

    selected = [well for well in model.W if pyo.value(model.z[well]) >= 0.5]
    trucked = [well for well in model.W if pyo.value(model.t[well]) >= 0.5]
    pipeline_served = [well for well in selected if well not in trucked]
    if not selected:
        empty = _empty_result(request, cost_basis=cost_basis, domain_status="no_viable_network", solver_status=str(solver_status), termination=str(termination), reason="all_wells_negative_after_logistics", solve_time=cumulative_solve_time)
        empty.objective_value_usd = objective_value
        empty.objective_bound_usd = objective_bound
        empty.optimality_gap = gap
        return empty

    active_rows: list[tuple[str, str, str, float, float]] = []
    for arc in directed_arcs:
        if pyo.value(model.a[arc]) >= 0.5:
            active_rows.append((arc[0], arc[1], arc[2], float(arc[3]), float(pyo.value(model.f_peak[arc]))))
    booster_by_node: dict[str, float] = {}
    boosters: list[BoosterStation] = []
    for node in node_ids:
        for lift in lift_options:
            if pyo.value(model.booster[node, lift]) < 0.5:
                continue
            flow = float(pyo.value(model.boost_flow[node, lift]))
            power = booster_power_kw(
                mass_flow_kg_s=flow,
                lift_bar=lift,
                pressure_bar=float(pyo.value(model.pressure[node])),
                temperature_c=float(assumptions["ground_temperature_c"]),
                efficiency=float(assumptions["booster_efficiency"]),
            )
            capex = booster_capex_usd(power_kw=power, case=cost_case)
            energy = power * operating_hours * float(cost_case["electricity_usd_per_kwh"])
            booster_by_node[node] = lift
            boosters.append(
                BoosterStation(
                    node_id=node,
                    suction_pressure_bar=float(pyo.value(model.pressure[node])),
                    discharge_pressure_bar=float(pyo.value(model.pressure[node])) + lift,
                    lift_bar=lift,
                    mass_flow_kg_s=flow,
                    power_kw=power,
                    capex_usd=capex,
                    annual_energy_cost_usd=energy,
                )
            )

    built_segments: list[BuiltSegment] = []
    verification_failures: list[dict[str, Any]] = []
    maximum_pressure_error = 0.0
    min_velocity = float(assumptions["min_velocity_m_s"])
    max_velocity = float(assumptions["max_velocity_m_s"])
    pressure_tolerance = float(assumptions.get("continuous_pressure_tolerance_bar", 1.0))
    relative_tolerance = float(assumptions.get("continuous_relative_tolerance", 0.05))
    for edge_id, from_node, to_node, diameter, peak_flow in active_rows:
        segment = segments[edge_id]
        reverse = from_node == segment.to_node
        inlet_suction = float(pyo.value(model.pressure[from_node]))
        inlet = inlet_suction + booster_by_node.get(from_node, 0.0)
        outlet = float(pyo.value(model.pressure[to_node]))
        profile = integrate_route_profile(
            segment,
            mass_flow_kg_s=peak_flow,
            diameter_in=diameter,
            inlet_pressure_bar=inlet,
            temperature_c=float(assumptions["ground_temperature_c"]),
            roughness_m=float(assumptions["pipe_roughness_m"]),
            max_step_m=float(assumptions.get("continuous_step_m", 100.0)),
            reverse=reverse,
        )
        actual_drop = inlet - profile[-1].pressure_bar
        arc = (edge_id, from_node, to_node, diameter)
        pwl_drop = float(pyo.value(model.loss[arc]))
        error = abs(actual_drop - pwl_drop)
        maximum_pressure_error = max(maximum_pressure_error, error)
        tolerance = max(pressure_tolerance, relative_tolerance * max(abs(actual_drop), 1.0))
        maop = hydraulics[(edge_id, from_node, to_node)].diameters[diameter].maop_bar
        pressures_ok = min(item.pressure_bar for item in profile) >= dense_min - 1e-6 and max(item.pressure_bar for item in profile) <= maop + 1e-6
        velocities_ok = min(item.velocity_m_s for item in profile) >= min_velocity - 1e-6 and max(item.velocity_m_s for item in profile) <= max_velocity + 1e-6
        head_ok = all(second.hydraulic_head_bar <= first.hydraulic_head_bar + 0.05 for first, second in zip(profile, profile[1:]))
        error_ok = error <= tolerance
        if not (pressures_ok and velocities_ok and head_ok and error_ok):
            verification_failures.append(
                {
                    "segment_id": edge_id,
                    "pressure_ok": pressures_ok,
                    "velocity_ok": velocities_ok,
                    "head_ok": head_ok,
                    "pwl_error_ok": error_ok,
                    "pwl_error_bar": error,
                    "continuous_inlet_pressure_bar": inlet,
                }
            )
        annual_flow = sum(float(pyo.value(model.f_annual[item])) for item in directed_arcs if item[0] == edge_id and item[1] == from_node and item[2] == to_node)
        built_segments.append(
            BuiltSegment(
                segment_id=edge_id,
                from_node=from_node,
                to_node=to_node,
                diameter_in=diameter,
                maop_bar=maop,
                length_km=segment.length_km,
                flow_tonnes_per_year=annual_flow,
                peak_mass_flow_kg_s=peak_flow,
                velocity_m_s=max(item.velocity_m_s for item in profile),
                inlet_pressure_bar=inlet,
                outlet_pressure_bar=profile[-1].pressure_bar,
                pressure_drop_bar=actual_drop,
                pwl_pressure_drop_bar=pwl_drop,
                pwl_error_bar=error,
                pwl_tolerance_bar=tolerance,
                dense_phase_ok=min(item.pressure_bar for item in profile) >= dense_min - 1e-6,
                maop_ok=max(item.pressure_bar for item in profile) <= maop + 1e-6,
                continuous_profile=profile,
            )
        )

    if verification_failures and _refinement_attempt < 2:
        refined = copy.deepcopy(request.assumptions)
        old = sorted(set(float(value) for value in refined["pipeline"]["hydraulic_breakpoint_fractions"]))
        refined["pipeline"]["hydraulic_breakpoint_fractions"] = sorted(set(old + [(a + b) / 2.0 for a, b in zip(old, old[1:])]))
        overrides = dict(refined["pipeline"].get("segment_pressure_anchors_bar", {}))
        trust_region = float(refined["pipeline"].get("refinement_pressure_trust_region_bar", 2.0))
        for failure in verification_failures:
            center = float(failure["continuous_inlet_pressure_bar"])
            overrides[str(failure["segment_id"])] = [
                max(dense_min, center - trust_region),
                center,
                min(max_pressure, center + trust_region),
            ]
        refined["pipeline"]["segment_pressure_anchors_bar"] = overrides
        return solve_pipeline_design(
            request.model_copy(update={"assumptions": refined}),
            _refinement_attempt=_refinement_attempt + 1,
            _cumulative_solve_time=cumulative_solve_time,
        )

    pipeline_capex_total = sum(pipe_capex_usd(diameter_in=row[3], length_km=segments[row[0]].length_km, case=cost_case) for row in active_rows)
    booster_capex_total = sum(item.capex_usd for item in boosters)
    annual_energy_total = sum(item.annual_energy_cost_usd for item in boosters)
    annual_mass = sum(demand_by_id[well].annual_demand_tonnes for well in selected)
    costs = build_cost_breakdown(
        cost_basis=cost_basis,
        cost_case=request.cost_case,
        pipeline_capex_usd_value=pipeline_capex_total,
        booster_capex_usd_value=booster_capex_total,
        annual_booster_energy_usd=annual_energy_total,
        annual_mass_tonnes=annual_mass,
        discount_rate=discount_rate,
        project_life_years=project_life,
    )
    segment_lifecycle_cost = {
        edge_id: pipe_capex_usd(diameter_in=diameter, length_km=segments[edge_id].length_km, case=cost_case)
        * (1.0 + float(cost_case["pipeline_maintenance_fraction"]) * pv_factor)
        for edge_id, _from, _to, diameter, _flow in active_rows
    }
    booster_lifecycle_cost = {item.node_id: item.capex_usd + item.annual_energy_cost_usd * pv_factor for item in boosters}
    allocations = _flow_based_allocations(
        selected=selected,
        demands=demand_by_id,
        active_rows=active_rows,
        segment_lifecycle_cost=segment_lifecycle_cost,
        booster_lifecycle_cost=booster_lifecycle_cost,
    )
    for built in built_segments:
        built.allocated_lifecycle_cost_usd = segment_lifecycle_cost[built.segment_id]
    delivered = {
        well: float(cost_case["co2_supply_usd_per_tonne"]) + allocations[well] / max(demand_by_id[well].annual_demand_tonnes * pv_factor, 1e-9)
        for well in selected
    }
    max_constraint_violation = _constraint_violation(model)
    peak_mass_balance_residual, annual_mass_balance_residual = _mass_balance_relative_residual(model, node_ids)
    mass_balance_tolerance = 1e-6
    solver_feasibility_tolerance = float(assumptions.get("solver_feasibility_tolerance", 1e-5))
    active_graph = nx.DiGraph((from_node, to_node) for _edge, from_node, to_node, _diameter, _peak in active_rows)
    connectivity_passed = all(
        any(source in active_graph and well in active_graph and nx.has_path(active_graph, source, well) for source in source_by_id)
        for well in pipeline_served
    )
    allocated_lifecycle_total = sum(allocations.values())
    transport_lifecycle_total = (
        costs.pipeline_capex_usd + costs.booster_capex_usd + costs.annual_opex_usd * pv_factor
    )
    allocation_relative_residual = abs(allocated_lifecycle_total - transport_lifecycle_total) / max(1.0, transport_lifecycle_total)
    constraint_audit = {
        "passed": (
            max_constraint_violation <= solver_feasibility_tolerance
            and peak_mass_balance_residual <= mass_balance_tolerance
            and annual_mass_balance_residual <= mass_balance_tolerance
            and connectivity_passed
            and allocation_relative_residual <= mass_balance_tolerance
        ),
        "max_constraint_violation": max_constraint_violation,
        "solver_feasibility_tolerance": solver_feasibility_tolerance,
        "peak_mass_balance_relative_residual": peak_mass_balance_residual,
        "annual_mass_balance_relative_residual": annual_mass_balance_residual,
        "mass_balance_relative_tolerance": mass_balance_tolerance,
        "connectivity_passed": connectivity_passed,
        "allocated_lifecycle_cost_usd": allocated_lifecycle_total,
        "transport_lifecycle_cost_usd": transport_lifecycle_total,
        "allocation_relative_residual": allocation_relative_residual,
        "annual_budget_used_tonnes": annual_mass,
        "annual_budget_limit_tonnes": request.annual_co2_budget_tonnes,
        "selected_well_count": len(selected),
        "active_segment_count": len(active_rows),
    }
    verification_passed = not verification_failures
    hydraulic_verification = {
        "passed": verification_passed,
        "failure_count": len(verification_failures),
        "failures": verification_failures,
        "maximum_pwl_error_bar": maximum_pressure_error,
        "pressure_tolerance_bar": pressure_tolerance,
        "relative_tolerance": relative_tolerance,
        "continuous_step_m": float(assumptions.get("continuous_step_m", 100.0)),
        "refinement_attempts": _refinement_attempt,
    }
    decisions = [
        WellSelectionDecision(
            candidate_id=item.candidate_id,
            selected=item.candidate_id in selected,
            reason=("mandatory" if item.mandatory else "selected") if item.candidate_id in selected else ("negative_net_value" if item.pre_logistics_value_usd <= 0 else "network_cost"),
        )
        for item in request.well_demands
    ]
    if not verification_passed:
        domain_status = "hydraulic_verification_failed"
    elif not constraint_audit["passed"]:
        domain_status = "not_solved_to_tolerance"
    else:
        domain_status = "accepted"
    transport_network_pv = costs.pipeline_capex_usd + costs.booster_capex_usd + costs.annual_opex_usd * pv_factor
    supply_mode_by_well = {well: ("trucking" if well in trucked else "pipeline") for well in selected}
    trucking_lifecycle_cost_usd = sum(trucking_cost_by_well[well] for well in trucked)
    return PipelineDesignResult(
        domain_status=domain_status,
        solver=solver_name,
        solver_status=str(solver_status),
        termination_condition=str(termination),
        objective_mode=request.objective_mode,
        objective_value_usd=objective_value,
        objective_bound_usd=objective_bound,
        optimality_gap=gap,
        selected_wells=selected,
        supply_mode_by_well=supply_mode_by_well,
        trucking_lifecycle_cost_usd=trucking_lifecycle_cost_usd,
        well_decisions=decisions,
        built_segments=built_segments,
        boosters=boosters,
        node_pressures_bar={node: float(pyo.value(model.pressure[node])) for node in node_ids},
        source_annual_flows_tonnes={source: float(pyo.value(model.source_annual[source])) for source in model.S},
        source_peak_flows_kg_s={source: float(pyo.value(model.source_peak[source])) for source in model.S},
        delivered_cost_usd_per_tonne=delivered,
        per_well_allocated_cost_usd=allocations,
        costs=costs,
        constraint_audit=constraint_audit,
        hydraulic_verification=hydraulic_verification,
        solve_time_seconds=cumulative_solve_time,
        route_provenance={
            **_request_provenance(request),
            "route_library_segment_count": len(all_segments),
            "optimization_segment_count": len(segments),
            "optimization_presolve": (
                "exact_minimum_cost_mandatory_shortest_corridor_with_single_source_orientation_and_fixed_flow_pwl"
                if oriented_corridor
                else "exact_minimum_cost_mandatory_shortest_corridor"
                if exact_mandatory_presolve
                else "none"
            ),
            "hydraulic_method": "CoolProp local-state DCC PWL plus continuous verification",
        },
        pipeline_capex_usd=costs.pipeline_capex_usd,
        booster_capex_usd=costs.booster_capex_usd,
        annual_opex_usd=costs.annual_opex_usd,
        total_network_cost_usd=transport_network_pv,
    )


def allocate_network_cost(result: PipelineDesignResult, well_values: dict[str, Any]) -> dict[str, float]:
    """Legacy adapter: return already reconciled flow-based allocations."""

    return {well: result.per_well_allocated_cost_usd.get(well, 0.0) for well in result.selected_wells}


def main() -> None:
    from jatibarang_ccus.infrastructure.routing import build_route_library
    from jatibarang_ccus.phase1.case_study import DEFAULT_ASSUMPTIONS, _candidate_models, _evaluate_candidate, _scenario_parameters, _source_model, load_assumptions

    parser = argparse.ArgumentParser(description="Run a Feature 002 Pyomo/CBC smoke solve.")
    parser.add_argument("--assumptions", type=Path, default=DEFAULT_ASSUMPTIONS)
    parser.add_argument("--candidate-limit", type=int, default=3)
    args = parser.parse_args()
    assumptions = load_assumptions(args.assumptions)
    source = _source_model(assumptions)
    candidates = _candidate_models(assumptions)[: args.candidate_limit]
    params = _scenario_parameters(assumptions["screening_grid"])[0]
    price = float(assumptions["carbon_prices_usd_per_tonne"]["current_idx"])
    values = [_evaluate_candidate(candidate, params, assumptions["economics"], price) for candidate in candidates]
    sources, demands = adapt_legacy_pipeline_inputs(source=source, candidates=candidates, well_values=values, assumptions=assumptions)
    library = build_route_library(RouteLibraryRequest(sources=sources, well_demands=demands, routing_assumptions=assumptions["routing"]))
    request = PipelineDesignRequest(
        sources=sources,
        well_demands=demands,
        route_library=library,
        annual_co2_budget_tonnes=float(assumptions["economics"]["co2_budget_tonnes"]),
        assumptions=assumptions,
        cost_case=str(assumptions["pipeline"].get("cost_case", "base")),
        solver=str(assumptions["pipeline"].get("solver", "cbc")),
    )
    print(json.dumps(solve_pipeline_design(request).model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    main()
