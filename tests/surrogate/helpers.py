from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np

from jatibarang_ccus.surrogate.preprocessing import schedule_fingerprint
from jatibarang_ccus.surrogate.schemas import (
    GeologyInput,
    Grid2D,
    OperatingSchedule,
    PredictRequest,
    ReservoirState,
    SeedHistory,
)


VALIDATION_DIR = Path("data/validation_cases")


def _grid(values: np.ndarray) -> Grid2D:
    return Grid2D.from_array(np.asarray(values, dtype=np.float32))


def request_from_mrst(case_id: str = "case_0016") -> PredictRequest:
    path = VALIDATION_DIR / f"{case_id}.mat"
    if not path.exists():
        raise FileNotFoundError(path)
    with h5py.File(path, "r") as handle:
        params = {key: float(np.asarray(handle["params"][key]).reshape(-1)[0]) for key in handle["params"].keys()}
        pressure = np.asarray(handle["pressure"], dtype=np.float32)
        gas = np.asarray(handle["gas_sat"], dtype=np.float32)
        z_co2 = np.asarray(handle["z_co2"], dtype=np.float32)
        dt = np.asarray(handle["dt_days"], dtype=np.float32).reshape(-1)
        stages = np.asarray(handle["stage_labels"], dtype=np.int64).reshape(-1)
        oil_rate = np.asarray(handle["well_oil_rate"], dtype=np.float32).reshape(-1)
        gas_rate = np.asarray(handle["well_gas_rate"], dtype=np.float32).reshape(-1)
        geology = GeologyInput(
            permeability_md=_grid(np.power(10.0, np.asarray(handle["perm_map"], dtype=np.float32))),
            porosity_fraction=_grid(np.asarray(handle["poro_map"])),
            structure_m=_grid(np.asarray(handle["structure_map"])),
            fracture_proxy=_grid(np.asarray(handle["fracture_proxy_map"])),
            barrier=_grid(np.asarray(handle["barrier_map"])),
            facies=_grid(np.asarray(handle["facies_map"])),
            well_mask=_grid(np.asarray(handle["well_mask"])),
            completion_mask=_grid(np.asarray(handle["completion_mask"])),
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
            pressure_bar=_grid(pressure[index]),
            gas_saturation=_grid(gas[index]),
            z_co2=_grid(z_co2[index]),
        )
        for index in range(8)
    ]
    produce = (stages[:8] == 3).astype(np.float32)
    seed = SeedHistory(
        initial_state=frames[0],
        frames=frames,
        oil_delta_m3=(np.abs(oil_rate[:8]) * dt[:8] * 86400.0 * produce).tolist(),
        gas_delta_m3=(np.abs(gas_rate[:8]) * dt[:8] * 86400.0 * produce).tolist(),
        source_class="mrst_ground_truth",
        source_id=case_id,
        schedule_fingerprint=schedule_fingerprint(schedule),
    )
    return PredictRequest(scenario_id=case_id, geology=geology, schedule=schedule, seed=seed)
