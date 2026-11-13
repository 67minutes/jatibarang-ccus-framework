from __future__ import annotations

import json
from pathlib import Path

import pytest

from jatibarang_ccus.imports import reservoir_catalog


def _design(path: Path, geologies: list[dict[str, str]]) -> Path:
    path.write_text(
        json.dumps({"design_id": "design-a", "design_sha256": "A" * 64, "geologies": geologies}),
        encoding="utf-8",
    )
    return path


def test_builds_frontend_catalog_with_derived_only_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    for name in ("case_1.mat", "case_2.mat"):
        (source / name).write_bytes(b"upstream")

    def fake_writer(source_path: Path, target: Path) -> str:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"derived")
        return "B" * 64

    monkeypatch.setattr(reservoir_catalog, "write_derived_reservoir", fake_writer)
    result = reservoir_catalog.build_reservoir_catalog(
        _design(tmp_path / "design.json", [
            {"candidate_id": "W01", "source_case_id": "case_1", "source_output_file": "case_1.mat"},
            {"candidate_id": "W02", "source_case_id": "case_2", "source_output_file": "case_2.mat"},
        ]),
        source,
        tmp_path / "output",
    )

    assert result["raw_training_corpus_copied"] is False
    assert result["artifact_policy"] == "derived_static_maps_and_eight_frame_seed_only"
    assert [item["well_id"] for item in result["entries"]] == ["W01", "W02"]
    assert all(item["model_path"].endswith(".reservoir.npz") for item in result["entries"])
    assert Path(result["catalog_path"]).is_file()


def test_rejects_noncontiguous_or_unsafe_design_entries(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    with pytest.raises(ValueError, match="expected W01"):
        reservoir_catalog.build_reservoir_catalog(
            _design(tmp_path / "gap.json", [
                {"candidate_id": "W02", "source_case_id": "case_2", "source_output_file": "case_2.mat"},
            ]),
            source,
            tmp_path / "output",
        )
    with pytest.raises(ValueError, match="unsafe"):
        reservoir_catalog.build_reservoir_catalog(
            _design(tmp_path / "unsafe.json", [
                {"candidate_id": "W01", "source_case_id": "case_1", "source_output_file": "../case_1.mat"},
            ]),
            source,
            tmp_path / "output",
        )
