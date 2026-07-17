from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from jatibarang_ccus.surrogate.preprocessing import build_control_timeline, compile_request, schedule_fingerprint
from jatibarang_ccus.surrogate.runner import load_surrogate

from .helpers import request_from_mrst


def test_schedule_has_training_discretization_and_boundaries() -> None:
    request = request_from_mrst()
    runner = load_surrogate()
    controls, dt, stages, cycles, elapsed = build_control_timeline(request.schedule, runner.checkpoint["stats"])

    assert len(stages) == request.schedule.cycles * 12
    np.testing.assert_array_equal(stages[:12], [1, 1, 1, 1, 2, 2, 3, 3, 3, 3, 3, 3])
    np.testing.assert_array_equal(cycles[:13], [1] * 12 + [2])
    assert controls.shape == (request.schedule.cycles * 12, 20)
    assert controls[3, 11] == pytest.approx(0.875)
    assert controls[4, 11] == pytest.approx(0.25)
    assert controls[5, 12] == pytest.approx(0.25)
    assert elapsed[-1] == pytest.approx(float(np.sum(dt)))


@pytest.mark.parametrize("case_id", ["case_0016", "case_0115", "case_0197"])
def test_physical_compiler_matches_upstream_fixture(case_id: str) -> None:
    fixture_path = Path(f"tests/fixtures/surrogate/{case_id}_inputs.npz")
    if not Path(f"data/validation_cases/{case_id}.mat").exists():
        pytest.skip("local MRST validation file is not available")
    request = request_from_mrst(case_id)
    runner = load_surrogate()
    compiled = compile_request(request, runner.checkpoint["stats"])
    expected = np.load(fixture_path)

    np.testing.assert_allclose(compiled.x_dynamic_seed, expected["x_dyn"], atol=1e-6, rtol=0.0)
    np.testing.assert_allclose(compiled.x_static, expected["x_static"], atol=1e-6, rtol=0.0)


def test_out_of_range_values_are_flagged_not_rejected() -> None:
    request = request_from_mrst()
    schedule = request.schedule.model_copy(update={"injection_rate_m3_day": 12000.0})
    seed = request.seed.model_copy(update={"schedule_fingerprint": schedule_fingerprint(schedule)})
    updated = request.model_copy(update={"schedule": schedule, "seed": seed})
    compiled = compile_request(updated, load_surrogate().checkpoint["stats"])
    flag = next(item for item in compiled.extrapolation_flags if item.quantity == "injection_rate_m3_day")
    assert flag.is_extrapolation is True


def test_seed_schedule_fingerprint_mismatch_is_rejected() -> None:
    request = request_from_mrst()
    bad_seed = request.seed.model_copy(update={"schedule_fingerprint": "0" * 64})
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        compile_request(request.model_copy(update={"seed": bad_seed}), load_surrogate().checkpoint["stats"])
