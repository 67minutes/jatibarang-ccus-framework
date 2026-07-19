"""Throughput crossover for CO2 supply modes (Figure 5c input).

Pure cost-basis arithmetic: no MRST, no surrogate, no scenario bank. Booster
costs are deliberately excluded (screening lower bound that favors pipelines,
so a trucking-wins conclusion is conservative). Commodity supply is excluded
from every mode (pure transport comparison on the levelized_transport basis).
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from jatibarang_ccus.infrastructure.costs import (
    annuity_present_value_factor,
    load_cost_basis,
    pipe_capex_usd,
    trucking_logistics_usd_per_tonne,
)
from jatibarang_ccus.infrastructure.hydraulics import _diameter_flow_kg_s
from jatibarang_ccus.phase1.case_study import DEFAULT_ASSUMPTIONS, load_assumptions

SECONDS_PER_YEAR = 365.0 * 86_400.0


def _diameter_flow_window_kg_s(pipe: dict, diameter_in: float) -> tuple[float, float]:
    anchors = [float(v) for v in pipe["pressure_anchors_bar"]]
    temperature = float(pipe["ground_temperature_c"])
    minimum = max(
        _diameter_flow_kg_s(diameter_in=diameter_in, pressure_bar=a, temperature_c=temperature,
                            velocity_m_s=float(pipe["min_velocity_m_s"]))
        for a in anchors
    )
    maximum = min(
        _diameter_flow_kg_s(diameter_in=diameter_in, pressure_bar=a, temperature_c=temperature,
                            velocity_m_s=float(pipe["max_velocity_m_s"]))
        for a in anchors
    )
    return minimum, maximum


def _cheapest_admissible_diameter(pipe: dict, flow_kg_s: float) -> float | None:
    admissible = []
    for entry in pipe["pipe_diameters"]:
        diameter = float(entry["diameter_in"])
        low, high = _diameter_flow_window_kg_s(pipe, diameter)
        if low <= flow_kg_s <= high:
            admissible.append(diameter)
    return min(admissible) if admissible else None


def _trunk_levelized_usd_per_tonne(pipe: dict, case: dict, trunk_km: float,
                                   annual_tonnes: float, pv_factor: float,
                                   diameter_in: float) -> float:
    capex = pipe_capex_usd(diameter_in=diameter_in, length_km=trunk_km, case=case)
    lifecycle = capex * (1.0 + float(case["pipeline_maintenance_fraction"]) * pv_factor)
    return lifecycle / (annual_tonnes * pv_factor)


def crossover_table(
    *,
    annual_tonnes_grid: list[float],
    trunk_km: float,
    lastmile_km: float,
    full_route_km: float,
    per_well_annual_tonnes: float,
    cost_case: str,
) -> list[dict]:
    assumptions = load_assumptions(DEFAULT_ASSUMPTIONS)
    pipe = assumptions["pipeline"]
    basis = load_cost_basis(pipe["cost_basis_path"])
    case = basis["cases"][cost_case]
    economics = assumptions["economics"]
    pv_factor = annuity_present_value_factor(
        float(economics["discount_rate"]), int(economics["project_life_years"])
    )
    fallback_diameter = min(float(entry["diameter_in"]) for entry in pipe["pipe_diameters"])
    rows: list[dict] = []
    for annual_tonnes in annual_tonnes_grid:
        trunk_flow = annual_tonnes * 1_000.0 / SECONDS_PER_YEAR
        per_well_flow = per_well_annual_tonnes * 1_000.0 / SECONDS_PER_YEAR
        trunk_diameter = _cheapest_admissible_diameter(pipe, trunk_flow)
        lateral_diameter = _cheapest_admissible_diameter(pipe, per_well_flow)
        rows.append({
            "annual_tonnes": annual_tonnes,
            "mode": "trucking",
            "levelized_usd_per_tonne": trucking_logistics_usd_per_tonne(case, full_route_km),
            "hydraulically_admissible": True,
            "diameter_in": None,
        })
        pipe_diameter = trunk_diameter if trunk_diameter is not None else fallback_diameter
        rows.append({
            "annual_tonnes": annual_tonnes,
            "mode": "pipeline_direct",
            "levelized_usd_per_tonne": _trunk_levelized_usd_per_tonne(
                pipe, case, trunk_km, annual_tonnes, pv_factor, pipe_diameter
            ),
            "hydraulically_admissible": trunk_diameter is not None and lateral_diameter is not None,
            "diameter_in": pipe_diameter,
        })
        rows.append({
            "annual_tonnes": annual_tonnes,
            "mode": "hybrid_trunk_truck",
            "levelized_usd_per_tonne": _trunk_levelized_usd_per_tonne(
                pipe, case, trunk_km, annual_tonnes, pv_factor, pipe_diameter
            )
            + trucking_logistics_usd_per_tonne(case, lastmile_km),
            "hydraulically_admissible": trunk_diameter is not None,
            "diameter_in": pipe_diameter,
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="output/crossover/pipeline_cost_crossover.csv")
    parser.add_argument("--trunk-km", type=float, default=68.0)
    parser.add_argument("--lastmile-km", type=float, default=5.0)
    parser.add_argument("--full-route-km", type=float, default=78.0)
    parser.add_argument("--per-well-annual-tonnes", type=float, default=1_516.0)
    parser.add_argument("--cost-case", default="base", choices=["low", "base", "high"])
    args = parser.parse_args()
    grid = [10_000.0 * (10 ** (i / 8.0)) for i in range(0, 17)]  # 10 kt/yr -> 1 Mt/yr, log-spaced
    rows = crossover_table(
        annual_tonnes_grid=grid,
        trunk_km=args.trunk_km,
        lastmile_km=args.lastmile_km,
        full_route_km=args.full_route_km,
        per_well_annual_tonnes=args.per_well_annual_tonnes,
        cost_case=args.cost_case,
    )
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} rows -> {target}")


if __name__ == "__main__":
    main()
