from __future__ import annotations

import json

import pytest

from jatibarang_ccus.surrogate.config import CHANNEL_CONTRACT, PROMOTED_CHECKPOINT, PROMOTED_CHECKPOINT_SHA256
from jatibarang_ccus.surrogate.metadata import ACCURACY_BANDS, ACCURACY_METADATA_PATH
from jatibarang_ccus.surrogate.runner import load_surrogate, verify_checkpoint


EXPECTED_STATS = {
    "pressure_mean": 53.994626286438965,
    "pressure_std": 8.33254043764201,
    "perm_mean": 1.6158922562004245,
    "perm_std": 0.5498339937243941,
    "poro_mean": 0.1945479605945279,
    "poro_std": 0.029472247869062187,
    "dt_max": 34.86787033081055,
    "structure_abs_max": 1.7161699533462524,
    "inj_rate_max": 9982.275106013587,
    "prod_bhp_max": 699.6446495360955,
    "n_cycles_max": 4.0,
    "anisotropy_max": 2.991920365879958,
    "delta_oil_max": 0.028243480250239372,
    "delta_gas_max": 0.005858070682734251,
}


def test_promoted_checkpoint_sha256_matches() -> None:
    digest = verify_checkpoint(PROMOTED_CHECKPOINT)
    assert digest == PROMOTED_CHECKPOINT_SHA256


def test_model_info_reports_locked_contract() -> None:
    runner = load_surrogate()
    info = runner.model_info()
    assert info.output_contract == CHANNEL_CONTRACT.output_contract
    assert info.tin == CHANNEL_CONTRACT.tin
    assert info.stored_dynamic_channels == 20
    assert info.forward_dynamic_channels == 13
    assert info.static_channels == 12
    assert info.model_kwargs["use_transition_features"] is False
    assert info.model_kwargs["use_stage_progress_features"] is True


def test_checkpoint_normalization_statistics_match_promoted_identity() -> None:
    stats = load_surrogate().checkpoint["stats"]
    assert set(EXPECTED_STATS) <= set(stats)
    for name, expected in EXPECTED_STATS.items():
        assert float(stats[name]) == pytest.approx(expected, rel=0.0, abs=1e-12)


def test_accuracy_bands_are_loaded_from_the_derived_metadata_artifact() -> None:
    artifact = json.loads(ACCURACY_METADATA_PATH.read_text(encoding="utf-8"))
    assert set(ACCURACY_BANDS) == {"one_step", "t_plus_5", "t_plus_10", "t_plus_11", "last_24"}
    assert ACCURACY_BANDS["last_24"].pressure_r2 == artifact["bands"]["last_24"]["pressure_r2"]
