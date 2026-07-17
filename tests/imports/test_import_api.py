from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import rasterio
from fastapi.testclient import TestClient
from rasterio.transform import from_bounds as transform_from_bounds

from jatibarang_ccus.api.app import create_app
from jatibarang_ccus.imports.store import ImportStore
from jatibarang_ccus.imports.terrain import TerrainRegistry

from tests.screening.helpers import FakeRunner


class _FakeScreening:
    def list_presets(self):
        return []

    def health(self):
        return {
            "status": "ready", "surrogate_loaded": True, "solver_available": True,
            "active_runs": 0, "presets": [], "details": {},
        }


def _app(tmp_path: Path):
    return create_app(
        FakeRunner,
        screening_factory=lambda _runner: _FakeScreening(),
        terrain_registry=TerrainRegistry(tmp_path / "registry"),
        import_store=ImportStore(tmp_path / "imports"),
    )


@pytest.fixture()
def dem(tmp_path: Path) -> Path:
    path = tmp_path / "dem.tif"
    data = np.linspace(0, 300, 40 * 50, dtype=np.float32).reshape(40, 50)
    transform = transform_from_bounds(107.5, -6.9, 108.2, -6.4, 50, 40)
    with rasterio.open(
        path, "w", driver="GTiff", height=40, width=50, count=1,
        dtype="float32", crs="EPSG:4326", transform=transform,
    ) as dst:
        dst.write(data, 1)
    return path


def test_terrain_import_list_and_window(tmp_path: Path, dem: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        imported = client.post("/terrain/import", json={"path": str(dem)})
        assert imported.status_code == 200
        body = imported.json()
        assert body["terrain_id"].startswith("terrain-")
        assert body["overview"]["width"] > 0

        listed = client.get("/terrain").json()[0]
        assert listed["terrain_id"] == body["terrain_id"]
        stored_path = Path(listed["source_path"])
        assert stored_path.exists()
        assert stored_path.parent.parent == tmp_path / "imports"

        window = client.get(
            f"/terrain/{body['terrain_id']}/window",
            params={"min_lon": 107.6, "min_lat": -6.8, "max_lon": 107.9, "max_lat": -6.6},
        )
        assert window.status_code == 200
        assert window.json()["extent"]["minLon"] >= 107.5

        missing = client.post("/terrain/import", json={"path": str(tmp_path / "nope.tif")})
        assert missing.status_code == 422


def test_reservoir_import_returns_typed_payload(tmp_path: Path) -> None:
    model = Path("data/validation_cases/case_0016.mat")
    with TestClient(_app(tmp_path)) as client:
        response = client.post("/reservoir/import", json={"model_path": str(model)})
        assert response.status_code == 200
        body = response.json()
        assert body["geology"]["length_x_m"] == 900.0
        assert body["native_fingerprint"]
        assert body["launchpads"]["covered_fingerprints"] == [body["native_fingerprint"]]
        assert body["well_ij"][0] in range(64)

        bad = client.post("/reservoir/import", json={"model_path": str(tmp_path / "x.mat")})
        assert bad.status_code == 422
