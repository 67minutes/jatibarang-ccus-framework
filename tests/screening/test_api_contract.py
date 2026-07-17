from __future__ import annotations

from fastapi.testclient import TestClient
import yaml

from jatibarang_ccus.api.app import create_app
from jatibarang_ccus.screening.progress import RunBusyError
from jatibarang_ccus.screening.schemas import ProgressEvent

from .helpers import FakeRunner


class FakeScreening:
    def list_presets(self):
        return []

    def health(self):
        return {
            "status": "ready",
            "surrogate_loaded": True,
            "solver_available": True,
            "active_runs": 0,
            "presets": [],
            "details": {},
        }

    def stream(self, payload):
        return iter(
            [
                ProgressEvent(
                    run_id=payload.run_id or "fake",
                    sequence=0,
                    event="cancelled",
                    stage="cancelled",
                )
            ]
        )

    def cancel(self, run_id):
        return run_id == "active"


def test_feature005_metadata_routes_and_openapi_contract() -> None:
    with TestClient(create_app(FakeRunner, screening_factory=lambda _runner: FakeScreening())) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/presets").status_code == 200

    generated = create_app(FakeRunner, screening_factory=lambda _runner: FakeScreening()).openapi()
    contract = yaml.safe_load(open("specs/005-screening-api/contracts/openapi.yaml", encoding="utf-8"))
    assert generated["info"] == contract["info"]
    for path, item in contract["paths"].items():
        assert path in generated["paths"]
        for method, expected in item.items():
            actual = generated["paths"][path][method]
            assert actual["summary"] == expected["summary"]
            assert set(expected["responses"]) <= set(actual["responses"])
    for path in ("/screen", "/screen/stream"):
        expected = contract["paths"][path]["post"]["requestBody"]["content"]["application/json"]["schema"]
        actual = generated["paths"][path]["post"]["requestBody"]["content"]["application/json"]["schema"]
        assert {item["$ref"] for item in actual["oneOf"]} == {
            item["$ref"] for item in expected["oneOf"]
        }
        assert actual["discriminator"]["propertyName"] == "mode"
    assert "text/event-stream" in generated["paths"]["/screen/stream"]["post"]["responses"]["200"]["content"]


def test_sse_and_cancellation_routes_have_typed_terminal_events() -> None:
    with TestClient(create_app(FakeRunner, screening_factory=lambda _runner: FakeScreening())) as client:
        response = client.post(
            "/screen/stream",
            json={"mode": "preset", "preset_id": "jatibarang_demo_v1", "run_id": "sse-test"},
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert "event: cancelled" in response.text
        assert '"run_id":"sse-test"' in response.text
        assert client.delete("/screen/runs/active").status_code == 202
        assert client.delete("/screen/runs/missing").status_code == 404


def test_screen_maps_busy_and_dependency_errors_to_429_and_503() -> None:
    class FailingScreening(FakeScreening):
        def __init__(self, error):
            self.error = error

        def run(self, _payload):
            raise self.error

    with TestClient(
        create_app(
            FakeRunner,
            screening_factory=lambda _runner: FailingScreening(RunBusyError("active")),
        )
    ) as client:
        response = client.post("/screen", json={"mode": "preset", "preset_id": "jatibarang_demo_v1"})
        assert response.status_code == 429
    with TestClient(
        create_app(
            FakeRunner,
            screening_factory=lambda _runner: FailingScreening(FileNotFoundError("preset missing")),
        )
    ) as client:
        response = client.post("/screen", json={"mode": "preset", "preset_id": "jatibarang_demo_v1"})
        assert response.status_code == 503
