from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

import numpy as np
import pytest
import yaml
from fastapi.testclient import TestClient

from jatibarang_ccus.api.app import create_app
from jatibarang_ccus.surrogate.preprocessing import schedule_fingerprint
from jatibarang_ccus.surrogate.runner import ModelInfo, ScheduledPrediction

from .helpers import request_from_mrst


STATS = {
    "pressure_mean": 53.994626286438965,
    "pressure_std": 8.33254043764201,
    "perm_mean": 1.6158922562004245,
    "perm_std": 0.5498339937243941,
    "poro_mean": 0.1945479605945279,
    "poro_std": 0.029472247869062187,
    "dt_max": 34.86787033081055,
    "structure_abs_max": 1.7161699533462524,
    "inj_rate_max": 9982.275106013587,
    "prod_bhp_max": 699.6446495360955,
    "n_cycles_max": 4.0,
    "anisotropy_max": 2.991920365879958,
    "delta_oil_max": 0.028243480250239372,
    "delta_gas_max": 0.005858070682734251,
}


class FakeRunner:
    def __init__(self) -> None:
        self.checkpoint = {"stats": STATS}

    def model_info(self) -> ModelInfo:
        return ModelInfo(
            checkpoint_path="fixture.pt",
            checkpoint_sha256="A" * 64,
            checkpoint_run_name="fixture",
            output_contract="production_v2",
            tin=8,
            stored_dynamic_channels=20,
            forward_dynamic_channels=13,
            static_channels=12,
            model_kwargs={},
        )

    def info_dict(self) -> dict:
        return asdict(self.model_info())

    def predict_compiled(self, compiled):
        return self._prediction(compiled)

    def predict_compiled_batch(self, compiled, *, microbatch_size=16):
        return [self._prediction(item) for item in compiled]

    def _prediction(self, compiled) -> ScheduledPrediction:
        horizon = compiled.forecast_steps
        pred = np.zeros((horizon, 4, 64, 64), dtype=np.float32)
        pred[:, 1] = 0.01
        pred[:, 2] = 0.02
        pred[:, 3] = 0.5
        delta = np.zeros((horizon, 2), dtype=np.float32)
        oil = np.concatenate([compiled.seed_oil_delta_m3, np.zeros(horizon, dtype=np.float32)])
        gas = np.concatenate([compiled.seed_gas_delta_m3, np.zeros(horizon, dtype=np.float32)])
        return ScheduledPrediction(
            scenario_id=compiled.scenario_id,
            pred_normalized=pred,
            pred_pressure_bar=np.full((horizon, 64, 64), STATS["pressure_mean"], dtype=np.float32),
            pred_delta_normalized=delta,
            forecast_oil_delta_m3=np.zeros(horizon, dtype=np.float32),
            forecast_gas_delta_m3=np.zeros(horizon, dtype=np.float32),
            oil_delta_m3=oil,
            gas_delta_m3=gas,
            cumulative_oil_m3=np.cumsum(oil),
            cumulative_gas_m3=np.cumsum(gas),
            stages=compiled.stages.copy(),
        )


class ShortFakeRunner(FakeRunner):
    def _prediction(self, compiled) -> ScheduledPrediction:
        prediction = super()._prediction(compiled)
        horizon = 1
        return ScheduledPrediction(
            scenario_id=prediction.scenario_id,
            pred_normalized=prediction.pred_normalized[:horizon],
            pred_pressure_bar=prediction.pred_pressure_bar[:horizon],
            pred_delta_normalized=prediction.pred_delta_normalized[:horizon],
            forecast_oil_delta_m3=prediction.forecast_oil_delta_m3[:horizon],
            forecast_gas_delta_m3=prediction.forecast_gas_delta_m3[:horizon],
            oil_delta_m3=prediction.oil_delta_m3[: 8 + horizon],
            gas_delta_m3=prediction.gas_delta_m3[: 8 + horizon],
            cumulative_oil_m3=prediction.cumulative_oil_m3[: 8 + horizon],
            cumulative_gas_m3=prediction.cumulative_gas_m3[: 8 + horizon],
            stages=prediction.stages[: 8 + horizon],
        )


def test_lifespan_loads_once_and_model_info_exposes_contract() -> None:
    calls = 0

    def factory():
        nonlocal calls
        calls += 1
        return FakeRunner()

    with TestClient(create_app(factory)) as client:
        first = client.get("/model/info")
        second = client.get("/model/info")
    assert first.status_code == 200
    assert second.status_code == 200
    assert calls == 1
    assert first.json()["dynamic_channels_stored"][0] == "pressure_normalized"
    assert first.json()["upstream_validated_rollout_steps"] == 24
    assert first.json()["output_units"]["co2_inventory"] == "metric tonne"


def test_predict_returns_detailed_fields_and_flags() -> None:
    payload = request_from_mrst().model_dump(mode="json")
    with TestClient(create_app(FakeRunner)) as client:
        response = client.post("/predict", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["timeline"]) == 48
    assert len(body["fields"]) == 48
    assert body["confidence"]["extended_horizon"] is True
    assert body["inventory"]["status"] == "available"
    assert body["provenance"]["checkpoint_sha256"] == "A" * 64
    assert body["provenance"]["schedule_fingerprint"] == payload["seed"]["schedule_fingerprint"]
    assert {flag["quantity"] for flag in body["extrapolation_flags"]} >= {
        "injection_rate_m3_day",
        "injection_duration_days",
        "cycles",
    }


