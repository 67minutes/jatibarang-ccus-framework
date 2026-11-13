from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import rasterio
from fastapi.testclient import TestClient
from rasterio.transform import from_bounds as transform_from_bounds

from jatibarang_ccus.api.app import create_app
from jatibarang_ccus.imports.launchpads import write_launchpad_bank
from jatibarang_ccus.imports.mrst import load_mrst_reservoir, write_derived_reservoir
from jatibarang_ccus.imports.roads import RoadsRegistry
from jatibarang_ccus.imports.store import ImportStore
from jatibarang_ccus.imports.terrain import TerrainRegistry
from jatibarang_ccus.infrastructure.economics import evaluate_economic_batch
from jatibarang_ccus.infrastructure.facility import evaluate_facility_portfolio
from jatibarang_ccus.infrastructure.supply import evaluate_trucking_supply
from jatibarang_ccus.screening.orchestrator import ScreeningOrchestrator, ScreeningServices
from jatibarang_ccus.surrogate.schemas import SeedHistory

from tests.screening.helpers import FakeRunner
from tests.imports.test_roads import write_pbf
from tests.screening.test_orchestration_integration import (
    accepted_pipeline,
    inline_request,
    route_library,
)


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
        roads_registry=RoadsRegistry(tmp_path / "imports"),
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


@pytest.fixture()
def roads_dem(tmp_path: Path) -> Path:
    path = tmp_path / "roads-dem.tif"
    data = np.linspace(0, 300, 40 * 50, dtype=np.float32).reshape(40, 50)
    transform = transform_from_bounds(107.0, -6.6, 107.2, -6.3, 50, 40)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=40,
        width=50,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
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


def test_derived_reservoir_omits_targets_but_preserves_runtime_contract(
    tmp_path: Path,
) -> None:
    source = Path("data/validation_cases/case_0016.mat")
    target = tmp_path / "case_0016.reservoir.npz"

    digest = write_derived_reservoir(source, target)
    raw = load_mrst_reservoir(source)
    derived = load_mrst_reservoir(target)

    assert derived.sha256 == digest
    assert derived.targets == {}
    assert derived.schedule == raw.schedule
    assert derived.seed.schedule_fingerprint == raw.seed.schedule_fingerprint
    assert derived.well_ij == raw.well_ij
    assert derived.completion_ij == raw.completion_ij
    assert derived.geology.permeability_md.values == raw.geology.permeability_md.values

    with TestClient(_app(tmp_path)) as client:
        response = client.post(
            "/reservoir/import", json={"model_path": str(target)}
        )
    assert response.status_code == 200
    assert response.json()["native_fingerprint"] == raw.seed.schedule_fingerprint


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


def test_reservoir_catalog_import_is_well_keyed_and_rejects_duplicates(
    tmp_path: Path,
) -> None:
    model = Path("data/validation_cases/case_0016.mat")
    with TestClient(_app(tmp_path)) as client:
        response = client.post(
            "/reservoir/import-batch",
            json={
                "entries": [
                    {"well_id": "W01", "model_path": str(model)},
                    {"well_id": "W02", "model_path": str(model)},
                ]
            },
        )
        duplicate = client.post(
            "/reservoir/import-batch",
            json={
                "entries": [
                    {"well_id": "W01", "model_path": str(model)},
                    {"well_id": "W01", "model_path": str(model)},
                ]
            },
        )

    assert response.status_code == 200
    assert response.json()["count"] == 2
    assert set(response.json()["reservoirs"]) == {"W01", "W02"}
    assert duplicate.status_code == 422


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


