from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from jatibarang_ccus.imports import workflow_bank


def test_builds_one_real_common_fingerprint_bank_per_well(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fingerprint = "A" * 64
    catalog = {
        "entries": [
            {"well_id": "W01", "source_case_id": "case_1", "model_path": "one.npz"},
            {"well_id": "W02", "source_case_id": "case_2", "model_path": "two.npz"},
        ]
    }
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    output_entries = []
    for well, case in (("W01", "case_1"), ("W02", "case_2")):
        path = tmp_path / f"{well}.mat"
        path.write_bytes(well.encode())
        output_entries.append({
            "candidate_id": well,
            "source_case_id": case,
            "schedule_fingerprint": fingerprint,
            "output_file": path.name,
            "output_sha256": hashlib.sha256(path.read_bytes()).hexdigest().upper(),
        })
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({
        "completed_runs": 2,
        "requested_runs": 2,
        "raw_training_corpus_copied": False,
        "entries": output_entries,
    }), encoding="utf-8")
    monkeypatch.setattr(
        workflow_bank,
        "load_mrst_reservoir",
        lambda _path: SimpleNamespace(
            seed=SimpleNamespace(schedule_fingerprint=fingerprint),
        ),
    )

    def fake_bank(path: Path, entries: dict[str, object]) -> str:
        assert list(entries) == [fingerprint]
        path.write_bytes(b"bank")
        return "B" * 64

    monkeypatch.setattr(workflow_bank, "write_launchpad_bank", fake_bank)
    result = workflow_bank.build_workflow_launchpad_catalog(
        catalog_path,
        manifest_path,
        tmp_path / "runtime",
    )

    assert len(result["entries"]) == 2
    assert {item["bank_sha256"] for item in result["entries"]} == {"B" * 64}
    assert result["workflow_smoke"]["schedule_fingerprint"] == fingerprint
    assert result["workflow_smoke"]["raw_training_corpus_copied"] is False
    assert Path(result["catalog_path"]).is_file()


def test_rejects_incomplete_exporter_manifest(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"entries": []}), encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "completed_runs": 0,
        "requested_runs": 1,
        "raw_training_corpus_copied": False,
        "entries": [],
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="incomplete"):
        workflow_bank.build_workflow_launchpad_catalog(
            catalog,
            manifest,
            tmp_path / "runtime",
        )
