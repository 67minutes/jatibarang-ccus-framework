"""Terrain registry: whole-raster overviews and windowed crops (spec §6).

The registry JSON maps terrain_id -> {sha256, source_path, extent, cell_size_m}.
Overviews are decimated reads capped at max_px on the long side; windows are
bounded reads served for the field view. The same registered raster hash is
what routing consumes, keeping visualization and routing consistent.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from pydantic import BaseModel
from rasterio.windows import from_bounds as window_from_bounds


class TerrainImportError(ValueError):
    """The file is not a readable georeferenced raster."""


class Heightmap(BaseModel):
    width: int
    height: int
    extent: dict[str, float]  # minLon/maxLon/minLat/maxLat
    minElev: float
    maxElev: float
    elevations: list[float]


@dataclass(frozen=True)
class TerrainRecord:
    terrain_id: str
    sha256: str
    source_path: str
    extent: tuple[float, float, float, float]  # minLon, minLat, maxLon, maxLat
    cell_size_m: float


class TerrainRegistry:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.index_path = self.root / "terrain_registry.json"

    # ------------------------------------------------------------- persistence
    def _read_index(self) -> dict[str, dict]:
        if not self.index_path.exists():
            return {}
        return json.loads(self.index_path.read_text(encoding="utf-8"))

    def _write_index(self, index: dict[str, dict]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")

    # ------------------------------------------------------------------- API
    def imports(self, path: Path) -> TerrainRecord:
        path = Path(path)
        if not path.exists():
            raise TerrainImportError(f"terrain file is missing: {path}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        terrain_id = f"terrain-{digest[:16].lower()}"
        index = self._read_index()
        if terrain_id not in index:
            try:
                with rasterio.open(path) as src:
                    bounds = src.bounds
                    cell_deg = abs(src.transform.a)
            except Exception as exc:
                raise TerrainImportError(f"not a readable raster: {path.name}: {exc}") from exc
            mid_lat = (bounds.bottom + bounds.top) / 2
            cell_size_m = cell_deg * 111_320 * math.cos(math.radians(mid_lat))
            index[terrain_id] = {
                "sha256": digest,
                "source_path": str(path),
                "extent": [bounds.left, bounds.bottom, bounds.right, bounds.top],
                "cell_size_m": cell_size_m,
            }
            self._write_index(index)
        return self.get(terrain_id)

    def list(self) -> list[TerrainRecord]:
        return [self.get(terrain_id) for terrain_id in sorted(self._read_index())]

    def get(self, terrain_id: str) -> TerrainRecord:
        entry = self._read_index().get(terrain_id)
        if entry is None:
            raise KeyError(f"terrain is not registered: {terrain_id}")
        return TerrainRecord(
            terrain_id=terrain_id,
            sha256=entry["sha256"],
            source_path=entry["source_path"],
            extent=tuple(entry["extent"]),
            cell_size_m=entry["cell_size_m"],
        )

    def overview(self, terrain_id: str, max_px: int = 512) -> Heightmap:
        record = self.get(terrain_id)
        min_lon, min_lat, max_lon, max_lat = record.extent
        return self._read(record, (min_lon, min_lat, max_lon, max_lat), max_px)

    def window(
        self,
        terrain_id: str,
        bounds: tuple[float, float, float, float],
        max_px: int = 768,
    ) -> Heightmap:
        record = self.get(terrain_id)
        min_lon, min_lat, max_lon, max_lat = record.extent
        clipped = (
            max(bounds[0], min_lon), max(bounds[1], min_lat),
            min(bounds[2], max_lon), min(bounds[3], max_lat),
        )
        if clipped[0] >= clipped[2] or clipped[1] >= clipped[3]:
            raise TerrainImportError("window does not intersect the terrain extent")
        return self._read(record, clipped, max_px)

    def _read(
        self,
        record: TerrainRecord,
        bounds: tuple[float, float, float, float],
        max_px: int,
    ) -> Heightmap:
        with rasterio.open(record.source_path) as src:
            win = window_from_bounds(bounds[0], bounds[1], bounds[2], bounds[3], src.transform)
            scale = max(1.0, win.width / max_px, win.height / max_px)
            out_w = max(2, int(win.width / scale))
            out_h = max(2, int(win.height / scale))
            data = src.read(1, window=win, out_shape=(out_h, out_w)).astype(float)
            nodata = src.nodata
        if nodata is not None:
            data[data == nodata] = np.nan
        data = np.clip(np.nan_to_num(data, nan=0.0), 0.0, None)
        return Heightmap(
            width=out_w,
            height=out_h,
            extent={
                "minLon": bounds[0], "maxLon": bounds[2],
                "minLat": bounds[1], "maxLat": bounds[3],
            },
            minElev=float(data.min()),
            maxElev=float(data.max()),
            elevations=[float(v) for v in data.reshape(-1)],
        )
