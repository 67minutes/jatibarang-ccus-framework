from __future__ import annotations

from pathlib import Path

import pytest

from jatibarang_ccus.screening.prediction_cache import PredictionCache
from jatibarang_ccus.screening.presets import materialize_inline_scenarios
from jatibarang_ccus.surrogate.postprocessing import build_prediction_result
from jatibarang_ccus.surrogate.preprocessing import compile_request
from tests.screening.helpers import FakeRunner
from tests.screening.test_orchestration_integration import inline_request


def compact_prediction():
    runner = FakeRunner()
    scenario = materialize_inline_scenarios(inline_request())[0]
    compiled = compile_request(
        scenario.predict_request,
        runner.checkpoint["stats"],
    )
    raw = runner.predict_compiled_batch([compiled], microbatch_size=1)[0]
    return build_prediction_result(
        compiled,
        raw,
        runner,
        include_fields=False,
    )


def test_prediction_cache_round_trips_and_rejects_conflicts(
    tmp_path: Path,
) -> None:
    path = tmp_path / "predictions.sqlite3"
    identity = {
        "checkpoint_sha256": "A" * 64,
        "preset_design_sha256": "B" * 64,
    }
    prediction = compact_prediction()
    with PredictionCache(path, identity=identity) as cache:
        cache["fingerprint"] = prediction
        assert cache["fingerprint"] == prediction
        assert list(cache) == ["fingerprint"]
        assert len(cache) == 1
        assert len(cache.content_sha256()) == 64

    with PredictionCache(path, identity=identity) as resumed:
        assert resumed["fingerprint"] == prediction

    with pytest.raises(ValueError, match="identity"):
        PredictionCache(
            path,
            identity={
                "checkpoint_sha256": "C" * 64,
                "preset_design_sha256": "B" * 64,
            },
        )


def test_prediction_cache_detects_payload_tampering(tmp_path: Path) -> None:
    path = tmp_path / "predictions.sqlite3"
    cache = PredictionCache(path, identity={"basis": "test"})
    cache["fingerprint"] = compact_prediction()
    cache._connection.execute(
        """
        UPDATE predictions
        SET payload_sha256 = ?
        WHERE fingerprint = ?
        """,
        ("0" * 64, "fingerprint"),
    )
    cache._connection.commit()
    with pytest.raises(ValueError, match="hash mismatch"):
        cache["fingerprint"]
    cache.close()
