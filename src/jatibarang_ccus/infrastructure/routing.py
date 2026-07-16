from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import heapq
import json
import math
from pathlib import Path
from typing import Any, Iterable

from affine import Affine
import numpy as np
from pyproj import CRS, Transformer
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import rowcol, xy
from rasterio.windows import Window
from shapely.geometry import Point, shape
from shapely import contains_xy
from shapely.ops import transform as transform_geometry

from jatibarang_ccus.contracts import (
    Coordinate,
    ExclusionZone,
    RouteLibrary,
    RouteLibraryRequest,
    RouteNode,
    RouteSegment,
)
from jatibarang_ccus.surrogate.config import REPO_ROOT


@dataclass(frozen=True)
class TerrainGrid:
    elevation: np.ndarray
    valid_mask: np.ndarray
    transform: Affine
    crs: str
    source_path: Path
    source_sha256: str
    downsample_factor: int
    local_crs: str
    to_local: Transformer
    x_m: np.ndarray
    y_m: np.ndarray
    cell_width_m: float
    cell_height_m: float


@dataclass(frozen=True)
class RoutingSurface:
    hard_mask: np.ndarray
    penalty_multiplier: np.ndarray
    zone_masks: dict[str, np.ndarray]
    zones: list[ExclusionZone]
    metadata: dict[str, Any]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _repo_path(path_value: str | Path) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else REPO_ROOT / path


def _coordinate(value: Coordinate | dict[str, float]) -> Coordinate:
    return value if isinstance(value, Coordinate) else Coordinate.model_validate(value)


def _bounds_for_points(points: Iterable[Coordinate], padding_degrees: float) -> tuple[float, float, float, float]:
    coords = list(points)
    west = min(point.longitude for point in coords) - padding_degrees
    east = max(point.longitude for point in coords) + padding_degrees
    south = min(point.latitude for point in coords) - padding_degrees
    north = max(point.latitude for point in coords) + padding_degrees
    return west, south, east, north


def _local_transformer(points: list[Coordinate]) -> tuple[str, Transformer]:
    lat0 = sum(item.latitude for item in points) / len(points)
    lon0 = sum(item.longitude for item in points) / len(points)
    local = CRS.from_proj4(f"+proj=aeqd +lat_0={lat0} +lon_0={lon0} +datum=WGS84 +units=m +no_defs")
    return local.to_string(), Transformer.from_crs("EPSG:4326", local, always_xy=True)


