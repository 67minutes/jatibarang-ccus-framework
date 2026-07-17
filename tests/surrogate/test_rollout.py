from __future__ import annotations

from pathlib import Path

import numpy as np

from jatibarang_ccus.surrogate.runner import load_surrogate
from jatibarang_ccus.surrogate.preprocessing import compile_request

from .helpers import request_from_mrst


def test_seed_rollout_shape_and_determinism() -> None:
    inputs = np.load(Path("tests/fixtures/surrogate/case_0016_inputs.npz"))
    expected = np.load(Path("tests/fixtures/surrogate/case_0016_expected.npz"))
    runner = load_surrogate()

    stage_sequence = expected["stage"][:3]
    first = runner.predict_seed(inputs["x_dyn"], inputs["x_static"], rollout_len=3, stage_sequence=stage_sequence)
    second = runner.predict_seed(inputs["x_dyn"], inputs["x_static"], rollout_len=3, stage_sequence=stage_sequence)

    assert first.pred.shape == (3, 4, 64, 64)
    assert first.pred_delta_norm.shape == (3, 2)
    np.testing.assert_allclose(first.pred, second.pred, atol=0.0, rtol=0.0)
    cumulative = np.cumsum(first.pred_delta_norm, axis=0)
    assert np.all(np.diff(cumulative, axis=0) >= 0.0)


def test_scheduled_rollout_exactly_matches_upstream_future_controls() -> None:
    runner = load_surrogate()
    compiled = compile_request(request_from_mrst(), runner.checkpoint["stats"])
    expected = np.load(Path("tests/fixtures/surrogate/case_0016_expected.npz"))
    prediction = runner.predict_compiled(compiled, max_forecast_steps=24)

    np.testing.assert_allclose(prediction.pred_normalized, expected["pred"], atol=0.0, rtol=0.0)
    np.testing.assert_allclose(prediction.pred_delta_normalized, expected["pred_delta_norm"], atol=0.0, rtol=0.0)
    expected_scale = np.asarray(
        [runner.checkpoint["stats"]["delta_oil_max"], runner.checkpoint["stats"]["delta_gas_max"]],
        dtype=np.float32,
    )
    expected_surface_delta = expected["pred_delta_norm"] * expected_scale[None, :] * 86400.0
    np.testing.assert_allclose(prediction.forecast_oil_delta_m3, expected_surface_delta[:, 0], atol=1e-6, rtol=0.0)
    np.testing.assert_allclose(prediction.forecast_gas_delta_m3, expected_surface_delta[:, 1], atol=1e-6, rtol=0.0)
    assert len(prediction.oil_delta_m3) == 8 + 24
    assert np.all(np.diff(prediction.cumulative_oil_m3) >= 0.0)
    assert np.all(np.diff(prediction.cumulative_gas_m3) >= 0.0)


def test_three_and_four_cycle_forecast_lengths() -> None:
    runner = load_surrogate()
    four_cycle = request_from_mrst()
    compiled_four = compile_request(four_cycle, runner.checkpoint["stats"])
    assert compiled_four.forecast_steps == 40

    schedule_three = four_cycle.schedule.model_copy(update={"cycles": 3})
    from jatibarang_ccus.surrogate.preprocessing import schedule_fingerprint

    seed_three = four_cycle.seed.model_copy(update={"schedule_fingerprint": schedule_fingerprint(schedule_three)})
    compiled_three = compile_request(
        four_cycle.model_copy(update={"schedule": schedule_three, "seed": seed_three}),
        runner.checkpoint["stats"],
    )
    assert compiled_three.forecast_steps == 28
