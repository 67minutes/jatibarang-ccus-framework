from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import rasterio
from fastapi.testclient import TestClient
from rasterio.transform import from_bounds as transform_from_bounds

from jatibarang_ccus.api.app import create_app
from jatibarang_ccus.imports.launchpads import write_launchpad_bank
from jatibarang_ccus.imports.mrst import load_mrst_reservoir
from jatibarang_ccus.imports.store import ImportStore
from jatibarang_ccus.imports.terrain import TerrainRegistry
from jatibarang_ccus.surrogate.schemas import SeedHistory

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
        native_seed = SeedHistory.model_validate(body["native_seed"])
        assert native_seed.schedule_fingerprint == body["native_fingerprint"]
        assert body["bank_seeds"] == {}
        assert body["well_ij"][0] in range(64)

        bad = client.post("/reservoir/import", json={"model_path": str(tmp_path / "x.mat")})
        assert bad.status_code == 422


def test_reservoir_import_returns_fingerprint_keyed_bank_seeds(tmp_path: Path) -> None:
    model = Path("data/validation_cases/case_0016.mat")
    bank_entry = load_mrst_reservoir(Path("data/validation_cases/case_0115.mat")).seed
    bank_path = tmp_path / "model.launchpads.npz"
    bank_sha256 = write_launchpad_bank(
        bank_path,
        {bank_entry.schedule_fingerprint: bank_entry},
    )

    with TestClient(_app(tmp_path)) as client:
        response = client.post(
            "/reservoir/import",
            json={"model_path": str(model), "bank_path": str(bank_path)},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["launchpads"]["bank_id"]
    assert body["launchpads"]["bank_sha256"] == bank_sha256
    assert body["launchpads"]["covered_fingerprints"] == sorted(
        {body["native_fingerprint"], bank_entry.schedule_fingerprint}
    )
    assert set(body["bank_seeds"]) == {bank_entry.schedule_fingerprint}
    restored = SeedHistory.model_validate(body["bank_seeds"][bank_entry.schedule_fingerprint])
    assert restored.schedule_fingerprint == bank_entry.schedule_fingerprint
    stored_bank = tmp_path / "imports" / body["launchpads"]["bank_id"] / bank_path.name
    assert stored_bank.exists()


def test_reservoir_get_reloads_from_the_artifact_store(tmp_path: Path) -> None:
    model = Path("data/validation_cases/case_0016.mat")
    bank_entry = load_mrst_reservoir(
        Path("data/validation_cases/case_0115.mat")
    ).seed
    bank_path = tmp_path / "model.launchpads.npz"
    write_launchpad_bank(
        bank_path,
        {bank_entry.schedule_fingerprint: bank_entry},
    )

    with TestClient(_app(tmp_path)) as client:
        imported = client.post(
            "/reservoir/import",
            json={"model_path": str(model), "bank_path": str(bank_path)},
        ).json()

        again = client.get(
            f"/reservoir/{imported['model_id']}",
            params={"bank_id": imported["launchpads"]["bank_id"]},
        )
        assert again.status_code == 200
        body = again.json()
        assert body["sha256"] == imported["sha256"]
        assert body["native_fingerprint"] == imported["native_fingerprint"]
        assert body["launchpads"] == imported["launchpads"]
        assert set(body["bank_seeds"]) == set(imported["bank_seeds"])
        assert body["native_seed"]

        assert client.get("/reservoir/00000000deadbeef").status_code == 404
        missing_bank = client.get(
            f"/reservoir/{imported['model_id']}",
            params={"bank_id": "00000000deadbeef"},
        )
        assert missing_bank.status_code == 404


def test_path_taking_import_routes_refuse_non_loopback_clients(tmp_path: Path, dem: Path) -> None:
    """The import routes read local files named by the client; that is safe
    only from the machine's own user. A non-loopback peer must get 403 even if
    the server is ever bound beyond 127.0.0.1."""
    import asyncio

    import httpx

    async def remote_calls() -> tuple[int, int]:
        transport = httpx.ASGITransport(
            app=_app(tmp_path), client=("203.0.113.9", 4444)
        )
        async with httpx.AsyncClient(
            transport=transport, base_url="http://workbench"
        ) as remote:
            terrain = await remote.post("/terrain/import", json={"path": str(dem)})
            reservoir = await remote.post(
                "/reservoir/import",
                json={"model_path": "data/validation_cases/case_0016.mat"},
            )
            return terrain.status_code, reservoir.status_code

    assert asyncio.run(remote_calls()) == (403, 403)
