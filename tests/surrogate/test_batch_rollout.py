from __future__ import annotations

from dataclasses import replace

import numpy as np

from jatibarang_ccus.surrogate.preprocessing import compile_request
from jatibarang_ccus.surrogate.runner import load_surrogate

from .helpers import request_from_mrst


def test_microbatch_matches_individual_scheduled_rollouts() -> None:
    runner = load_surrogate()
    first = compile_request(request_from_mrst(), runner.checkpoint["stats"])
    second = replace(first, scenario_id="case_0016_copy")

    batch = runner.predict_compiled_batch([first, second], microbatch_size=2, max_forecast_steps=3)
    individual = runner.predict_compiled(first, max_forecast_steps=3)

    assert [item.scenario_id for item in batch] == ["case_0016", "case_0016_copy"]
    np.testing.assert_allclose(batch[0].pred_normalized, individual.pred_normalized, atol=1e-6, rtol=0.0)
    np.testing.assert_allclose(batch[1].pred_normalized, individual.pred_normalized, atol=1e-6, rtol=0.0)
    np.testing.assert_allclose(batch[0].pred_delta_normalized, individual.pred_delta_normalized, atol=1e-6, rtol=0.0)


def test_batch_is_bitwise_deterministic() -> None:
    runner = load_surrogate()
    compiled = compile_request(request_from_mrst(), runner.checkpoint["stats"])
    first = runner.predict_compiled_batch([compiled], max_forecast_steps=3)[0]
    second = runner.predict_compiled_batch([compiled], max_forecast_steps=3)[0]

    np.testing.assert_array_equal(first.pred_normalized, second.pred_normalized)
    np.testing.assert_array_equal(first.oil_delta_m3, second.oil_delta_m3)
