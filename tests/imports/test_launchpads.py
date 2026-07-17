from __future__ import annotations

from pathlib import Path

import pytest

from jatibarang_ccus.imports.launchpads import (
    LaunchpadBankError,
    load_launchpad_bank,
    write_launchpad_bank,
)
from jatibarang_ccus.imports.mrst import load_mrst_reservoir

CASE = Path("data/validation_cases/case_0016.mat")


def test_bank_round_trip(tmp_path: Path) -> None:
    imported = load_mrst_reservoir(CASE)
    bank_path = tmp_path / "model.launchpads.npz"
    digest = write_launchpad_bank(bank_path, {imported.seed.schedule_fingerprint: imported.seed})
    assert len(digest) == 64
    loaded = load_launchpad_bank(bank_path)
    assert set(loaded) == {imported.seed.schedule_fingerprint}
    pad = loaded[imported.seed.schedule_fingerprint]
    assert len(pad.frames) == 8
    assert pad.frames[0].pressure_bar.values == imported.seed.frames[0].pressure_bar.values


def test_rejects_wrong_format(tmp_path: Path) -> None:
    bogus = tmp_path / "bank.npz"
    bogus.write_bytes(b"zip? no")
    with pytest.raises(LaunchpadBankError):
        load_launchpad_bank(bogus)
