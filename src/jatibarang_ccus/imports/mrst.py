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
DERIVED_RESERVOIR_VERSION = 1


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


def _file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest().upper()


def _load_derived_reservoir(path: Path) -> MrstReservoirImport:
    try:
        with np.load(path, allow_pickle=False) as data:
            if int(data["meta/version"][0]) != DERIVED_RESERVOIR_VERSION:
                raise MrstImportError(
                    f"unsupported derived reservoir version in {path.name}"
                )
            geology = GeologyInput(
                permeability_md=_grid(data["geology/permeability_md"]),
                porosity_fraction=_grid(data["geology/porosity_fraction"]),
                structure_m=_grid(data["geology/structure_m"]),
                fracture_proxy=_grid(data["geology/fracture_proxy"]),
                barrier=_grid(data["geology/barrier"]),
                facies=_grid(data["geology/facies"]),
                well_mask=_grid(data["geology/well_mask"]),
                completion_mask=_grid(data["geology/completion_mask"]),
                anisotropy_ratio=float(data["geology/anisotropy_ratio"][0]),
                reservoir_temperature_c=float(data["geology/reservoir_temperature_c"][0]),
                length_x_m=float(data["geology/length_x_m"][0]),
                length_y_m=float(data["geology/length_y_m"][0]),
                thickness_m=float(data["geology/thickness_m"][0]),
            )
            schedule = OperatingSchedule(
                injection_rate_m3_day=float(data["schedule/injection_rate_m3_day"][0]),
                injection_reference_pressure_bar=float(
                    data["schedule/injection_reference_pressure_bar"][0]
                ),
                injection_reference_temperature_c=float(
                    data["schedule/injection_reference_temperature_c"][0]
                ),
                injection_duration_days=float(data["schedule/injection_duration_days"][0]),
                soak_duration_days=float(data["schedule/soak_duration_days"][0]),
                production_duration_days=float(data["schedule/production_duration_days"][0]),
                production_bhp_psi=float(data["schedule/production_bhp_psi"][0]),
                cycles=int(data["schedule/cycles"][0]),
            )
            frames_raw = data["seed/frames"]
            frames = [
                ReservoirState(
                    pressure_bar=_grid(frames_raw[index, 0]),
                    gas_saturation=_grid(frames_raw[index, 1]),
                    z_co2=_grid(frames_raw[index, 2]),
                )
                for index in range(8)
            ]
            seed = SeedHistory(
                initial_state=frames[0],
                frames=frames,
                oil_delta_m3=data["seed/oil_delta_m3"].tolist(),
                gas_delta_m3=data["seed/gas_delta_m3"].tolist(),
                source_class=str(data["seed/source_class"][0]),
                source_id=str(data["seed/source_id"][0]),
                schedule_fingerprint=str(data["seed/schedule_fingerprint"][0]),
            )
            well_raw = data["well_ij"].astype(int).reshape(-1)
            completion_raw = data["completion_ij"].astype(int)
    except MrstImportError:
        raise
    except Exception as exc:
        raise MrstImportError(
            f"not a readable derived MRST reservoir: {path.name}: {exc}"
        ) from exc
    return MrstReservoirImport(
        geology=geology,
        seed=seed,
        schedule=schedule,
        well_ij=(int(well_raw[0]), int(well_raw[1])),
        completion_ij=[tuple(map(int, row)) for row in completion_raw],
        targets={},
        sha256=_file_sha256(path),
    )


def load_mrst_reservoir(path: Path) -> MrstReservoirImport:
    path = Path(path)
    if not path.exists():
        raise MrstImportError(f"reservoir model file is missing: {path}")
    if path.suffix.lower() == ".npz":
        return _load_derived_reservoir(path)
    digest = _file_sha256(path)
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
            "dt_days": dt,
            "stage_labels": stages,
        },
        sha256=digest,
    )


def write_derived_reservoir(source: Path, target: Path) -> str:
    """Write only runtime static fields and the real eight-frame MRST seed.

    The full simulation target trajectory is intentionally omitted, keeping the
    raw training corpus in the upstream repository while retaining everything
    the screening runtime and pre-run viewport require.
    """

    imported = load_mrst_reservoir(source)
    geology = imported.geology
    schedule = imported.schedule
    frames = np.empty((8, 3, 64, 64), dtype=np.float32)
    for index, frame in enumerate(imported.seed.frames):
        frames[index, 0] = frame.pressure_bar.as_array()
        frames[index, 1] = frame.gas_saturation.as_array()
        frames[index, 2] = frame.z_co2.as_array()
    payload = {
        "meta/version": np.array([DERIVED_RESERVOIR_VERSION], dtype=np.int64),
        "meta/source_sha256": np.array([imported.sha256], dtype=np.str_),
        "meta/source_file": np.array([Path(source).name], dtype=np.str_),
        "geology/permeability_md": geology.permeability_md.as_array().astype(np.float32),
        "geology/porosity_fraction": geology.porosity_fraction.as_array().astype(np.float32),
        "geology/structure_m": geology.structure_m.as_array().astype(np.float32),
        "geology/fracture_proxy": geology.fracture_proxy.as_array().astype(np.float32),
        "geology/barrier": geology.barrier.as_array().astype(np.float32),
        "geology/facies": geology.facies.as_array().astype(np.float32),
        "geology/well_mask": geology.well_mask.as_array().astype(np.float32),
        "geology/completion_mask": geology.completion_mask.as_array().astype(np.float32),
        "geology/anisotropy_ratio": np.array([geology.anisotropy_ratio]),
        "geology/reservoir_temperature_c": np.array([geology.reservoir_temperature_c]),
        "geology/length_x_m": np.array([geology.length_x_m]),
        "geology/length_y_m": np.array([geology.length_y_m]),
        "geology/thickness_m": np.array([geology.thickness_m]),
        "schedule/injection_rate_m3_day": np.array([schedule.injection_rate_m3_day]),
        "schedule/injection_reference_pressure_bar": np.array(
            [schedule.injection_reference_pressure_bar]
        ),
        "schedule/injection_reference_temperature_c": np.array(
            [schedule.injection_reference_temperature_c]
        ),
        "schedule/injection_duration_days": np.array([schedule.injection_duration_days]),
        "schedule/soak_duration_days": np.array([schedule.soak_duration_days]),
        "schedule/production_duration_days": np.array([schedule.production_duration_days]),
        "schedule/production_bhp_psi": np.array([schedule.production_bhp_psi]),
        "schedule/cycles": np.array([schedule.cycles], dtype=np.int64),
        "seed/frames": frames,
        "seed/oil_delta_m3": np.asarray(imported.seed.oil_delta_m3, dtype=np.float32),
        "seed/gas_delta_m3": np.asarray(imported.seed.gas_delta_m3, dtype=np.float32),
        "seed/source_class": np.array([imported.seed.source_class], dtype=np.str_),
        "seed/source_id": np.array([imported.seed.source_id], dtype=np.str_),
        "seed/schedule_fingerprint": np.array(
            [imported.seed.schedule_fingerprint], dtype=np.str_
        ),
        "well_ij": np.asarray(imported.well_ij, dtype=np.int64),
        "completion_ij": np.asarray(imported.completion_ij, dtype=np.int64),
    }
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(target, **payload)
    return _file_sha256(target)
