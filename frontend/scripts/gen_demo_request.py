"""Generate a valid demo inline screening request for the workbench.

The real MRST-derived preset payloads are not materialized locally (preset
readiness is BLOCKED), so the demo path uses an *inline* request. This builds a
small but genuinely valid request — uniform-field geology, real Jatibarang-area
coordinates, 3 candidate wells, 4 carbon prices, 2 schedules — that the real
backend can screen end to end. The uniform geology means the plume renders flat;
that is honest for a dev/demo fixture and is replaced by real MRST fields when
Feature 007 lands.

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
from tests.screening.helpers import (  # noqa: E402
    economic_dimensions,
    geology,
    schedule,
    seed,
)

# A tightly clustered well group (~200-300 m spacing) around an on-field source,
# so short pipeline segments have a chance of being economic. The default wide
# spacing plus a distant source makes every pipeline uneconomic at this
# in-envelope throughput.
WELLS = [
    ("W01", -6.4830, 108.3110),
    ("W02", -6.4825, 108.3145),
    ("W03", -6.4848, 108.3160),
]

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
    # The operational grid below sweeps injection rate only (fixed cycles), so it
    # expands to exactly these two schedules — one seed each, full coverage.
    schedules = [schedule(rate=9000.0, cycles=3), schedule(rate=6000.0, cycles=3)]
    carbon_prices, fiscal_cases, assumptions = economic_dimensions()

    fingerprints = [schedule_fingerprint(item) for item in schedules]
    provenance = fiscal_cases[0].provenance[0]

    candidates = [
        ScreeningCandidate(
            candidate_id=well_id,
            location=Coordinate(latitude=lat, longitude=lon),
            geology_id="G",
            seed_by_schedule_fingerprint={
                fingerprints[idx]: f"S{idx}" for idx in range(len(schedules))
            },
            produced_co2=ProducedCO2Assumption(mole_fraction=0.65, provenance=provenance),
        )
        for well_id, lat, lon in WELLS
    ]

    return InlineScreenRequest(
        mode="inline",
        geologies={"G": geology()},
        seeds={f"S{idx}": seed(item) for idx, item in enumerate(schedules)},
        candidates=candidates,
        sources=[demo_source()],
        operational_grid=OperationalGrid(
            injection_rate_m3_day=[9000.0, 6000.0],
            injection_duration_days=[45.0],
            soak_duration_days=[30.0],
            production_duration_days=[190.0],
            production_bhp_psi=[675.0],
            cycles=[3],
        ),
        annual_co2_budget_tonnes=320_000.0,
        carbon_prices=carbon_prices,
        fiscal_cases=fiscal_cases,
        economic_assumptions=assumptions,
        shortlist_top_k=5,
        detailed_top_k=3,
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
