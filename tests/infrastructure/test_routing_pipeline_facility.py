from __future__ import annotations

import networkx as nx

from jatibarang_ccus.contracts import PipelineDesignRequest, RouteLibraryRequest
from jatibarang_ccus.infrastructure.facility import evaluate_facility, facility_input_from_screened_value
from jatibarang_ccus.infrastructure.pipeline import adapt_legacy_pipeline_inputs, solve_pipeline_design
from jatibarang_ccus.infrastructure.routing import build_route_library
from jatibarang_ccus.phase1.case_study import (
    DEFAULT_ASSUMPTIONS,
    _candidate_models,
    _evaluate_candidate,
    _scenario_parameters,
    _source_model,
    load_assumptions,
)


def _small_case():
    assumptions = load_assumptions(DEFAULT_ASSUMPTIONS)
    source = _source_model(assumptions)
    candidates = _candidate_models(assumptions)[:3]
    params = _scenario_parameters(assumptions["screening_grid"])[0]
    price = float(assumptions["carbon_prices_usd_per_tonne"]["current_idx"])
    values = [_evaluate_candidate(candidate, params, assumptions["economics"], price) for candidate in candidates]
    sources, demands = adapt_legacy_pipeline_inputs(source=source, candidates=candidates, well_values=values, assumptions=assumptions)
    library = build_route_library(RouteLibraryRequest(sources=sources, well_demands=demands, routing_assumptions=assumptions["routing"]))
    return assumptions, source, candidates, values, sources, demands, library


def test_astar_routes_on_real_srtm_are_valid() -> None:
    _, source, candidates, _, _, _, library = _small_case()
    graph = nx.Graph()
    for segment in library.segments:
        graph.add_edge(segment.from_node, segment.to_node, weight=segment.length_km)
        assert len(segment.geometry) == len(segment.elevation_m)
    assert library.provenance["terrain_sha256"]
    assert nx.shortest_path_length(graph, source.id, candidates[0].id, weight="weight") > 50.0


def test_small_pipeline_milp_returns_audited_rational_zero() -> None:
    assumptions, _, _, _, sources, demands, library = _small_case()
    result = solve_pipeline_design(
        PipelineDesignRequest(
            sources=sources,
            well_demands=demands,
            route_library=library,
            annual_co2_budget_tonnes=sum(item.capacity_tonnes_per_year for item in sources),
            assumptions=assumptions,
            solver="cbc",
        )
    )
    assert result.termination_condition.lower() in {"optimal", "feasible", "maxtimelimit"}
    assert result.domain_status == "no_viable_network"
    assert not result.selected_wells
    assert result.constraint_audit["passed"]


def test_coolprop_facility_costs_are_monotonic_with_rate() -> None:
    assumptions, _, _, values, _, _, _ = _small_case()
    value = values[0]
    base_input = facility_input_from_screened_value(
        candidate_id=value.candidate_id,
        parameters=value.parameters,
        injected_co2_tonnes=value.injected_co2_tonnes,
        stored_co2_tonnes=value.stored_co2_tonnes,
        delivery_pressure_bar=100.0,
        peak_produced_gas_m3_day=value.peak_produced_gas_m3_day,
        produced_co2_fraction=value.produced_co2_fraction,
        assumptions=assumptions,
        well_count=1,
    )
    high_payload = base_input.model_copy(
        update={
            "injection_rate_std_m3_day": base_input.injection_rate_std_m3_day * 1.25,
            "fresh_co2_peak_mass_flow_kg_s": base_input.fresh_co2_peak_mass_flow_kg_s * 1.25,
        }
    )
    base = evaluate_facility(base_input, assumptions["facility"])
    high = evaluate_facility(high_payload, assumptions["facility"])
    assert high.total_power_kw > base.total_power_kw
    assert high.capex_usd > base.capex_usd
    assert base.dwsim_validation_status == "validated"
