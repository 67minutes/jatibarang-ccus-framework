"""Offline OSM road import, routing cache, and basin display layers."""

from __future__ import annotations

import hashlib
import heapq
import json
import math
from array import array
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import osmium
from shapely.geometry import LineString

from ..contracts import CO2Source, PipelineWellDemand, TruckingLeg

DRIVABLE = {
    "motorway",
    "trunk",
    "primary",
    "secondary",
    "tertiary",
    "unclassified",
    "residential",
    "motorway_link",
    "trunk_link",
    "primary_link",
    "secondary_link",
}
MAJOR = {
    "motorway",
    "trunk",
    "primary",
    "motorway_link",
    "trunk_link",
    "primary_link",
}
PAD_FRACTION = 0.2
MAX_LAYER_POINTS_PER_LINE = 400
LAYER_SIMPLIFY_TOLERANCE_DEG = 0.00005
EARTH_RADIUS_KM = 6371.0088
GREATCIRCLE_DETOUR_FACTOR = 1.4
MIN_LEG_KM = 0.1
CACHE_SCHEMA_VERSION = 4
MAX_LAYER_LINES_BY_CLASS = {"major": 4_000, "minor": 4_000}
MAX_PLACE_LABELS = 250


class RoadsImportError(ValueError):
    """The file is not a readable OSM extract with roads in the extent."""


def haversine_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    rad = math.pi / 180.0
    dlat = (lat2 - lat1) * rad
    dlon = (lon2 - lon1) * rad
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1 * rad)
        * math.cos(lat2 * rad)
        * math.sin(dlon / 2) ** 2
    )
    return EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(h), math.sqrt(1 - h))


@dataclass(frozen=True)
class RoadNetworkRecord:
    road_network_id: str
    sha256: str
    source_path: str
    bbox: tuple[float, float, float, float]
    node_count: int
    edge_count: int


@dataclass
class RoadGraph:
    road_network_id: str
    latlon: np.ndarray
    indptr: np.ndarray
    indices: np.ndarray
    weights_m: np.ndarray
    lon_scale: float
    _path_cache: dict[
        tuple[int, int],
        tuple[float, list[tuple[float, float]]],
    ] = field(default_factory=dict, repr=False)
    def snap(self, lat: float, lon: float) -> tuple[int, float]:
        # Chunked planar nearest-neighbour search avoids both a SciPy runtime
        # dependency and a second province-scale spatial-index allocation.
        best_index = 0
        best_distance_sq = math.inf
        chunk_size = 100_000
        scaled_lon = lon * self.lon_scale
        for start in range(0, self.latlon.shape[0], chunk_size):
            chunk = self.latlon[start : start + chunk_size]
            distance_sq = (
                np.square(chunk[:, 0] - lat)
                + np.square(chunk[:, 1] * self.lon_scale - scaled_lon)
            )
            local_index = int(np.argmin(distance_sq))
            local_distance_sq = float(distance_sq[local_index])
            if local_distance_sq < best_distance_sq:
                best_distance_sq = local_distance_sq
                best_index = start + local_index
        index = best_index
        node_lat, node_lon = self.latlon[int(index)]
        connector_km = haversine_km(
            lat,
            lon,
            float(node_lat),
            float(node_lon),
        )
        return int(index), connector_km

    def shortest_path_km(
        self,
        a: int,
        b: int,
    ) -> tuple[float, list[tuple[float, float]]]:
        cached = self._path_cache.get((a, b))
        if cached is not None:
            return cached
        return self.shortest_paths_km(a, [b])[b]

    def shortest_paths_km(
        self,
        source: int,
        targets: list[int],
    ) -> dict[int, tuple[float, list[tuple[float, float]]]]:
        """Resolve one source to many targets in one bounded Dijkstra pass."""

        results: dict[int, tuple[float, list[tuple[float, float]]]] = {}
        missing: set[int] = set()
        for target in targets:
            cached = self._path_cache.get((source, target))
            if cached is None:
                missing.add(target)
            else:
                results[target] = cached
        if not missing:
            return results

        node_count = self.latlon.shape[0]
        distances = np.full(node_count, np.inf, dtype=np.float64)
        previous = np.full(node_count, -1, dtype=np.int64)
        distances[source] = 0.0
        queue: list[tuple[float, int]] = [(0.0, source)]
        settled_targets: set[int] = set()
        while queue and missing:
            distance, node = heapq.heappop(queue)
            if distance != distances[node]:
                continue
            if node in missing:
                missing.remove(node)
                settled_targets.add(node)
                if not missing:
                    break
            for offset in range(
                int(self.indptr[node]),
                int(self.indptr[node + 1]),
            ):
                neighbour = int(self.indices[offset])
                candidate = distance + float(self.weights_m[offset])
                if candidate < distances[neighbour]:
                    distances[neighbour] = candidate
                    previous[neighbour] = node
                    heapq.heappush(queue, (candidate, neighbour))
        if missing:
            raise ValueError(
                "road nodes are disconnected: "
                f"{source} -> {sorted(missing)}"
            )

        for target in settled_targets:
            nodes = [target]
            while nodes[-1] != source:
                predecessor = int(previous[nodes[-1]])
                if predecessor < 0:
                    raise ValueError(
                        "road path reconstruction failed: "
                        f"{source} -> {target}"
                    )
                nodes.append(predecessor)
            nodes.reverse()
            route = [
                (float(self.latlon[node][0]), float(self.latlon[node][1]))
                for node in nodes
            ]
            result = (float(distances[target]) / 1000.0, route)
            self._path_cache[(source, target)] = result
            self._path_cache[(target, source)] = (
                result[0],
                list(reversed(route)),
            )
            results[target] = result
        return results