def load_terrain_grid(
    *,
    raster_path: str | Path,
    points: Iterable[Coordinate | dict[str, float]],
    target_cell_size_m: float = 300.0,
    padding_degrees: float = 0.05,
) -> TerrainGrid:
    path = _repo_path(raster_path)
    if not path.exists():
        raise FileNotFoundError(f"Terrain raster is missing: {path}")
    coords = [_coordinate(item) for item in points]
    if not coords:
        raise ValueError("At least one terrain point is required.")

    with rasterio.open(path) as src:
        if src.crs is None:
            raise ValueError(f"Terrain raster has no CRS: {path}")
        for coord in coords:
            if not (src.bounds.left <= coord.longitude <= src.bounds.right and src.bounds.bottom <= coord.latitude <= src.bounds.top):
                raise ValueError(f"Coordinate {coord} is outside terrain raster bounds.")
        west, south, east, north = _bounds_for_points(coords, padding_degrees)
        west, east = max(west, src.bounds.left), min(east, src.bounds.right)
        south, north = max(south, src.bounds.bottom), min(north, src.bounds.top)
        top_row, left_col = src.index(west, north)
        bottom_row, right_col = src.index(east, south)
        row_start = max(0, min(top_row, bottom_row))
        row_stop = min(src.height, max(top_row, bottom_row) + 1)
        col_start = max(0, min(left_col, right_col))
        col_stop = min(src.width, max(left_col, right_col) + 1)
        window = Window(col_start, row_start, col_stop - col_start, row_stop - row_start)

        local_crs, to_local = _local_transformer(coords)
        center_lat = (south + north) / 2.0
        native_cell_m = abs(src.transform.a) * 111_320.0 * math.cos(math.radians(center_lat))
        factor = max(1, int(round(float(target_cell_size_m) / max(native_cell_m, 1.0))))
        out_height = max(3, int(math.ceil(window.height / factor)))
        out_width = max(3, int(math.ceil(window.width / factor)))
        elevation = src.read(1, window=window, out_shape=(out_height, out_width), resampling=Resampling.average, masked=True)
        transform = src.window_transform(window) * Affine.scale(window.width / out_width, window.height / out_height)
        valid_mask = ~np.ma.getmaskarray(elevation)
        filled = np.asarray(elevation.astype(float).filled(np.nan), dtype=float)
        if np.isnan(filled).all():
            raise ValueError("Terrain crop has no valid elevation cells.")
        filled = np.nan_to_num(filled, nan=float(np.nanmedian(filled)))
        rows, cols = np.indices(filled.shape)
        lon, lat = xy(transform, rows.ravel(), cols.ravel(), offset="center")
        projected_x, projected_y = to_local.transform(np.asarray(lon), np.asarray(lat))
        x_m = np.asarray(projected_x).reshape(filled.shape)
        y_m = np.asarray(projected_y).reshape(filled.shape)
        x0, y0 = x_m[0, 0], y_m[0, 0]
        x1, y1 = x_m[0, min(1, out_width - 1)], y_m[0, min(1, out_width - 1)]
        x2, y2 = x_m[min(1, out_height - 1), 0], y_m[min(1, out_height - 1), 0]
        return TerrainGrid(
            elevation=filled,
            valid_mask=valid_mask,
            transform=transform,
            crs=str(src.crs),
            source_path=path,
            source_sha256=sha256_file(path),
            downsample_factor=factor,
            local_crs=local_crs,
            to_local=to_local,
            x_m=x_m,
            y_m=y_m,
            cell_width_m=max(math.hypot(x1 - x0, y1 - y0), 1.0),
            cell_height_m=max(math.hypot(x2 - x0, y2 - y0), 1.0),
        )


