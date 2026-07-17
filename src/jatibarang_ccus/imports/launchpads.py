"""Launch-pad bank v1: schedule-fingerprinted warm-start histories in one NPZ.

Layout (all float32 unless noted):
  meta/version: [1]
  meta/fingerprints: array[str]                    (N fingerprints)
  <fp>/frames: (8, 3, 64, 64)                       pressure_bar, gas_saturation, z_co2
  <fp>/oil_delta_m3, <fp>/gas_delta_m3: (8,)
  <fp>/source_id: array[str] length 1
Never generated from thin air: banks are written from MRST-derived SeedHistory
objects only (spec §9 honesty rule).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from ..surrogate.schemas import Grid2D, ReservoirState, SeedHistory

VERSION = 1


class LaunchpadBankError(ValueError):
    """The file is not a readable launch-pad bank."""


def _frames_array(seed: SeedHistory) -> np.ndarray:
    out = np.empty((8, 3, 64, 64), dtype=np.float32)
    for index, frame in enumerate(seed.frames):
        out[index, 0] = np.asarray(frame.pressure_bar.as_array(), dtype=np.float32)
        out[index, 1] = np.asarray(frame.gas_saturation.as_array(), dtype=np.float32)
        out[index, 2] = np.asarray(frame.z_co2.as_array(), dtype=np.float32)
    return out


def write_launchpad_bank(path: Path, entries: dict[str, SeedHistory]) -> str:
    payload: dict[str, np.ndarray] = {
        "meta/version": np.array([VERSION]),
        "meta/fingerprints": np.array(sorted(entries), dtype=np.str_),
    }
    for fingerprint in sorted(entries):
        seed = entries[fingerprint]
        payload[f"{fingerprint}/frames"] = _frames_array(seed)
        payload[f"{fingerprint}/oil_delta_m3"] = np.asarray(seed.oil_delta_m3, dtype=np.float32)
        payload[f"{fingerprint}/gas_delta_m3"] = np.asarray(seed.gas_delta_m3, dtype=np.float32)
        payload[f"{fingerprint}/source_id"] = np.array([seed.source_id], dtype=np.str_)
    np.savez_compressed(path, **payload)
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()


def load_launchpad_bank(path: Path) -> dict[str, SeedHistory]:
    path = Path(path)
    try:
        with np.load(path, allow_pickle=False) as data:
            if int(data["meta/version"][0]) != VERSION:
                raise LaunchpadBankError(f"unsupported bank version in {path.name}")
            result: dict[str, SeedHistory] = {}
            for fingerprint in [str(v) for v in data["meta/fingerprints"]]:
                frames_raw = data[f"{fingerprint}/frames"]
                frames = [
                    ReservoirState(
                        pressure_bar=Grid2D.from_array(frames_raw[i, 0]),
                        gas_saturation=Grid2D.from_array(frames_raw[i, 1]),
                        z_co2=Grid2D.from_array(frames_raw[i, 2]),
                    )
                    for i in range(8)
                ]
                result[fingerprint] = SeedHistory(
                    initial_state=frames[0],
                    frames=frames,
                    oil_delta_m3=data[f"{fingerprint}/oil_delta_m3"].tolist(),
                    gas_delta_m3=data[f"{fingerprint}/gas_delta_m3"].tolist(),
                    source_class="mrst_ground_truth",
                    source_id=str(data[f"{fingerprint}/source_id"][0]),
                    schedule_fingerprint=fingerprint,
                )
            return result
    except LaunchpadBankError:
        raise
    except Exception as exc:  # zipfile/keys/shape errors
        raise LaunchpadBankError(f"not a readable launch-pad bank: {path.name}: {exc}") from exc
