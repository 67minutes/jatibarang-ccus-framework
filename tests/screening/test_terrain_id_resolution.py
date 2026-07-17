from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds as transform_from_bounds

from jatibarang_ccus.imports.terrain import TerrainRegistry
from jatibarang_ccus.screening.orchestrator import (
    resolve_terrain_path,
    routing_assumptions_for_terrain,
)
from jatibarang_ccus.screening.schemas import InlineScreenRequest


def test_schema_accepts_arbitrary_terrain_id() -> None:
    request = InlineScreenRequest.model_construct(
        terrain_id="terrain-abc123def4567890"
    )
    assert request.terrain_id == "terrain-abc123def4567890"


def test_legacy_id_resolves_to_pinned_raster() -> None:
    path = resolve_terrain_path("jatibarang_srtm_v1")
    assert path.name == "DEM SRTM 30M JAWA BARAT.tif"


def test_unknown_id_raises_value_error() -> None:
    with pytest.raises(ValueError, match="terrain"):
        resolve_terrain_path("terrain-0000000000000000")


def test_registered_id_replaces_both_path_and_pinned_sha(tmp_path: Path) -> None:
    raster = tmp_path / "imported.tif"
    with rasterio.open(
        raster,
        "w",
        driver="GTiff",
        width=4,
        height=4,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform_from_bounds(107.0, -7.0, 108.0, -6.0, 4, 4),
    ) as target:
        target.write(np.arange(16, dtype=np.float32).reshape(4, 4), 1)

    registry = TerrainRegistry(tmp_path / "registry")
    record = registry.imports(raster)
    assumptions = routing_assumptions_for_terrain(
        record.terrain_id,
        {
            "terrain_raster_path": "legacy.tif",
            "terrain_sha256": "PINNED",
        },
        registry=registry,
    )

    assert Path(assumptions["terrain_raster_path"]) == raster
    assert assumptions["terrain_sha256"] == record.sha256