def load_exclusion_zones(path_value: str | Path | None) -> tuple[list[ExclusionZone], dict[str, Any]]:
    if not path_value:
        return [], {"status": "none", "sha256": None}
    path = _repo_path(path_value)
    if not path.exists():
        raise FileNotFoundError(f"Exclusion GeoJSON is missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    zones: list[ExclusionZone] = []
    for feature in payload.get("features", []):
        props = feature.get("properties", {})
        zones.append(
            ExclusionZone(
                zone_id=str(props["zone_id"]),
                zone_class=str(props["zone_class"]),
                routing_mode=str(props["routing_mode"]),
                geometry=feature["geometry"],
                buffer_m=float(props.get("buffer_m", 0.0)),
                penalty_multiplier=float(props.get("penalty_multiplier", 1.0)),
                provenance={key: value for key, value in props.items() if key not in {"zone_id", "zone_class", "routing_mode", "buffer_m", "penalty_multiplier"}},
            )
        )
    metadata = dict(payload.get("metadata", {}))
    metadata.update({"path": str(path), "sha256": sha256_file(path), "feature_count": len(zones)})
    return zones, metadata


def _coordinate_from_cell(grid: TerrainGrid, cell: tuple[int, int]) -> Coordinate:
    lon, lat = xy(grid.transform, cell[0], cell[1], offset="center")
    return Coordinate(latitude=float(lat), longitude=float(lon))


def _cell_from_coordinate(grid: TerrainGrid, coord: Coordinate) -> tuple[int, int]:
    row, col = rowcol(grid.transform, coord.longitude, coord.latitude)
    if not (0 <= int(row) < grid.elevation.shape[0] and 0 <= int(col) < grid.elevation.shape[1]):
        raise ValueError(f"Coordinate {coord} is outside cropped terrain grid.")
    cell = int(row), int(col)
    if not grid.valid_mask[cell]:
        raise ValueError(f"Coordinate {coord} falls on terrain nodata.")
    return cell


def _projected_geometry(grid: TerrainGrid, zone: ExclusionZone):
    geometry = shape(zone.geometry)
    projected = transform_geometry(lambda x, y, z=None: grid.to_local.transform(x, y), geometry)
    return projected.buffer(zone.buffer_m) if zone.buffer_m else projected


def _build_routing_surface(
    grid: TerrainGrid,
    *,
    zones: list[ExclusionZone],
    metadata: dict[str, Any],
    endpoint_cells: set[tuple[int, int]],
    endpoint_exemption_cells: int,
) -> RoutingSurface:
    nodata_mask = ~grid.valid_mask
    hard = nodata_mask.copy()
    penalty = np.ones(grid.elevation.shape, dtype=float)
    zone_masks: dict[str, np.ndarray] = {}
    projected = [(zone, _projected_geometry(grid, zone)) for zone in zones]
    local_x, local_y = grid.x_m.ravel(), grid.y_m.ravel()
    for zone, geometry in projected:
        mask = contains_xy(geometry, local_x, local_y).reshape(grid.elevation.shape)
        zone_masks[zone.zone_id] = mask
        if zone.routing_mode == "hard":
            hard |= mask
        else:
            penalty[mask] = np.maximum(penalty[mask], zone.penalty_multiplier)

    radius = max(0, int(endpoint_exemption_cells))
    for row, col in endpoint_cells:
        hard[max(0, row - radius) : row + radius + 1, max(0, col - radius) : col + radius + 1] = False
    hard |= nodata_mask
    return RoutingSurface(hard_mask=hard, penalty_multiplier=penalty, zone_masks=zone_masks, zones=zones, metadata=metadata)


def _distance_m(grid: TerrainGrid, a: Coordinate, b: Coordinate) -> float:
    ax, ay = grid.to_local.transform(a.longitude, a.latitude)
    bx, by = grid.to_local.transform(b.longitude, b.latitude)
    return math.hypot(bx - ax, by - ay)


def _cell_distance_m(grid: TerrainGrid, a: tuple[int, int], b: tuple[int, int]) -> float:
    return math.hypot(float(grid.x_m[b] - grid.x_m[a]), float(grid.y_m[b] - grid.y_m[a]))


def _neighbors(cell: tuple[int, int], shape_value: tuple[int, int]) -> Iterable[tuple[int, int]]:
    row, col = cell
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            neighbor = row + dr, col + dc
            if 0 <= neighbor[0] < shape_value[0] and 0 <= neighbor[1] < shape_value[1]:
                yield neighbor


def _edge_cost(
    grid: TerrainGrid,
    surface: RoutingSurface,
    a: tuple[int, int],
    b: tuple[int, int],
    *,
    slope_penalty: float,
    max_slope: float,
) -> float | None:
    if surface.hard_mask[b]:
        return None
    distance = _cell_distance_m(grid, a, b)
    if distance <= 0:
        return None
    slope = abs(float(grid.elevation[b] - grid.elevation[a])) / distance
    if slope > max_slope:
        return None
    return distance * (1.0 + slope_penalty * slope) * float((surface.penalty_multiplier[a] + surface.penalty_multiplier[b]) / 2.0)


def astar_route(
    grid: TerrainGrid,
    *,
    start: Coordinate,
    goal: Coordinate,
    slope_penalty: float,
    max_slope: float,
    surface: RoutingSurface | None = None,
) -> list[tuple[int, int]]:
    if surface is None:
        surface = RoutingSurface(
            hard_mask=np.zeros(grid.elevation.shape, dtype=bool),
            penalty_multiplier=np.ones(grid.elevation.shape),
            zone_masks={},
            zones=[],
            metadata={"status": "none"},
        )
    start_cell, goal_cell = _cell_from_coordinate(grid, start), _cell_from_coordinate(grid, goal)
    frontier: list[tuple[float, tuple[int, int]]] = [(0.0, start_cell)]
    came_from: dict[tuple[int, int], tuple[int, int] | None] = {start_cell: None}
    cost_so_far: dict[tuple[int, int], float] = {start_cell: 0.0}
    while frontier:
        _, current = heapq.heappop(frontier)
        if current == goal_cell:
            break
        for neighbor in _neighbors(current, grid.elevation.shape):
            step = _edge_cost(grid, surface, current, neighbor, slope_penalty=slope_penalty, max_slope=max_slope)
            if step is None:
                continue
            new_cost = cost_so_far[current] + step
            if neighbor not in cost_so_far or new_cost < cost_so_far[neighbor]:
                cost_so_far[neighbor] = new_cost
                heapq.heappush(frontier, (new_cost + _cell_distance_m(grid, neighbor, goal_cell), neighbor))
                came_from[neighbor] = current
    if goal_cell not in came_from:
        raise ValueError(f"No A* route found from {start} to {goal} under max_slope={max_slope}.")
    path = [goal_cell]
    while came_from[path[-1]] is not None:
        path.append(came_from[path[-1]])  # type: ignore[arg-type]
    path.reverse()
    return path


def _route_segment_from_cells(
    *,
    grid: TerrainGrid,
    surface: RoutingSurface,
    segment_id: str,
    from_node: str,
    to_node: str,
    cells: list[tuple[int, int]],
) -> RouteSegment:
    geometry = [_coordinate_from_cell(grid, cell) for cell in cells]
    elevations = [float(grid.elevation[cell]) for cell in cells]
    length_m, route_cost = 0.0, 0.0
    slopes: list[float] = []
    for a, b, elev_a, elev_b in zip(cells, cells[1:], elevations, elevations[1:]):
        distance = _cell_distance_m(grid, a, b)
        length_m += distance
        slopes.append((elev_b - elev_a) / max(distance, 1e-9))
        route_cost += distance * float((surface.penalty_multiplier[a] + surface.penalty_multiplier[b]) / 2.0)
    if length_m <= 0:
        raise ValueError(f"Route {segment_id} has zero length.")
    hard_ids = [zone.zone_id for zone in surface.zones if zone.routing_mode == "hard" and any(surface.zone_masks[zone.zone_id][cell] and surface.hard_mask[cell] for cell in cells)]
    penalty_ids = [zone.zone_id for zone in surface.zones if zone.routing_mode == "penalty" and any(surface.zone_masks[zone.zone_id][cell] for cell in cells)]
    return RouteSegment(
        id=segment_id,
        from_node=from_node,
        to_node=to_node,
        geometry=geometry,
        elevation_m=elevations,
        length_km=length_m / 1_000.0,
        min_slope=min(slopes) if slopes else 0.0,
        max_slope=max(slopes) if slopes else 0.0,
        route_cost=route_cost,
        terrain_sha256=grid.source_sha256,
        hard_exclusion_ids=hard_ids,
        penalty_zone_ids=penalty_ids,
        penalty_cost=max(0.0, route_cost - length_m),
    )


def _input_fingerprint(request: RouteLibraryRequest, terrain_sha: str, exclusion_sha: str | None) -> str:
    payload = {
        "sources": [{"id": item.id, "location": item.location.model_dump(mode="json")} for item in request.sources],
        "wells": [
            {
                "id": item.candidate_id,
                "location": item.location.model_dump(mode="json"),
                "influence_radius_m": item.influence_radius_m,
            }
            for item in request.well_demands
        ],
        "routing": {key: value for key, value in request.routing_assumptions.items() if key != "cache_directory"},
        "routing_algorithm_version": "2.0",
        "terrain_sha256": terrain_sha,
        "exclusion_sha256": exclusion_sha,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest().upper()


def _node_id(cell: tuple[int, int], endpoint_cells: dict[tuple[int, int], tuple[str, str]]) -> tuple[str, str]:
    if cell in endpoint_cells:
        return endpoint_cells[cell]
    return f"J_{cell[0]}_{cell[1]}", "junction"


def build_route_library(request: RouteLibraryRequest) -> RouteLibrary:
    assumptions = request.routing_assumptions
    endpoints = [(item.id, "source", item.location) for item in request.sources] + [
        (item.candidate_id, "well", item.location) for item in request.well_demands
    ]
    points = [item[2] for item in endpoints]
    grid = load_terrain_grid(
        raster_path=assumptions["terrain_raster_path"],
        points=points,
        target_cell_size_m=float(assumptions.get("target_cell_size_m", 300.0)),
        padding_degrees=float(assumptions.get("padding_degrees", 0.05)),
    )
    expected_sha = str(assumptions.get("terrain_sha256", "")).upper()
    if expected_sha and expected_sha != grid.source_sha256:
        raise ValueError(f"Terrain SHA256 mismatch: expected {expected_sha}, got {grid.source_sha256}.")
    endpoint_cells: dict[tuple[int, int], tuple[str, str]] = {}
    for node_id, kind, coord in endpoints:
        cell = _cell_from_coordinate(grid, coord)
        if cell in endpoint_cells:
            raise ValueError(f"Endpoints {endpoint_cells[cell][0]} and {node_id} map to the same terrain cell.")
        endpoint_cells[cell] = node_id, kind
    zones, exclusion_metadata = load_exclusion_zones(assumptions.get("exclusion_geojson_path"))
    fingerprint = _input_fingerprint(request, grid.source_sha256, exclusion_metadata.get("sha256"))
    cache_value = assumptions.get("cache_directory")
    cache_path = _repo_path(cache_value) / f"{fingerprint}.json" if cache_value else None
    if cache_path and cache_path.exists():
        cached = RouteLibrary.model_validate_json(cache_path.read_text(encoding="utf-8"))
        cached.provenance["cache_hit"] = True
        return cached
    surface = _build_routing_surface(
        grid,
        zones=zones,
        metadata=exclusion_metadata,
        endpoint_cells=set(endpoint_cells),
        endpoint_exemption_cells=int(assumptions.get("endpoint_exemption_cells", 1)),
    )
    slope_penalty = float(assumptions.get("slope_penalty", 8.0))
    max_slope = float(assumptions.get("max_buildable_slope", 1.5))
    nearest_count = int(assumptions.get("well_nearest_neighbors", 4))
    raw_paths: list[list[tuple[int, int]]] = []
    for source in request.sources:
        for well in request.well_demands:
            raw_paths.append(astar_route(grid, start=source.location, goal=well.location, slope_penalty=slope_penalty, max_slope=max_slope, surface=surface))
    seen_pairs: set[tuple[str, str]] = set()
    for well in request.well_demands:
        others = sorted(
            (item for item in request.well_demands if item.candidate_id != well.candidate_id),
            key=lambda item: _distance_m(grid, well.location, item.location),
        )[:nearest_count]
        for other in others:
            pair = tuple(sorted((well.candidate_id, other.candidate_id)))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            raw_paths.append(astar_route(grid, start=well.location, goal=other.location, slope_penalty=slope_penalty, max_slope=max_slope, surface=surface))

    adjacency: dict[tuple[int, int], set[tuple[int, int]]] = {}
    for path in raw_paths:
        for a, b in zip(path, path[1:]):
            adjacency.setdefault(a, set()).add(b)
            adjacency.setdefault(b, set()).add(a)
    marked = set(endpoint_cells) | {cell for cell, neighbors in adjacency.items() if len(neighbors) != 2}
    visited: set[frozenset[tuple[int, int]]] = set()
    chains: list[tuple[tuple[int, int], tuple[int, int], list[tuple[int, int]]]] = []
    for start in sorted(marked):
        for neighbor in sorted(adjacency.get(start, set())):
            edge = frozenset((start, neighbor))
            if edge in visited:
                continue
            visited.add(edge)
            chain = [start, neighbor]
            previous, current = start, neighbor
            while current not in marked:
                candidates = sorted(item for item in adjacency[current] if item != previous)
                if len(candidates) != 1:
                    raise RuntimeError("Route-union compression encountered an invalid degree-two chain.")
                nxt = candidates[0]
                visited.add(frozenset((current, nxt)))
                chain.append(nxt)
                previous, current = current, nxt
            chains.append((start, current, chain))
    max_segment_length_m = float(assumptions.get("max_candidate_segment_length_m", 30_000.0))
    split_chains: list[tuple[tuple[int, int], tuple[int, int], list[tuple[int, int]]]] = []
    for _start, _end, chain in chains:
        current_chain = [chain[0]]
        current_length = 0.0
        for cell in chain[1:]:
            current_length += _cell_distance_m(grid, current_chain[-1], cell)
            current_chain.append(cell)
            if current_length >= max_segment_length_m and cell != chain[-1]:
                marked.add(cell)
                split_chains.append((current_chain[0], cell, current_chain))
                current_chain = [cell]
                current_length = 0.0
        if len(current_chain) >= 2:
            split_chains.append((current_chain[0], current_chain[-1], current_chain))
    chains = split_chains
    nodes: list[RouteNode] = []
    for cell in sorted(marked):
        node_id, kind = _node_id(cell, endpoint_cells)
        nodes.append(RouteNode(id=node_id, kind=kind, location=_coordinate_from_cell(grid, cell), elevation_m=float(grid.elevation[cell])))
    segments: list[RouteSegment] = []
    for index, (start, end, chain) in enumerate(chains, start=1):
        from_id, _ = _node_id(start, endpoint_cells)
        to_id, _ = _node_id(end, endpoint_cells)
        segments.append(
            _route_segment_from_cells(
                grid=grid,
                surface=surface,
                segment_id=f"SEG_{index:04d}",
                from_node=from_id,
                to_node=to_id,
                cells=chain,
            )
        )
    provenance = {
        "terrain_path": str(grid.source_path),
        "terrain_sha256": grid.source_sha256,
        "terrain_crs": grid.crs,
        "local_metric_crs": grid.local_crs,
        "downsample_factor": grid.downsample_factor,
        "route_method": "A* on exclusion-aware downsampled SRTM union graph",
        "routing_algorithm_version": "2.0",
        "target_cell_size_m": float(assumptions.get("target_cell_size_m", 300.0)),
        "max_candidate_segment_length_m": max_segment_length_m,
        "source_count": len(request.sources),
        "candidate_well_count": len(request.well_demands),
        "junction_count": sum(node.kind == "junction" for node in nodes),
        "raw_path_count": len(raw_paths),
        "exclusions": exclusion_metadata,
        "cache_hit": False,
    }
    library = RouteLibrary(nodes=nodes, segments=segments, fingerprint=fingerprint, provenance=provenance)
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(library.model_dump_json(indent=2), encoding="utf-8")
    return library


def main() -> None:
    from jatibarang_ccus.infrastructure.pipeline import adapt_legacy_pipeline_inputs
    from jatibarang_ccus.phase1.case_study import DEFAULT_ASSUMPTIONS, _candidate_models, _source_model, load_assumptions

    parser = argparse.ArgumentParser(description="Build the Feature 002 route library.")
    parser.add_argument("--assumptions", type=Path, default=DEFAULT_ASSUMPTIONS)
    args = parser.parse_args()
    assumptions = load_assumptions(args.assumptions)
    sources, demands = adapt_legacy_pipeline_inputs(
        source=_source_model(assumptions), candidates=_candidate_models(assumptions), well_values=[], assumptions=assumptions
    )
    result = build_route_library(RouteLibraryRequest(sources=sources, well_demands=demands, routing_assumptions=assumptions["routing"]))
    print(json.dumps({"fingerprint": result.fingerprint, "nodes": len(result.nodes), "segments": len(result.segments), "provenance": result.provenance}, indent=2))


if __name__ == "__main__":
    main()
