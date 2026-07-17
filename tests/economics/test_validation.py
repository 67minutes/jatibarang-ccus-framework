from __future__ import annotations

import json

from jsonschema import validate

from jatibarang_ccus.infrastructure.economic_adapters import load_economic_basis
from jatibarang_ccus.infrastructure.economic_validation import (
    DEFAULT_SCHEMA,
    build_reference_request,
    verify_artifact_manifest,
    write_artifact_manifest,
)
from jatibarang_ccus.infrastructure.economics import evaluate_economic_batch


def test_reference_request_and_result_validate_against_schema():
    request = build_reference_request(load_economic_basis())
    result = evaluate_economic_batch(request)
    schema = json.loads(DEFAULT_SCHEMA.read_text(encoding="utf-8"))
    validate(request.model_dump(mode="json"), schema)
    validate(result.model_dump(mode="json"), schema)
    assert result.accounting_verdict == "PASS"


def test_sha256_manifest_detects_tampering(tmp_path):
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("original", encoding="utf-8")
    manifest = write_artifact_manifest(tmp_path)
    assert verify_artifact_manifest(manifest) == []
    artifact.write_text("changed!", encoding="utf-8")
    assert verify_artifact_manifest(manifest) == ["sha256:artifact.txt"]
