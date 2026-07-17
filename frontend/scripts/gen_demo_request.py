"""Generate the real case-0016 validation preview used by the workbench.

The promoted 200/3,240-scenario banks are not materialized yet, so the offline
startup path remains an inline request. Unlike the old uniform gray fixture,
this request uses the declared Figure-3 median-error validation case: its actual
MRST-derived static geology, eight-frame MRST warm start, and exact operating
schedule. It is a local proxy at W01, not a surveyed field orientation.

Run from the repo root:

    python frontend/scripts/gen_demo_request.py

Writes: frontend/public/assets/demo-request.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

from jatibarang_ccus.contracts import CO2Source, Coordinate  # noqa: E402
from jatibarang_ccus.screening.schemas import (  # noqa: E402
    InlineScreenRequest,
    OperationalGrid,
    ProducedCO2Assumption,
    ScreeningCandidate,
)
from jatibarang_ccus.surrogate.preprocessing import schedule_fingerprint  # noqa: E402
from jatibarang_ccus.surrogate.validation import load_validation_case  # noqa: E402
from tests.screening.helpers import economic_dimensions  # noqa: E402

# A tightly clustered well group (~200-300 m spacing) around an on-field source,
# so short pipeline segments have a chance of being economic. The default wide
# spacing plus a distant source makes every pipeline uneconomic at this
# in-envelope throughput.
WELL = ("W01", -6.4830, 108.3110)

# An on-field CO2 source co-located with the well cluster (< ~1.5 km) so the
# optimizer can build a short, viable pipeline network. The default fixture
# source is ~60 km away, which yields the honest but flat "no_viable_network"
# outcome given the small in-envelope per-well CO2 demand.
def demo_source() -> CO2Source:
    return CO2Source(
        id="SRC",
        name="Jatibarang demo source",
        location=Coordinate(latitude=-6.4900, longitude=108.3120),
        capacity_tonnes_per_year=500_000.0,
        max_mass_flow_kg_s=600.0,
        outlet_pressure_bar=120.0,
        outlet_temperature_c=27.0,
        co2_purity=0.95,
    )


def build_request() -> InlineScreenRequest:
    # The exact Figure-3 case schedule keeps the MRST warm start and surrogate
    # rollout scientifically aligned; this is not a synthetic operating sweep.
    validation, _targets = load_validation_case("case_0016")
    active_schedule = validation.schedule
    carbon_prices, fiscal_cases, assumptions = economic_dimensions()

    fingerprint = schedule_fingerprint(active_schedule)
    provenance = fiscal_cases[0].provenance[0]
    well_id, lat, lon = WELL
    candidate = ScreeningCandidate(
        candidate_id=well_id,
        location=Coordinate(latitude=lat, longitude=lon),
        geology_id="case_0016",
        seed_by_schedule_fingerprint={fingerprint: "case_0016_seed"},
        produced_co2=ProducedCO2Assumption(mole_fraction=0.65, provenance=provenance),
    )

    return InlineScreenRequest(
        mode="inline",
        geologies={"case_0016": validation.geology},
        seeds={"case_0016_seed": validation.seed},
        candidates=[candidate],
        sources=[demo_source()],
        operational_grid=OperationalGrid(
            injection_rate_m3_day=[active_schedule.injection_rate_m3_day],
            injection_duration_days=[active_schedule.injection_duration_days],
            soak_duration_days=[active_schedule.soak_duration_days],
            production_duration_days=[active_schedule.production_duration_days],
            production_bhp_psi=[active_schedule.production_bhp_psi],
            cycles=[active_schedule.cycles],
        ),
        annual_co2_budget_tonnes=320_000.0,
        carbon_prices=carbon_prices,
        fiscal_cases=fiscal_cases,
        economic_assumptions=assumptions,
        shortlist_top_k=5,
        detailed_top_k=1,
    )


def main() -> None:
    request = build_request()
    out = REPO_ROOT / "frontend" / "public" / "assets" / "demo-request.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = json.loads(request.model_dump_json())
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
