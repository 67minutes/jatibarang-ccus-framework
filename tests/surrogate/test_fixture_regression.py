from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from jatibarang_ccus.surrogate.runner import load_surrogate


FIXTURE_DIR = Path("tests/fixtures/surrogate")


def test_fixture_manifest_shapes() -> None:
    manifest = json.loads((FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8"))
    for case in manifest["cases"]:
        inputs = np.load(FIXTURE_DIR / case["inputs"])
        expected = np.load(FIXTURE_DIR / case["expected"])
        assert list(inputs["x_dyn"].shape) == case["x_dyn_shape"]
        assert list(inputs["x_static"].shape) == case["x_static_shape"]
        assert list(expected["pred"].shape) == case["pred_shape"]


def test_promoted_surrogate_reproduces_fixture_first_steps() -> None:
    runner = load_surrogate()
    manifest = json.loads((FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8"))
    for case in manifest["cases"]:
        inputs = np.load(FIXTURE_DIR / case["inputs"])
        expected = np.load(FIXTURE_DIR / case["expected"])
        pred, delta = runner.predict_one_step(
            inputs["x_dyn"],
            inputs["x_static"],
            stage=int(expected["stage"][0]),
        )
        np.testing.assert_allclose(pred, expected["pred"][0], atol=1e-6, rtol=0.0)
        np.testing.assert_allclose(delta, expected["pred_delta_norm"][0], atol=1e-6, rtol=0.0)

