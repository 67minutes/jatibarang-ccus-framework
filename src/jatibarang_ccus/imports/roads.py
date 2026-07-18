"""Offline OSM road import, routing cache, and basin display layers."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np
import osmium
from scipy.spatial import cKDTree
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
    graph: nx.Graph
    kdtree: cKDTree
    lon_scale: float
    _path_cache: dict[
        tuple[int, int],
        tuple[float, list[tuple[float, float]]],
    ] = field(default_factory=dict, repr=False)

    def snap(self, lat: float, lon: float) -> tuple[int, float]:
        _, index = self.kdtree.query([lat, lon * self.lon_scale])
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
        nodes = nx.shortest_path(self.graph, a, b, weight="length_m")
        length_m = sum(
            self.graph.edges[u, v]["length_m"]
            for u, v in zip(nodes, nodes[1:])
        )
        route = [
            (float(self.latlon[node][0]), float(self.latlon[node][1]))
            for node in nodes
        ]
        result = (length_m / 1000.0, route)
        self._path_cache[(a, b)] = result
        self._path_cache[(b, a)] = (result[0], list(reversed(route)))
        return result


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
    legs: list[TruckingLeg] = []
    for demand in demands:
        demand_lat = demand.location.latitude
        demand_lon = demand.location.longitude
        source = min(
            sources,
            key=lambda item: haversine_km(
                item.location.latitude,
                item.location.longitude,
                demand_lat,
                demand_lon,
            ),
        )
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
            source_index, source_connector = graph.snap(source_lat, source_lon)
            demand_index, demand_connector = graph.snap(demand_lat, demand_lon)
            path_km, path = graph.shortest_path_km(
                source_index,
                demand_index,
            )
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
    def __init__(self, bbox: tuple[float, float, float, float]) -> None:
        super().__init__()
        self.bbox = bbox
        self.node_coords: dict[int, tuple[float, float]] = {}
        self.edges: list[tuple[int, int, float, str]] = []
        self.road_lines: list[tuple[str, list[tuple[float, float]]]] = []
        self.coastline: list[list[tuple[float, float]]] = []
        self.places: list[dict[str, Any]] = []

    def _inside(self, lat: float, lon: float) -> bool:
        min_lon, min_lat, max_lon, max_lat = self.bbox
        return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat

    def node(self, node: "osmium.osm.Node") -> None:
        kind = node.tags.get("place")
        if (
            kind in {"city", "town"}
            and "name" in node.tags
            and node.location.valid()
        ):
            lat, lon = node.location.lat, node.location.lon
            if self._inside(lat, lon):
                self.places.append(
                    {
                        "name": node.tags["name"],
                        "lat": lat,
                        "lon": lon,
                        "kind": kind,
                    }
                )

    def way(self, way: "osmium.osm.Way") -> None:
        highway = way.tags.get("highway")
        is_road = highway in DRIVABLE
        is_coast = way.tags.get("natural") == "coastline"
        if not is_road and not is_coast:
            return

        points: list[tuple[int, float, float]] = []
        for node in way.nodes:
            if not node.location.valid():
                continue
            lat, lon = node.location.lat, node.location.lon
            if self._inside(lat, lon):
                points.append((node.ref, lat, lon))
        if len(points) < 2:
            return
        if is_coast:
            self.coastline.append([(lat, lon) for _, lat, lon in points])
            return

        road_class = "major" if highway in MAJOR else "minor"
        self.road_lines.append(
            (road_class, [(lat, lon) for _, lat, lon in points])
        )
        for first, second in zip(points, points[1:]):
            ref_a, lat_a, lon_a = first
            ref_b, lat_b, lon_b = second
            self.node_coords[ref_a] = (lat_a, lon_a)
            self.node_coords[ref_b] = (lat_b, lon_b)
            self.edges.append(
                (
                    ref_a,
                    ref_b,
                    haversine_km(lat_a, lon_a, lat_b, lon_b) * 1000.0,
                    highway,
                )
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
            digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
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
            and tuple(entry["bbox"]) == bbox
            and graph_path.exists()
            and layers_path.exists()
        )
        if not cache_valid:
            collector = _Collector(bbox)
            try:
                collector.apply_file(str(path), locations=True)
            except (RuntimeError, OSError) as exc:
                raise RoadsImportError(
                    f"not a readable OSM extract: {path.name}: {exc}"
                ) from exc
            if not collector.edges:
                raise RoadsImportError(
                    "no drivable roads found inside the terrain extent: "
                    f"{path.name}"
                )

            source_graph = nx.Graph()
            for ref_a, ref_b, length_m, highway in collector.edges:
                existing = source_graph.get_edge_data(ref_a, ref_b)
                if existing is None or length_m < existing["length_m"]:
                    source_graph.add_edge(
                        ref_a,
                        ref_b,
                        length_m=length_m,
                        highway=highway,
                    )
            largest = max(nx.connected_components(source_graph), key=len)
            source_graph = source_graph.subgraph(largest).copy()
            refs = sorted(source_graph.nodes)
            ref_to_index = {ref: index for index, ref in enumerate(refs)}
            latlon = np.array(
                [collector.node_coords[ref] for ref in refs],
                dtype=np.float64,
            )
            graph_edges = list(source_graph.edges)
            edge_src = np.array(
                [ref_to_index[first] for first, _ in graph_edges],
                dtype=np.int64,
            )
            edge_dst = np.array(
                [ref_to_index[second] for _, second in graph_edges],
                dtype=np.int64,
            )
            edge_len = np.array(
                [source_graph.edges[edge]["length_m"] for edge in graph_edges],
                dtype=np.float64,
            )

            cache_dir.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(
                graph_path,
                latlon=latlon,
                edge_src=edge_src,
                edge_dst=edge_dst,
                edge_len=edge_len,
            )
            layers = {
                "roads": [
                    {"class": road_class, "points": _simplify(line)}
                    for road_class, line in collector.road_lines
                ],
                "coastline": [_simplify(line) for line in collector.coastline],
                "places": collector.places,
            }
            layers_path.write_text(json.dumps(layers), encoding="utf-8")
            index[road_network_id] = {
                "sha256": digest,
                "source_path": str(path),
                "bbox": list(bbox),
                "node_count": int(latlon.shape[0]),
                "edge_count": int(edge_src.shape[0]),
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
            **entry,
            "road_network_id": road_network_id,
            "bbox": tuple(entry["bbox"]),
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
            edge_src = data["edge_src"].copy()
            edge_dst = data["edge_dst"].copy()
            edge_len = data["edge_len"].copy()
        graph = nx.Graph()
        for src, dst, length in zip(edge_src, edge_dst, edge_len):
            graph.add_edge(int(src), int(dst), length_m=float(length))
        mid_lat = float(latlon[:, 0].mean())
        lon_scale = math.cos(math.radians(mid_lat))
        kdtree = cKDTree(
            np.column_stack([latlon[:, 0], latlon[:, 1] * lon_scale])
        )
        built = RoadGraph(
            road_network_id=road_network_id,
            latlon=latlon,
            graph=graph,
            kdtree=kdtree,
            lon_scale=lon_scale,
        )
        self._graphs[road_network_id] = built
        return built
