from __future__ import annotations

from pathlib import Path

import pytest

from jatibarang_ccus.imports.mrst import MrstImportError, load_mrst_reservoir

CASE = Path("data/validation_cases/case_0016.mat")


def test_loads_case_0016_with_typed_payloads() -> None:
    imported = load_mrst_reservoir(CASE)
    geology = imported.geology
    assert geology.permeability_md.shape == (64, 64)
    assert geology.length_x_m == 900.0 and geology.length_y_m == 600.0
    assert imported.schedule.cycles in (3, 4)
    assert len(imported.seed.frames) == 8
    assert imported.seed.schedule_fingerprint
    assert imported.seed.source_class == "mrst_ground_truth"
    assert 0 <= imported.well_ij[0] < 64 and 0 <= imported.well_ij[1] < 64
    assert len(imported.sha256) == 64


def test_rejects_non_mat_file(tmp_path: Path) -> None:
    bogus = tmp_path / "model.mat"
    bogus.write_bytes(b"not an hdf5 file")
    with pytest.raises(MrstImportError):
        load_mrst_reservoir(bogus)
