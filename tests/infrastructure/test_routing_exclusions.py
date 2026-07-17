from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from jatibarang_ccus.contracts import RouteLibraryRequest
from jatibarang_ccus.infrastructure.routing import (
    build_route_library,
    load_exclusion_zones,
    load_terrain_grid,
)
from jatibarang_ccus.phase1.case_study import (
    DEFAULT_ASSUMPTIONS,
    _candidate_models,
    _source_model,
    load_assumptions,
)
from jatibarang_ccus.infrastructure.pipeline import adapt_legacy_pipeline_inputs


def test_tracked_exclusions_have_hard_and_penalty_modes() -> None:
    assumptions = load_assumptions(DEFAULT_ASSUMPTIONS)
    zones, metadata = load_exclusion_zones(assumptions["routing"]["exclusion_geojson_path"])
    assert {zone.routing_mode for zone in zones} == {"hard", "penalty"}
    assert metadata["license"] == "ODbL 1.0"
    assert metadata["sha256"]


def test_terrain_loader_rejects_endpoint_outside_raster() -> None:
    assumptions = load_assumptions(DEFAULT_ASSUMPTIONS)
    with pytest.raises(ValueError, match="outside terrain raster"):
        load_terrain_grid(
            raster_path=assumptions["routing"]["terrain_raster_path"],
            points=[{"latitude": 10.0, "longitude": 10.0}],
        )


def test_terrain_loader_rejects_all_nodata_crop(tmp_path: Path) -> None:
    raster_path = tmp_path / "nodata.tif"
    with rasterio.open(
        raster_path,
        "w",
        driver="GTiff",
        width=10,
        height=10,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(107.0, -6.0, 0.01, 0.01),
        nodata=-9999.0,
    ) as dataset:
        dataset.write(np.full((10, 10), -9999.0, dtype=np.float32), 1)
    with pytest.raises(ValueError, match="no valid elevation cells"):
        load_terrain_grid(
            raster_path=raster_path,
            points=[{"latitude": -6.05, "longitude": 107.05}],
            target_cell_size_m=300.0,
            padding_degrees=0.01,
        )


def test_route_library_is_deterministic_and_contains_free_junctions(tmp_path: Path) -> None:
    assumptions = load_assumptions(DEFAULT_ASSUMPTIONS)
    source = _source_model(assumptions)
    candidates = _candidate_models(assumptions)[:4]
    sources, demands = adapt_legacy_pipeline_inputs(
        source=source,
        candidates=candidates,
        well_values=[],
        assumptions=assumptions,
    )
    routing = dict(assumptions["routing"])
    routing["cache_directory"] = str(tmp_path)
    request = RouteLibraryRequest(sources=sources, well_demands=demands, routing_assumptions=routing)
    first = build_route_library(request)
    second = build_route_library(request)
    assert first.fingerprint == second.fingerprint
    assert any(node.kind == "junction" for node in first.nodes)
    assert all(not segment.hard_exclusion_ids for segment in first.segments)
    assert first.provenance["terrain_sha256"] == assumptions["routing"]["terrain_sha256"]