def _compact_largest_component(
    edge_ref_a: array,
    edge_ref_b: array,
    edge_length_m: array,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Densify, de-duplicate, and retain the largest component compactly.

    A province-scale ``networkx.Graph`` can require several gigabytes of
    Python objects.  This union-find pass has the same undirected-component
    semantics while keeping all large structures in packed NumPy arrays.
    """

    refs_a = np.frombuffer(edge_ref_a, dtype=np.int64)
    refs_b = np.frombuffer(edge_ref_b, dtype=np.int64)
    lengths = np.frombuffer(edge_length_m, dtype=np.float64)
    all_refs = np.empty(refs_a.size + refs_b.size, dtype=np.int64)
    all_refs[: refs_a.size] = refs_a
    all_refs[refs_a.size :] = refs_b
    refs = np.unique(all_refs)
    del all_refs
    src = np.searchsorted(refs, refs_a)
    dst = np.searchsorted(refs, refs_b)

    # Match nx.Graph semantics: undirected duplicate edges retain the minimum
    # observed length.
    low = np.minimum(src, dst)
    high = np.maximum(src, dst)
    order = np.lexsort((high, low))
    low = low[order]
    high = high[order]
    ordered_lengths = lengths[order]
    starts = np.empty(low.size, dtype=np.bool_)
    starts[0] = True
    starts[1:] = (low[1:] != low[:-1]) | (high[1:] != high[:-1])
    start_indices = np.flatnonzero(starts)
    src = low[start_indices]
    dst = high[start_indices]
    edge_len = np.minimum.reduceat(ordered_lengths, start_indices)
    del low, high, order, ordered_lengths, starts, start_indices

    node_count = refs.size
    parent = np.arange(node_count, dtype=np.int64)
    sizes = np.ones(node_count, dtype=np.int64)

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[int(parent[node])]
            node = int(parent[node])
        return node

    for edge_index in range(src.size):
        first = find(int(src[edge_index]))
        second = find(int(dst[edge_index]))
        if first == second:
            continue
        if sizes[first] < sizes[second]:
            first, second = second, first
        parent[second] = first
        sizes[first] += sizes[second]

    roots = np.empty(node_count, dtype=np.int64)
    for node in range(node_count):
        roots[node] = find(node)
    largest_root = int(np.argmax(np.bincount(roots)))
    keep_nodes = roots == largest_root
    dense_index = np.full(node_count, -1, dtype=np.int64)
    dense_index[keep_nodes] = np.arange(
        int(np.count_nonzero(keep_nodes)),
        dtype=np.int64,
    )
    keep_edges = keep_nodes[src] & keep_nodes[dst]
    compact_src = dense_index[src[keep_edges]]
    compact_dst = dense_index[dst[keep_edges]]
    compact_len = edge_len[keep_edges]
    compact_refs = refs[keep_nodes]
    return compact_refs, compact_src, compact_dst, compact_len


def _build_csr(
    node_count: int,
    edge_src: np.ndarray,
    edge_dst: np.ndarray,
    edge_len: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build a compact undirected CSR graph for exact length routing."""

    origins = np.empty(edge_src.size * 2, dtype=np.int64)
    destinations = np.empty_like(origins)
    weights = np.empty(origins.size, dtype=np.float64)
    origins[: edge_src.size] = edge_src
    origins[edge_src.size :] = edge_dst
    destinations[: edge_src.size] = edge_dst
    destinations[edge_src.size :] = edge_src
    weights[: edge_src.size] = edge_len
    weights[edge_src.size :] = edge_len
    order = np.argsort(origins, kind="stable")
    degree = np.bincount(origins, minlength=node_count)
    indptr = np.empty(node_count + 1, dtype=np.int64)
    indptr[0] = 0
    np.cumsum(degree, out=indptr[1:])
    return indptr, destinations[order], weights[order]


def compute_trucking_legs(
    sources: list[CO2Source],
    demands: list[PipelineWellDemand],
    graph: RoadGraph | None,
) -> tuple[float, str, list[TruckingLeg]]:
    """Build mass-weighted source-to-candidate trucking legs.

    Imported-road mode snaps endpoints onto the cached network and includes
    straight connector distances. Offline fallback uses great-circle distance
    with the approved 1.4 circuity factor.
    """

    if not sources:
        raise ValueError("trucking legs require at least one CO2 source")
    provenance = (
        f"osm_road_network:{graph.road_network_id}"
        if graph is not None
        else "greatcircle_detour_estimate"
    )
    selected_sources: list[CO2Source] = []
    for demand in demands:
        demand_lat = demand.location.latitude
        demand_lon = demand.location.longitude
        selected_sources.append(
            min(
                sources,
                key=lambda item: haversine_km(
                    item.location.latitude,
                    item.location.longitude,
                    demand_lat,
                    demand_lon,
                ),
            )
        )

    road_paths: dict[
        tuple[int, int],
        tuple[float, list[tuple[float, float]]],
    ] = {}
    snapped_sources: list[tuple[int, float] | None] = [None] * len(demands)
    snapped_demands: list[tuple[int, float] | None] = [None] * len(demands)
    if graph is not None:
        groups: dict[int, list[int]] = {}
        for index, (source, demand) in enumerate(
            zip(selected_sources, demands)
        ):
            source_snap = graph.snap(
                source.location.latitude,
                source.location.longitude,
            )
            demand_snap = graph.snap(
                demand.location.latitude,
                demand.location.longitude,
            )
            snapped_sources[index] = source_snap
            snapped_demands[index] = demand_snap
            groups.setdefault(source_snap[0], []).append(demand_snap[0])
        for source_index, target_indices in groups.items():
            for target_index, result in graph.shortest_paths_km(
                source_index,
                target_indices,
            ).items():
                road_paths[(source_index, target_index)] = result

    legs: list[TruckingLeg] = []
    for index, (demand, source) in enumerate(zip(demands, selected_sources)):
        demand_lat = demand.location.latitude
        demand_lon = demand.location.longitude
        source_lat = source.location.latitude
        source_lon = source.location.longitude
        route: list[tuple[float, float]] | None = None
        if graph is None:
            distance_km = (
                haversine_km(
                    source_lat,
                    source_lon,
                    demand_lat,
                    demand_lon,
                )
                * GREATCIRCLE_DETOUR_FACTOR
            )
        else:
            source_snap = snapped_sources[index]
            demand_snap = snapped_demands[index]
            if source_snap is None or demand_snap is None:  # pragma: no cover
                raise RuntimeError("road endpoints were not snapped")
            source_index, source_connector = source_snap
            demand_index, demand_connector = demand_snap
            path_km, path = road_paths[(source_index, demand_index)]
            distance_km = path_km + source_connector + demand_connector
            route = [
                (source_lat, source_lon),
                *path,
                (demand_lat, demand_lon),
            ]
        legs.append(
            TruckingLeg(
                candidate_id=demand.candidate_id,
                distance_km=max(distance_km, MIN_LEG_KM),
                annual_mass_tonnes=demand.annual_demand_tonnes,
                route=route,
            )
        )

    total_mass = sum(leg.annual_mass_tonnes for leg in legs)
    weighted_km = (
        sum(
            leg.distance_km * leg.annual_mass_tonnes
            for leg in legs
        )
        / total_mass
        if total_mass
        else MIN_LEG_KM
    )
    return weighted_km, provenance, legs


class _Collector(osmium.SimpleHandler):
    def __init__(
        self,
        bbox: tuple[float, float, float, float],
        *,
        node_store: Any | None = None,
    ) -> None:
        super().__init__()
        self.bbox = bbox
        self.node_coords = node_store if node_store is not None else {}
        self._disk_backed_nodes = node_store is not None
        # Packed arrays avoid one Python tuple plus one highway string reference
        # per edge while parsing province-scale extracts.
        self.edge_ref_a = array("q")
        self.edge_ref_b = array("q")
        self.edge_length_m = array("d")
        self.road_lines: list[tuple[str, list[tuple[float, float]]]] = []
        self._road_layer_counts = {"major": 0, "minor": 0}
        self.coastline: list[list[tuple[float, float]]] = []
        self.places: list[dict[str, Any]] = []

    def _inside(self, lat: float, lon: float) -> bool:
        min_lon, min_lat, max_lon, max_lat = self.bbox
        return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat

    def node(self, node: "osmium.osm.Node") -> None:
        if not node.location.valid():
            return
        lat, lon = node.location.lat, node.location.lon
        if not self._inside(lat, lon):
            return
        # OSM PBF files are ordered nodes before ways. Retaining only padded-
        # bbox coordinates avoids constructing a Java-wide location index.
        self.node_coords[node.id] = (
            node.location if self._disk_backed_nodes else (lat, lon)
        )
        kind = node.tags.get("place")
        if kind in {"city", "town"} and "name" in node.tags:
            self.places.append(
                {
                    "name": node.tags["name"],
                    "lat": lat,
                    "lon": lon,
                    "kind": kind,
                }
            )

    def coordinate(self, node_id: int) -> tuple[float, float] | None:
        try:
            value = self.node_coords[node_id]
        except KeyError:
            return None
        if self._disk_backed_nodes:
            if not value.valid():
                return None
            return float(value.lat), float(value.lon)
        return value

    def way(self, way: "osmium.osm.Way") -> None:
        highway = way.tags.get("highway")
        is_road = highway in DRIVABLE
        is_coast = way.tags.get("natural") == "coastline"
        if not is_road and not is_coast:
            return

        segments: list[list[tuple[int, float, float]]] = []
        current: list[tuple[int, float, float]] = []
        for node in way.nodes:
            coordinate = self.coordinate(node.ref)
            if coordinate is None:
                if len(current) >= 2:
                    segments.append(current)
                current = []
                continue
            lat, lon = coordinate
            current.append((node.ref, lat, lon))
        if len(current) >= 2:
            segments.append(current)
        if not segments:
            return
        if is_coast:
            self.coastline.extend(
                [(lat, lon) for _, lat, lon in segment]
                for segment in segments
            )
            return

        road_class = "major" if highway in MAJOR else "minor"
        for segment in segments:
            if self._road_layer_counts[road_class] < MAX_LAYER_LINES_BY_CLASS[road_class]:
                self.road_lines.append(
                    (road_class, [(lat, lon) for _, lat, lon in segment])
                )
                self._road_layer_counts[road_class] += 1
            for first, second in zip(segment, segment[1:]):
                ref_a, lat_a, lon_a = first
                ref_b, lat_b, lon_b = second
                self.edge_ref_a.append(ref_a)
                self.edge_ref_b.append(ref_b)
                self.edge_length_m.append(
                    haversine_km(lat_a, lon_a, lat_b, lon_b) * 1000.0
                )


def _simplify(
    points: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    if len(points) < 2:
        return points
    # Shapely consumes x/y, so temporarily present the stored lat/lon as lon/lat.
    line = LineString([(lon, lat) for lat, lon in points]).simplify(
        LAYER_SIMPLIFY_TOLERANCE_DEG,
        preserve_topology=False,
    )
    simplified = [(float(lat), float(lon)) for lon, lat in line.coords]
    if len(simplified) <= MAX_LAYER_POINTS_PER_LINE:
        return simplified
    step = math.ceil(len(simplified) / MAX_LAYER_POINTS_PER_LINE)
    capped = simplified[::step]
    if capped[-1] != simplified[-1]:
        capped.append(simplified[-1])
    return capped


def compact_layer_payload(
    layers: dict[str, Any],
    *,
    limits: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Deterministically bound cartographic roads without touching routing data."""

    selected: dict[str, list[tuple[int, dict[str, Any]]]] = {
        "major": [],
        "minor": [],
    }
    bounds = limits or MAX_LAYER_LINES_BY_CLASS
    for road in layers.get("roads", []):
        road_class = str(road.get("class", "minor"))
        if road_class not in selected:
            continue
        canonical = json.dumps(road, sort_keys=True, separators=(",", ":"))
        priority = int.from_bytes(
            hashlib.sha256(canonical.encode("utf-8")).digest()[:8],
            "big",
        )
        selected[road_class].append((priority, road))
    roads: list[dict[str, Any]] = []
    for road_class in ("major", "minor"):
        roads.extend(
            road
            for _, road in sorted(selected[road_class], key=lambda item: item[0])[
                : bounds[road_class]
            ]
        )
    places = sorted(
        layers.get("places", []),
        key=lambda place: hashlib.sha256(
            json.dumps(place, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).digest(),
    )[:MAX_PLACE_LABELS]
    return {**layers, "roads": roads, "places": places}


class RoadsRegistry:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.index_path = self.root / "roads_registry.json"
        self._graphs: dict[str, RoadGraph] = {}

    def _read_index(self) -> dict[str, dict[str, Any]]:
        if not self.index_path.exists():
            return {}
        return json.loads(self.index_path.read_text(encoding="utf-8"))

    def _write_index(self, index: dict[str, dict[str, Any]]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(
            json.dumps(index, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def imports(
        self,
        path: Path,
        extent: tuple[float, float, float, float],
    ) -> RoadNetworkRecord:
        path = Path(path)
        if not path.exists():
            raise RoadsImportError(f"road network file is missing: {path}")
        try:
            hasher = hashlib.sha256()
            with path.open("rb") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    hasher.update(block)
            digest = hasher.hexdigest().upper()
        except OSError as exc:
            raise RoadsImportError(
                f"road network file is unreadable: {path}: {exc}"
            ) from exc
        road_network_id = f"roads-{digest[:16].lower()}"
        pad_lon = (extent[2] - extent[0]) * PAD_FRACTION
        pad_lat = (extent[3] - extent[1]) * PAD_FRACTION
        bbox = (
            extent[0] - pad_lon,
            extent[1] - pad_lat,
            extent[2] + pad_lon,
            extent[3] + pad_lat,
        )
        cache_dir = self.root / digest[:16].lower()
        graph_path = cache_dir / "roads_graph.npz"
        layers_path = cache_dir / "roads_layers.json"
        index = self._read_index()
        entry = index.get(road_network_id)
        cache_valid = (
            entry is not None
            and entry.get("cache_schema_version") == CACHE_SCHEMA_VERSION
            and tuple(entry["bbox"]) == bbox
            and graph_path.exists()
            and layers_path.exists()
        )
        if not cache_valid:
            cache_dir.mkdir(parents=True, exist_ok=True)
            bbox_key = hashlib.sha256(
                json.dumps(bbox, separators=(",", ":")).encode("utf-8")
            ).hexdigest()[:12]
            location_index_path = cache_dir / f"bounded_locations_{bbox_key}.idx"
            location_store = osmium.index.create_map(
                f"sparse_file_array,{location_index_path}"
            )
            collector = _Collector(bbox, node_store=location_store)
            try:
                collector.apply_file(str(path))
            except (RuntimeError, OSError) as exc:
                raise RoadsImportError(
                    f"not a readable OSM extract: {path.name}: {exc}"
                ) from exc
            if not collector.edge_ref_a:
                raise RoadsImportError(
                    "no drivable roads found inside the terrain extent: "
                    f"{path.name}"
                )

            refs, edge_src, edge_dst, edge_len = _compact_largest_component(
                collector.edge_ref_a,
                collector.edge_ref_b,
                collector.edge_length_m,
            )
            latlon = np.empty((refs.size, 2), dtype=np.float64)
            for ref_index, ref in enumerate(refs):
                coordinate = collector.coordinate(int(ref))
                if coordinate is None:
                    raise RoadsImportError(
                        f"missing coordinate for retained OSM node {int(ref)}"
                    )
                latlon[ref_index] = coordinate
            indptr, indices, weights_m = _build_csr(
                refs.size,
                edge_src,
                edge_dst,
                edge_len,
            )
            edge_count = int(edge_src.size)
            del refs

            np.savez_compressed(
                graph_path,
                latlon=latlon,
                indptr=indptr,
                indices=indices,
                weights_m=weights_m,
            )
            layers = compact_layer_payload({
                "roads": [
                    {"class": road_class, "points": _simplify(line)}
                    for road_class, line in collector.road_lines
                ],
                "coastline": [_simplify(line) for line in collector.coastline],
                "places": collector.places,
            })
            layers_path.write_text(json.dumps(layers), encoding="utf-8")
            index[road_network_id] = {
                "cache_schema_version": CACHE_SCHEMA_VERSION,
                "sha256": digest,
                "source_path": str(path),
                "bbox": list(bbox),
                "node_count": int(latlon.shape[0]),
                "edge_count": edge_count,
            }
            self._write_index(index)
            self._graphs.pop(road_network_id, None)
        return self.get(road_network_id)

    def list(self) -> list[RoadNetworkRecord]:
        return [
            self.get(road_network_id)
            for road_network_id in sorted(self._read_index())
        ]

    def get(self, road_network_id: str) -> RoadNetworkRecord:
        entry = self._read_index().get(road_network_id)
        if entry is None:
            raise KeyError(f"road network is not registered: {road_network_id}")
        payload = {
            "road_network_id": road_network_id,
            "sha256": entry["sha256"],
            "source_path": entry["source_path"],
            "bbox": tuple(entry["bbox"]),
            "node_count": entry["node_count"],
            "edge_count": entry["edge_count"],
        }
        return RoadNetworkRecord(**payload)

    def _cache_dir(self, road_network_id: str) -> Path:
        return self.root / road_network_id.removeprefix("roads-")

    def layers(self, road_network_id: str) -> dict[str, Any]:
        self.get(road_network_id)
        path = self._cache_dir(road_network_id) / "roads_layers.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def graph(self, road_network_id: str) -> RoadGraph:
        cached = self._graphs.get(road_network_id)
        if cached is not None:
            return cached
        self.get(road_network_id)
        path = self._cache_dir(road_network_id) / "roads_graph.npz"
        with np.load(path) as data:
            latlon = data["latlon"].copy()
            indptr = data["indptr"].copy()
            indices = data["indices"].copy()
            weights_m = data["weights_m"].copy()
        mid_lat = float(latlon[:, 0].mean())
        lon_scale = math.cos(math.radians(mid_lat))
        built = RoadGraph(
            road_network_id=road_network_id,
            latlon=latlon,
            indptr=indptr,
            indices=indices,
            weights_m=weights_m,
            lon_scale=lon_scale,
        )
        self._graphs[road_network_id] = built
        return built