def test_out_of_range_prediction_runs_and_serializes_flag() -> None:
    request = request_from_mrst()
    schedule = request.schedule.model_copy(update={"injection_rate_m3_day": 12000.0})
    seed = request.seed.model_copy(update={"schedule_fingerprint": schedule_fingerprint(schedule)})
    payload = request.model_copy(update={"schedule": schedule, "seed": seed}).model_dump(mode="json")
    with TestClient(create_app(FakeRunner)) as client:
        response = client.post("/predict", json=payload)
    assert response.status_code == 200, response.text
    flag = next(item for item in response.json()["extrapolation_flags"] if item["quantity"] == "injection_rate_m3_day")
    assert flag == {
        "quantity": "injection_rate_m3_day",
        "observed_min": 12000.0,
        "observed_max": 12000.0,
        "trained_min": 8000.0,
        "trained_max": 10000.0,
        "is_extrapolation": True,
        "evaluated": True,
    }


def test_batch_is_compact_except_selected_scenarios() -> None:
    request = request_from_mrst()
    payload = {
        "geologies": {"g": request.geology.model_dump(mode="json")},
        "seeds": {"s": request.seed.model_dump(mode="json")},
        "scenarios": [
            {"scenario_id": "full", "geology_id": "g", "seed_id": "s", "schedule": request.schedule.model_dump(mode="json")},
            {"scenario_id": "compact", "geology_id": "g", "seed_id": "s", "schedule": request.schedule.model_dump(mode="json")},
        ],
        "full_field_scenario_ids": ["full"],
    }
    with TestClient(create_app(FakeRunner)) as client:
        response = client.post("/predict/batch", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scenario_count"] == 2
    assert body["results"][0]["fields"] is not None
    assert body["results"][1]["fields"] is None


def test_predict_rejects_mismatched_seed_fingerprint() -> None:
    request = request_from_mrst()
    payload = request.model_dump(mode="json")
    payload["seed"]["schedule_fingerprint"] = "0" * 64
    with TestClient(create_app(FakeRunner)) as client:
        response = client.post("/predict", json=payload)
    assert response.status_code == 422
    assert "fingerprint mismatch" in response.json()["detail"]


def test_predict_rejects_bad_shape_nonfinite_and_impossible_values() -> None:
    base = request_from_mrst().model_dump(mode="json")
    payloads = []

    bad_shape = json.loads(json.dumps(base))
    bad_shape["geology"]["permeability_md"]["shape"] = [32, 128]
    payloads.append((bad_shape, False))

    nonfinite = json.loads(json.dumps(base))
    nonfinite["schedule"]["injection_rate_m3_day"] = float("inf")
    payloads.append((nonfinite, True))

    impossible = json.loads(json.dumps(base))
    impossible["seed"]["frames"][0]["pressure_bar"]["values"][0] = -1.0
    payloads.append((impossible, False))

    with TestClient(create_app(FakeRunner)) as client:
        for payload, raw_json in payloads:
            if raw_json:
                response = client.post(
                    "/predict",
                    content=json.dumps(payload),
                    headers={"content-type": "application/json"},
                )
            else:
                response = client.post("/predict", json=payload)
            assert response.status_code == 422, response.text


def test_batch_endpoint_accepts_200_compact_scenarios() -> None:
    request = request_from_mrst()
    payload = {
        "geologies": {"g": request.geology.model_dump(mode="json")},
        "seeds": {"s": request.seed.model_dump(mode="json")},
        "scenarios": [
            {
                "scenario_id": f"scenario_{index:03d}",
                "geology_id": "g",
                "seed_id": "s",
                "schedule": request.schedule.model_dump(mode="json"),
            }
            for index in range(200)
        ],
    }
    with TestClient(create_app(ShortFakeRunner)) as client:
        response = client.post("/predict/batch", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scenario_count"] == 200
    assert all(result["fields"] is None for result in body["results"])


def test_checkpoint_load_failure_fails_application_startup() -> None:
    def missing_checkpoint():
        raise FileNotFoundError("fixture checkpoint missing")

    with pytest.raises(FileNotFoundError, match="fixture checkpoint missing"):
        with TestClient(create_app(missing_checkpoint)):
            pass


def test_generated_openapi_contains_feature_001_paths() -> None:
    generated = create_app(FakeRunner).openapi()
    contract_path = Path(__file__).resolve().parents[2] / "specs" / "001-subsurface-surrogate" / "contracts" / "openapi.yaml"
    contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))

    assert generated["info"] == contract["info"]
    for path, path_item in contract["paths"].items():
        assert path in generated["paths"]
        for method, expected_operation in path_item.items():
            actual_operation = generated["paths"][path][method]
            assert actual_operation["summary"] == expected_operation["summary"]
            assert set(expected_operation["responses"]) <= set(actual_operation["responses"])
            for status, expected_response in expected_operation["responses"].items():
                assert actual_operation["responses"][status]["description"] == expected_response["description"]
            if "requestBody" in expected_operation:
                expected_schema = expected_operation["requestBody"]["content"]["application/json"]["schema"]
                actual_schema = actual_operation["requestBody"]["content"]["application/json"]["schema"]
                assert actual_schema == expected_schema

    for name, expected_schema in contract["components"]["schemas"].items():
        actual_schema = generated["components"]["schemas"][name]
        assert actual_schema["required"] == expected_schema["required"]
        for property_name, expected_property in expected_schema["properties"].items():
            for constraint in ("minLength", "minItems", "maxItems"):
                if constraint in expected_property:
                    assert actual_schema["properties"][property_name][constraint] == expected_property[constraint]
