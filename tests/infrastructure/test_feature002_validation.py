from __future__ import annotations

from pathlib import Path

from jatibarang_ccus.infrastructure.validation import REQUIRED_ARTIFACTS, validate_artifact_bundle


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_tracked_feature002_artifact_bundle_passes() -> None:
    output = REPO_ROOT / "paper" / "validation" / "feature002"
    assert REQUIRED_ARTIFACTS <= {item.name for item in output.iterdir()}
    result = validate_artifact_bundle(output)
    assert result["passed"]
    assert result["selected_well_count"] >= 1
