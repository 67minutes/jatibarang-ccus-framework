from __future__ import annotations

import json

from jatibarang_ccus.screening.validation import _artifact_manifest, verify_artifacts


def test_artifact_manifest_detects_tampering(tmp_path) -> None:
    (tmp_path / "result.json").write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
    _artifact_manifest(tmp_path)
    assert verify_artifacts(tmp_path) == []

    (tmp_path / "result.json").write_text(json.dumps({"status": "changed"}), encoding="utf-8")
    assert verify_artifacts(tmp_path) == ["SHA-256 mismatch: result.json"]
