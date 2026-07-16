from __future__ import annotations

import argparse
from pathlib import Path
import time

import numpy as np

from .runner import load_surrogate


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a surrogate fixture smoke check.")
    parser.add_argument("--case", default="case_0016", help="Fixture case id, e.g. case_0016")
    args = parser.parse_args()

    fixture_dir = Path("tests/fixtures/surrogate")
    inputs = np.load(fixture_dir / f"{args.case}_inputs.npz")
    expected = np.load(fixture_dir / f"{args.case}_expected.npz")

    runner = load_surrogate()
    start = time.perf_counter()
    pred, delta = runner.predict_one_step(inputs["x_dyn"], inputs["x_static"], stage=int(expected["stage"][0]))
    elapsed = time.perf_counter() - start

    print(f"checkpoint={runner.model_info().checkpoint_run_name}")
    print(f"pred_shape={pred.shape}")
    print(f"delta_shape={delta.shape}")
    print(f"pred_max_abs_error={np.max(np.abs(pred - expected['pred'][0])):.8g}")
    print(f"delta_max_abs_error={np.max(np.abs(delta - expected['pred_delta_norm'][0])):.8g}")
    print(f"latency_seconds={elapsed:.6f}")


if __name__ == "__main__":
    main()

