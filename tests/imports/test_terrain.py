from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds as transform_from_bounds

from jatibarang_ccus.imports.terrain import TerrainImportError, TerrainRegistry


@pytest.fixture()
def small_geotiff(tmp_path: Path) -> Path:
    path = tmp_path / "toy_dem.tif"
    height, width = 60, 80
    data = np.linspace(0, 500, height * width, dtype=np.float32).reshape(height, width)
    transform = transform_from_bounds(107.0, -7.0, 108.0, -6.4, width, height)
    with rasterio.open(
        path, "w", driver="GTiff", height=height, width=width, count=1,
        dtype="float32", crs="EPSG:4326", transform=transform,
    ) as dst:
        dst.write(data, 1)
    return path


def test_import_registers_and_builds_overview(tmp_path: Path, small_geotiff: Path) -> None:
    registry = TerrainRegistry(tmp_path / "registry")
    record = registry.imports(small_geotiff)
    assert record.terrain_id.startswith("terrain-")
    assert len(record.sha256) == 64
    # idempotent by content hash
    assert registry.imports(small_geotiff).terrain_id == record.terrain_id
    assert [r.terrain_id for r in registry.list()] == [record.terrain_id]

    overview = registry.overview(record.terrain_id, max_px=32)
    assert max(overview.width, overview.height) <= 32
    assert overview.minElev >= 0 and overview.maxElev <= 500
    assert len(overview.elevations) == overview.width * overview.height


def test_window_crops_within_extent(tmp_path: Path, small_geotiff: Path) -> None:
    registry = TerrainRegistry(tmp_path / "registry")
    record = registry.imports(small_geotiff)
    window = registry.window(record.terrain_id, (107.2, -6.9, 107.6, -6.6), max_px=40)
    assert window.extent["minLon"] >= 107.0 and window.extent["maxLon"] <= 108.0
    assert len(window.elevations) == window.width * window.height


def test_import_rejects_non_raster(tmp_path: Path) -> None:
    bogus = tmp_path / "not_a_dem.tif"
    bogus.write_bytes(b"plain bytes")
    with pytest.raises(TerrainImportError):
        TerrainRegistry(tmp_path / "registry").imports(bogus)
