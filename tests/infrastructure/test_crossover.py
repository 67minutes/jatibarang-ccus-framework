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
