from __future__ import annotations

from jatibarang_ccus.contracts import (
    CO2Source,
    Coordinate,
    PipelineDesignRequest,
    PipelineWellDemand,
    RouteLibrary,
    RouteNode,
    RouteSegment,
    WellSelectionDecision,
)
from jatibarang_ccus.infrastructure.costs import load_cost_basis, trucking_logistics_usd_per_tonne
from jatibarang_ccus.infrastructure.pipeline import solve_pipeline_design
from jatibarang_ccus.phase1.case_study import DEFAULT_ASSUMPTIONS, load_assumptions


def _source(source_id: str, lon: float, capacity: float = 100_000.0) -> CO2Source:
    return CO2Source(
        id=source_id,
        name=source_id,
        location=Coordinate(latitude=0.0, longitude=lon),
        capacity_tonnes_per_year=capacity,
        max_mass_flow_kg_s=100.0,
        outlet_pressure_bar=120.0,
        outlet_temperature_c=27.0,
        co2_purity=0.98,
    )


def _well(well_id: str, lon: float, value: float = 5_000_000.0, mandatory: bool = False) -> PipelineWellDemand:
    return PipelineWellDemand(
        candidate_id=well_id,
        location=Coordinate(latitude=0.0, longitude=lon),
        annual_demand_tonnes=20_000.0,
        peak_mass_flow_kg_s=20.0,
        pre_logistics_value_usd=value,
        mandatory=mandatory,
    )


def _segment(segment_id: str, start: str, end: str, lon_a: float, lon_b: float) -> RouteSegment:
    return RouteSegment(
        id=segment_id,
        from_node=start,
        to_node=end,
        geometry=[Coordinate(latitude=0.0, longitude=lon_a), Coordinate(latitude=0.0, longitude=lon_b)],
        elevation_m=[0.0, 0.0],
        length_km=abs(lon_b - lon_a) * 111.32,
        min_slope=0.0,
        max_slope=0.0,
        route_cost=abs(lon_b - lon_a) * 111_320.0,
        terrain_sha256="TEST",
    )


def _assumptions():
    result = load_assumptions(DEFAULT_ASSUMPTIONS)
    result["pipeline"] = dict(result["pipeline"])
    result["pipeline"]["solver_time_limit_seconds"] = 20
    result["pipeline"]["solver_ratio_gap"] = 0.02
    return result


def _request(*, value: float = 5_000_000.0, mandatory: bool = False, budget: float = 100_000.0) -> PipelineDesignRequest:
    source = _source("S1", 0.0)
    well = _well("W1", 0.01, value=value, mandatory=mandatory)
    library = RouteLibrary(
        nodes=[
            RouteNode(id="S1", kind="source", location=source.location, elevation_m=0.0),
            RouteNode(id="W1", kind="well", location=well.location, elevation_m=0.0),
        ],
        segments=[_segment("E1", "S1", "W1", 0.0, 0.01)],
        fingerprint="SINGLE",
        provenance={"terrain_sha256": "TEST"},
    )
    return PipelineDesignRequest(
        sources=[source],
        well_demands=[well],
        route_library=library,
        annual_co2_budget_tonnes=budget,
        assumptions=_assumptions(),
        objective_mode="max_net_value",
    )


def test_single_well_network_is_selected_and_verified() -> None:
    result = solve_pipeline_design(_request())
    assert result.domain_status == "accepted"
    assert result.selected_wells == ["W1"]
    assert result.built_segments
    assert result.constraint_audit["passed"]
    assert result.hydraulic_verification["passed"]


def test_negative_value_returns_no_viable_network_not_infeasible() -> None:
    result = solve_pipeline_design(_request(value=-1_000_000.0))
    assert result.domain_status == "no_viable_network"
    assert not result.selected_wells
    assert not result.built_segments


def test_contradictory_mandatory_budget_returns_infeasible() -> None:
    request = _request(mandatory=True, budget=10_000.0)
    result = solve_pipeline_design(request)
    assert result.domain_status == "infeasible"
    assert result.constraint_audit["reason"] == "mandatory_annual_demand_exceeds_budget_or_capacity"


def test_shared_junction_connects_both_high_value_wells() -> None:
    source = _source("S1", 0.0)
    wells = [_well("W1", 0.02), _well("W2", 0.021)]
    nodes = [
        RouteNode(id="S1", kind="source", location=source.location, elevation_m=0.0),
        RouteNode(id="J1", kind="junction", location=Coordinate(latitude=0.0, longitude=0.01), elevation_m=0.0),
        *[RouteNode(id=w.candidate_id, kind="well", location=w.location, elevation_m=0.0) for w in wells],
    ]
    segments = [
        _segment("TRUNK", "S1", "J1", 0.0, 0.01),
        _segment("L1", "J1", "W1", 0.01, 0.02),
        _segment("L2", "J1", "W2", 0.01, 0.021),
    ]
    result = solve_pipeline_design(
        PipelineDesignRequest(
            sources=[source],
            well_demands=wells,
            route_library=RouteLibrary(nodes=nodes, segments=segments, fingerprint="SHARED", provenance={}),
            annual_co2_budget_tonnes=100_000.0,
            assumptions=_assumptions(),
        )
    )
    assert result.domain_status == "accepted"
    assert set(result.selected_wells) == {"W1", "W2"}
    assert any(segment.segment_id == "TRUNK" for segment in result.built_segments)


def test_capacity_constrained_multi_source_uses_both_sources() -> None:
    sources = [_source("S1", 0.0, 20_000.0), _source("S2", 0.02, 20_000.0)]
    wells = [_well("W1", 0.01), _well("W2", 0.03)]
    nodes = [
        *[RouteNode(id=s.id, kind="source", location=s.location, elevation_m=0.0) for s in sources],
        *[RouteNode(id=w.candidate_id, kind="well", location=w.location, elevation_m=0.0) for w in wells],
    ]
    segments = [_segment("E1", "S1", "W1", 0.0, 0.01), _segment("E2", "S2", "W2", 0.02, 0.03)]
    result = solve_pipeline_design(
        PipelineDesignRequest(
            sources=sources,
            well_demands=wells,
            route_library=RouteLibrary(nodes=nodes, segments=segments, fingerprint="MULTI", provenance={}),
            annual_co2_budget_tonnes=50_000.0,
            assumptions=_assumptions(),
        )
    )
    assert result.domain_status == "accepted"
    assert all(result.source_annual_flows_tonnes[source.id] > 0 for source in sources)


def test_mode_choice_contract_defaults() -> None:
    well = _well("W1", 0.01)
    assert well.trucking_distance_km is None
    trucked = well.model_copy(update={"trucking_distance_km": 78.0})
    assert trucked.trucking_distance_km == 78.0
    decision = WellSelectionDecision(candidate_id="W1", selected=False, reason="hydraulically_unreachable")
    assert decision.supply_mode is None


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