def test_screening_spatial_archive_round_trips_with_hash_reference(tmp_path: Path) -> None:
    orchestrator = ScreeningOrchestrator(
        FakeRunner(),
        services=ScreeningServices(
            route_builder=route_library,
            pipeline_solver=accepted_pipeline,
            facility_evaluator=evaluate_facility_portfolio,
            economic_evaluator=evaluate_economic_batch,
            trucking_evaluator=evaluate_trucking_supply,
            solver_checker=lambda _solver: None,
        ),
    )
    result = orchestrator.run(inline_request())
    payload = {
        "request_fingerprint": result.request_fingerprint,
        "detailed_predictions": {
            key: value.model_dump(mode="json")
            for key, value in result.detailed_predictions.items()
        },
        "detailed_reservoirs": {
            key: value.model_dump(mode="json")
            for key, value in result.detailed_reservoirs.items()
        },
    }

    with TestClient(_app(tmp_path)) as client:
        archived = client.post("/screening/spatial", json=payload)
        assert archived.status_code == 200
        reference = archived.json()
        assert reference["scenario_count"] == len(result.detailed_predictions)
        assert reference["compressed_bytes"] > 0

        restored = client.get(f"/screening/spatial/{reference['artifact_id']}")
        assert restored.status_code == 200
        body = restored.json()
        assert body["sha256"] == reference["sha256"]
        assert body["payload"]["request_fingerprint"] == result.request_fingerprint
        assert set(body["payload"]["detailed_predictions"]) == set(
            result.detailed_predictions
        )
        scenario_id = next(iter(result.detailed_predictions))
        assert body["payload"]["detailed_predictions"][scenario_id]["fields"]


def test_screening_spatial_archive_rejects_misaligned_scenarios(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        response = client.post(
            "/screening/spatial",
            json={
                "request_fingerprint": "A" * 64,
                "detailed_predictions": {},
                "detailed_reservoirs": {},
            },
        )
    assert response.status_code == 422


def test_roads_import_list_and_layers(
    tmp_path: Path,
    roads_dem: Path,
) -> None:
    pbf = tmp_path / "toy.osm.pbf"
    write_pbf(pbf)
    with TestClient(_app(tmp_path)) as client:
        terrain = client.post(
            "/terrain/import",
            json={"path": str(roads_dem)},
        ).json()
        imported = client.post(
            "/roads/import",
            json={"path": str(pbf), "terrain_id": terrain["terrain_id"]},
        )
        assert imported.status_code == 200
        body = imported.json()
        assert body["road_network_id"].startswith("roads-")
        assert body["edge_count"] > 0

        listed = client.get("/roads").json()
        assert listed[0]["road_network_id"] == body["road_network_id"]

        layers = client.get(f"/roads/{body['road_network_id']}/layers")
        assert layers.status_code == 200
        assert "roads" in layers.json()

        assert client.get("/roads/roads-unknown0000000/layers").status_code == 404
        unknown_terrain = client.post(
            "/roads/import",
            json={"path": str(pbf), "terrain_id": "terrain-nope"},
        )
        assert unknown_terrain.status_code == 404
        bad = client.post(
            "/roads/import",
            json={
                "path": str(tmp_path / "missing.pbf"),
                "terrain_id": terrain["terrain_id"],
            },
        )
        assert bad.status_code == 422


def test_path_taking_import_routes_refuse_non_loopback_clients(tmp_path: Path, dem: Path) -> None:
    """The import routes read local files named by the client; that is safe
    only from the machine's own user. A non-loopback peer must get 403 even if
    the server is ever bound beyond 127.0.0.1."""
    import asyncio

    import httpx

    async def remote_calls() -> tuple[int, int, int, int]:
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
            roads = await remote.post(
                "/roads/import",
                json={"path": "C:/roads.osm.pbf", "terrain_id": "terrain-x"},
            )
            catalog = await remote.post(
                "/reservoir/import-batch",
                json={
                    "entries": [
                        {
                            "well_id": "W01",
                            "model_path": "data/validation_cases/case_0016.mat",
                        }
                    ]
                },
            )
            return (
                terrain.status_code,
                reservoir.status_code,
                roads.status_code,
                catalog.status_code,
            )

    assert asyncio.run(remote_calls()) == (403, 403, 403, 403)
