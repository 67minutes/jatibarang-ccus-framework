from __future__ import annotations

from pathlib import Path

import osmium
import pytest

from jatibarang_ccus.imports.roads import (
    RoadsImportError,
    RoadsRegistry,
    haversine_km,
)

EXTENT = (107.0, -6.6, 107.2, -6.3)


def write_pbf(path: Path) -> None:
    """Write a road detour plus out-of-bounds and display-only features."""
    writer = osmium.SimpleWriter(str(path))
    nodes = {
        1: (107.02, -6.50),
        2: (107.10, -6.35),
        3: (107.18, -6.50),
        4: (109.00, -6.50),
        5: (109.10, -6.50),
        6: (107.10, -6.45),
        7: (107.00, -6.30),
        8: (107.20, -6.30),
        9: (107.05, -6.55),
        10: (107.15, -6.55),
    }
    for node_id, (lon, lat) in nodes.items():
        tags = {"place": "town", "name": "Testville"} if node_id == 6 else {}
        writer.add_node(
            osmium.osm.mutable.Node(
                id=node_id,
                location=(lon, lat),
                tags=tags,
            )
        )
    writer.add_way(
        osmium.osm.mutable.Way(
            id=1,
            nodes=[1, 2, 3],
            tags={"highway": "primary"},
        )
    )
    writer.add_way(
        osmium.osm.mutable.Way(
            id=2,
            nodes=[4, 5],
            tags={"highway": "primary"},
        )
    )
    writer.add_way(
        osmium.osm.mutable.Way(
            id=3,
            nodes=[7, 8],
            tags={"natural": "coastline"},
        )
    )
    writer.add_way(
        osmium.osm.mutable.Way(
            id=4,
            nodes=[9, 10],
            tags={"waterway": "river"},
        )
    )
    writer.close()


@pytest.fixture()
def pbf(tmp_path: Path) -> Path:
    path = tmp_path / "toy.osm.pbf"
    write_pbf(path)
    return path


def test_import_registers_clips_and_is_idempotent(
    tmp_path: Path,
    pbf: Path,
) -> None:
    registry = RoadsRegistry(tmp_path / "imports")
    record = registry.imports(pbf, EXTENT)
    assert record.road_network_id.startswith("roads-")
    assert record.node_count == 3
    assert record.edge_count == 2
    assert registry.imports(pbf, EXTENT).road_network_id == record.road_network_id
    assert [r.road_network_id for r in registry.list()] == [record.road_network_id]


def test_shortest_path_beats_haversine_on_the_detour(
    tmp_path: Path,
    pbf: Path,
) -> None:
    registry = RoadsRegistry(tmp_path / "imports")
    record = registry.imports(pbf, EXTENT)
    graph = registry.graph(record.road_network_id)
    a_idx, a_conn = graph.snap(-6.50, 107.02)
    b_idx, b_conn = graph.snap(-6.50, 107.18)
    assert a_conn < 0.1 and b_conn < 0.1
    path_km, route = graph.shortest_path_km(a_idx, b_idx)
    direct_km = haversine_km(-6.50, 107.02, -6.50, 107.18)
    assert path_km > direct_km * 1.5
    assert len(route) == 3


def test_layers_carry_roads_coastline_and_places(
    tmp_path: Path,
    pbf: Path,
) -> None:
    registry = RoadsRegistry(tmp_path / "imports")
    record = registry.imports(pbf, EXTENT)
    layers = registry.layers(record.road_network_id)
    assert layers["roads"] and layers["roads"][0]["class"] == "major"
    assert layers["coastline"]
    assert layers["places"] == [
        {"name": "Testville", "lat": -6.45, "lon": 107.10, "kind": "town"}
    ]


def test_rejects_non_pbf(tmp_path: Path) -> None:
    bogus = tmp_path / "roads.osm.pbf"
    bogus.write_bytes(b"not a pbf")
    with pytest.raises(RoadsImportError):
        RoadsRegistry(tmp_path / "imports").imports(bogus, EXTENT)
