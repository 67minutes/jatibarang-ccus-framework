"""Simplify Natural Earth coastline GeoJSON to a compact line bundle."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from shapely.geometry import shape

SIMPLIFY_TOLERANCE_DEG = 0.1


def main(source: str, target: str) -> None:
    data = json.loads(Path(source).read_text(encoding="utf-8"))
    lines: list[list[list[float]]] = []
    for feature in data["features"]:
        geometry = shape(feature["geometry"]).simplify(
            SIMPLIFY_TOLERANCE_DEG,
            preserve_topology=False,
        )
        parts = getattr(geometry, "geoms", [geometry])
        for part in parts:
            coords = [
                [round(float(longitude), 3), round(float(latitude), 3)]
                for longitude, latitude in part.coords
            ]
            if len(coords) >= 2:
                lines.append(coords)
    target_path = Path(target)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(
        json.dumps({"lines": lines}, separators=(",", ":")),
        encoding="utf-8",
    )
    print(
        f"{len(lines)} lines, {sum(len(line) for line in lines)} points, "
        f"{target_path.stat().st_size} bytes"
    )


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
