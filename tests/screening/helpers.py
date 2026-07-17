from __future__ import annotations

from dataclasses import asdict

import numpy as np

from jatibarang_ccus.contracts import (
    CO2Source,
    Coordinate,
    EconomicAssumptions,
    EconomicProvenance,
    FiscalCase,
)
from jatibarang_ccus.infrastructure.economic_adapters import carbon_prices_from_basis, load_economic_basis
from jatibarang_ccus.surrogate.preprocessing import schedule_fingerprint
from jatibarang_ccus.surrogate.runner import ModelInfo, ScheduledPrediction
from jatibarang_ccus.surrogate.schemas import (
    GeologyInput,
    Grid2D,
    OperatingSchedule,
    ReservoirState,
    SeedHistory,
)


STATS = {
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


def grid(value: float) -> Grid2D:
    return Grid2D(values=[value] * 4096)


def geology() -> GeologyInput:
    return GeologyInput(
        permeability_md=grid(100.0),
        porosity_fraction=grid(0.2),
        structure_m=grid(0.0),
        fracture_proxy=grid(0.2),
        barrier=grid(0.0),
        facies=grid(1.0),
        well_mask=grid(0.0),
        completion_mask=Grid2D(values=[1.0] + [0.0] * 4095),
        anisotropy_ratio=2.0,
        reservoir_temperature_c=91.0,
        length_x_m=900.0,
        length_y_m=600.0,
        thickness_m=6.0,
    )


def schedule(*, rate: float = 9000.0, cycles: int = 3) -> OperatingSchedule:
    return OperatingSchedule(
        injection_rate_m3_day=rate,
        injection_duration_days=45.0,
        soak_duration_days=30.0,
        production_duration_days=190.0,
        production_bhp_psi=675.0,
        cycles=cycles,
    )


def seed(active_schedule: OperatingSchedule | None = None) -> SeedHistory:
    active_schedule = active_schedule or schedule()
    state = ReservoirState(pressure_bar=grid(55.0), gas_saturation=grid(0.01), z_co2=grid(0.02))
    return SeedHistory(
        initial_state=state,
        frames=[state] * 8,
        oil_delta_m3=[1.0] * 8,
        gas_delta_m3=[2.0] * 8,
        source_class="derived_seed",
        source_id="fixture-seed",
        schedule_fingerprint=schedule_fingerprint(active_schedule),
    )


def source() -> CO2Source:
    return CO2Source(
        id="SRC",
        name="Fixture source",
        location=Coordinate(latitude=-6.57, longitude=107.75),
        capacity_tonnes_per_year=500_000.0,
        max_mass_flow_kg_s=600.0,
        outlet_pressure_bar=120.0,
        outlet_temperature_c=27.0,
        co2_purity=0.95,
    )


def economic_dimensions():
    basis = load_economic_basis()
    assumptions = EconomicAssumptions(
        version=basis["version"],
        currency_basis=basis["currency_basis"],
        discount_rate=basis["discount_rate"],
        oil_price_usd_per_bbl=basis["oil_price_usd_per_bbl"],
        gas_price_usd_per_mmbtu=basis["gas_price_usd_per_mmbtu"],
        gas_heating_value_mmbtu_per_std_m3=basis["gas_heating_value_mmbtu_per_std_m3"],
        lifting_cost_usd_per_bbl=basis["lifting_cost_usd_per_bbl"],
        workover_cost_usd_per_cycle=basis["workover_cost_usd_per_cycle"],
        mrv_cost_usd_per_tonne=basis["mrv_cost_usd_per_tonne"],
        certification_haircut=basis["certification_haircut"],
        storage_divergence_threshold_fraction_of_injected=basis["storage_divergence_threshold_fraction_of_injected"],
    )
    provenance = [EconomicProvenance(source_class="economic_assumption", source_id="fixture")]
    fiscal = [FiscalCase(case_id="pre_tax", mode="pre_tax", provenance=provenance)]
    return carbon_prices_from_basis(basis), fiscal, assumptions


class FakeRunner:
    def __init__(self) -> None:
        self.checkpoint = {"stats": STATS}
        self.batch_calls = 0
        self.compiled_count = 0

    def info_dict(self) -> dict:
        return asdict(self.model_info())

    def model_info(self) -> ModelInfo:
        return ModelInfo(
            checkpoint_path="fixture.pt",
            checkpoint_sha256="A" * 64,
            checkpoint_run_name="fixture",
            output_contract="production_v2",
            tin=8,
            stored_dynamic_channels=20,
            forward_dynamic_channels=13,
            static_channels=12,
            model_kwargs={},
        )

    def predict_compiled_batch(self, compiled, *, microbatch_size=16):
        self.batch_calls += 1
        self.compiled_count += len(compiled)
        return [self._prediction(item) for item in compiled]

    def _prediction(self, compiled) -> ScheduledPrediction:
        horizon = compiled.forecast_steps
        pred = np.zeros((horizon, 4, 64, 64), dtype=np.float32)
        pred[:, 0] = 0.1
        pred[:, 1] = 0.01
        pred[:, 2] = 0.02
        pred[:, 3] = 0.5
        oil_forecast = np.full(horizon, 5.0, dtype=np.float32)
        gas_forecast = np.full(horizon, 10.0, dtype=np.float32)
        oil = np.concatenate([compiled.seed_oil_delta_m3, oil_forecast])
        gas = np.concatenate([compiled.seed_gas_delta_m3, gas_forecast])
        return ScheduledPrediction(
            scenario_id=compiled.scenario_id,
            pred_normalized=pred,
            pred_pressure_bar=np.full((horizon, 64, 64), 55.0, dtype=np.float32),
            pred_delta_normalized=np.zeros((horizon, 2), dtype=np.float32),
            forecast_oil_delta_m3=oil_forecast,
            forecast_gas_delta_m3=gas_forecast,
            oil_delta_m3=oil,
            gas_delta_m3=gas,
            cumulative_oil_m3=np.cumsum(oil),
            cumulative_gas_m3=np.cumsum(gas),
            stages=compiled.stages.copy(),
        )
