from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from jatibarang_ccus.contracts import NetworkCostBreakdown
from jatibarang_ccus.surrogate.config import REPO_ROOT


CostCaseName = Literal["low", "base", "high"]


def _repo_path(path_value: str | Path) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else REPO_ROOT / path


def load_cost_basis(path_value: str | Path) -> dict[str, Any]:
    path = _repo_path(path_value)
    if not path.exists():
        raise FileNotFoundError(f"Pipeline cost basis is missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if set(payload.get("cases", {})) != {"low", "base", "high"}:
        raise ValueError("Pipeline cost basis must define low, base, and high cases.")
    payload["path"] = str(path)
    return payload


def annuity_present_value_factor(discount_rate: float, years: int) -> float:
    rate = float(discount_rate)
    count = int(years)
    if count <= 0:
        raise ValueError("Project life must be positive.")
    if rate == 0:
        return float(count)
    return (1.0 - (1.0 + rate) ** (-count)) / rate


def pipe_capex_usd(*, diameter_in: float, length_km: float, case: dict[str, float]) -> float:
    return float(case["pipe_usd_per_inch_m"]) * float(diameter_in) * float(length_km) * 1_000.0


def booster_capex_usd(*, power_kw: float, case: dict[str, float]) -> float:
    return float(case["booster_fixed_capex_usd"]) + float(case["booster_variable_capex_usd_per_kw"]) * float(power_kw)


def trucking_logistics_usd_per_tonne(case: dict[str, Any], distance_km: float) -> float:
    """Per-tonne trucking logistics (loading + liquefaction + reconditioning +
    distance transport), excluding the CO2 commodity supply price."""
    return (
        float(case["trucking_loading_usd_per_tonne"])
        + float(case["trucking_liquefaction_usd_per_tonne"])
        + float(case["trucking_reconditioning_usd_per_tonne"])
        + float(case["trucking_usd_per_tonne_km"]) * float(distance_km)
    )


def build_cost_breakdown(
    *,
    cost_basis: dict[str, Any],
    cost_case: CostCaseName,
    pipeline_capex_usd_value: float,
    booster_capex_usd_value: float,
    annual_booster_energy_usd: float,
    annual_mass_tonnes: float,
    discount_rate: float,
    project_life_years: int,
) -> NetworkCostBreakdown:
    case = cost_basis["cases"][cost_case]
    maintenance = float(pipeline_capex_usd_value) * float(case["pipeline_maintenance_fraction"])
    annual_opex = maintenance + float(annual_booster_energy_usd)
    pv_factor = annuity_present_value_factor(discount_rate, project_life_years)
    pv_transport = float(pipeline_capex_usd_value) + float(booster_capex_usd_value) + annual_opex * pv_factor
    pv_mass = max(float(annual_mass_tonnes) * pv_factor, 1e-9)
    levelized_transport = pv_transport / pv_mass
    supply = float(case["co2_supply_usd_per_tonne"])
    return NetworkCostBreakdown(
        cost_case=cost_case,
        cost_year=int(cost_basis["cost_year"]),
        pipeline_capex_usd=float(pipeline_capex_usd_value),
        booster_capex_usd=float(booster_capex_usd_value),
        annual_maintenance_usd=maintenance,
        annual_booster_energy_usd=float(annual_booster_energy_usd),
        annual_opex_usd=annual_opex,
        commodity_supply_usd_per_tonne=supply,
        present_value_lifecycle_cost_usd=pv_transport + supply * pv_mass,
        levelized_transport_usd_per_tonne=levelized_transport,
        levelized_delivered_usd_per_tonne=levelized_transport + supply,
        provenance={
            "status": cost_basis["status"],
            "pipeline_source": cost_basis["pipeline_source"],
            "equations": cost_basis["equations"],
            "citations": cost_basis["citations"],
            "path": cost_basis["path"],
        },
    )
