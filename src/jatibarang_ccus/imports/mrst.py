"""MRST reservoir-model import: one .mat realization -> typed payloads.

One export = one single-well sector simulation. It supplies the geology, the
native operating schedule, and that schedule's eight-frame launch pad. It
carries no georeference and no additional wells (spec §3, §7).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np

from ..surrogate.preprocessing import schedule_fingerprint
from ..surrogate.schemas import (
    GeologyInput,
    Grid2D,
    OperatingSchedule,
    ReservoirState,
    SeedHistory,
)

SECONDS_PER_DAY = 86400.0

ARRAY_KEYS = (
    "pressure", "gas_sat", "z_co2", "oil_sat", "perm_map", "poro_map",
    "structure_map", "fracture_proxy_map", "barrier_map", "facies_map",
    "well_mask", "completion_mask",
)


class MrstImportError(ValueError):
    """The file is not a readable MRST reservoir export."""


@dataclass(frozen=True)
class MrstReservoirImport:
    geology: GeologyInput
    seed: SeedHistory
    schedule: OperatingSchedule
    well_ij: tuple[int, int]
    completion_ij: list[tuple[int, int]]
    targets: dict[str, np.ndarray]
    sha256: str


def _grid(values: np.ndarray) -> Grid2D:
    return Grid2D.from_array(np.asarray(values, dtype=np.float32))


def load_mrst_reservoir(path: Path) -> MrstReservoirImport:
    path = Path(path)
    if not path.exists():
        raise MrstImportError(f"reservoir model file is missing: {path}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
    try:
        with h5py.File(path, "r") as handle:
            params = {
                key: float(np.asarray(handle["params"][key]).reshape(-1)[0])
                for key in handle["params"].keys()
            }
            arrays = {
                key: np.asarray(handle[key], dtype=np.float32) for key in ARRAY_KEYS
            }
            dt = np.asarray(handle["dt_days"], dtype=np.float32).reshape(-1)
            stages = np.rint(np.asarray(handle["stage_labels"])).astype(np.int64).reshape(-1)
            oil_rate = np.asarray(handle["well_oil_rate"], dtype=np.float32).reshape(-1)
            gas_rate = np.asarray(handle["well_gas_rate"], dtype=np.float32).reshape(-1)
            well_ij_raw = np.rint(np.asarray(handle["well_ij"])).astype(int).reshape(-1)
            completion_raw = np.rint(np.asarray(handle["completion_ij"])).astype(int)
    except (OSError, KeyError) as exc:
        raise MrstImportError(f"not a readable MRST export: {path.name}: {exc}") from exc

    geology = GeologyInput(
        permeability_md=_grid(np.power(10.0, arrays["perm_map"])),
        porosity_fraction=_grid(arrays["poro_map"]),
        structure_m=_grid(arrays["structure_map"]),
        fracture_proxy=_grid(arrays["fracture_proxy_map"]),
        barrier=_grid(arrays["barrier_map"]),
        facies=_grid(arrays["facies_map"]),
        well_mask=_grid(arrays["well_mask"]),
        completion_mask=_grid(arrays["completion_mask"]),
        anisotropy_ratio=params["anisotropy_ratio"],
        reservoir_temperature_c=91.0,
        length_x_m=900.0,
        length_y_m=600.0,
        thickness_m=6.0,
    )
    schedule = OperatingSchedule(
        injection_rate_m3_day=params["inj_rate_surf"],
        injection_duration_days=params["t_inj_days"],
        soak_duration_days=params["t_soak_days"],
        production_duration_days=params["t_prod_days"],
        production_bhp_psi=params["prod_bhp_psi"],
        cycles=int(params["n_cycles"]),
    )
    frames = [
        ReservoirState(
            pressure_bar=_grid(arrays["pressure"][index]),
            gas_saturation=_grid(arrays["gas_sat"][index]),
            z_co2=_grid(arrays["z_co2"][index]),
        )
        for index in range(8)
    ]
    produce = (stages == 3).astype(np.float32)
    oil_delta = np.abs(oil_rate) * dt * SECONDS_PER_DAY * produce
    gas_delta = np.abs(gas_rate) * dt * SECONDS_PER_DAY * produce
    seed = SeedHistory(
        # The exports do not contain the pre-operation state. The first exported
        # frame is retained as the explicit baseline and disclosed in the
        # scientific caveats.
        initial_state=frames[0],
        frames=frames,
        oil_delta_m3=oil_delta[:8].tolist(),
        gas_delta_m3=gas_delta[:8].tolist(),
        source_class="mrst_ground_truth",
        source_id=path.stem,
        schedule_fingerprint=schedule_fingerprint(schedule),
    )
    completion = [
        (int(completion_raw[0, k]) - 1, int(completion_raw[1, k]) - 1)
        for k in range(completion_raw.shape[1])
    ]
    return MrstReservoirImport(
        geology=geology,
        seed=seed,
        schedule=schedule,
        well_ij=(int(well_ij_raw[0]) - 1, int(well_ij_raw[1]) - 1),
        completion_ij=completion,
        targets={
            "pressure": arrays["pressure"],
            "gas_sat": arrays["gas_sat"],
            "z_co2": arrays["z_co2"],
            "oil_sat": arrays["oil_sat"],
            "oil_delta_m3": oil_delta,
            "gas_delta_m3": gas_delta,
        },
        sha256=digest,
    )
