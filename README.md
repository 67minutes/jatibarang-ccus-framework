# Jatibarang CCUS Framework

Spec Kit workspace for an integrated CO2 Huff-and-Puff CCUS screening and
planning framework for Jatibarang-class fractured carbonate reservoirs.

The repo is organized around the paper/demo framework, not the upstream training
pipeline. The frozen surrogate checkpoint and selected derived validation
artifacts are consumed here; the 177-case MRST training corpus stays in
`C:\Users\mauli\Documents\boreyes2026`.

## Current Status

Features 001, 002, 003, 004, and the Feature 005 integration service are implemented.
Feature 001 is the
subsurface surrogate inference service. Feature 002 builds cached, exclusion-aware
multi-source route libraries, optimizes pipeline topology and boosters with Pyomo/CBC,
performs continuous CoolProp hydraulic verification, and compares pipeline and
trucking supply costs on a common accounting basis. Feature 003 sizes one dedicated
well-pad facility per selected well, reconciles equipment/well/portfolio costs and CO2
losses, and carries a real eight-case offline DWSIM validation bundle. Feature 004
annualizes physical profiles, consumes mutually exclusive raw supply-cost contracts,
reconciles storage, and evaluates pre-tax plus parametric fiscal sensitivities across
four pinned carbon-price cases. Feature 005 adds synchronous and SSE screening routes,
exact warm-seed coverage, request-local inference deduplication, per-price schedule and
network selection, selected-well facilities, two-pass economics, same-set trucking,
interference/discrepancy audits, deterministic shortlists, cancellation, health, and
preset readiness reporting.

Feature 001 compiles physical 64 x 64 geology and eight-frame warm-start histories into the
promoted checkpoint contract, performs deterministic CPU rollouts, derives production,
CO2 inventory and plume summaries, and serves single or batched predictions through
FastAPI.

The production Feature 005 path no longer calls the analytic `_evaluate_candidate()`
proxy. The legacy Phase 1 abstract-number command remains available for provenance,
but `/screen` uses Features 001-004 through their stable typed contracts. The real
`jatibarang_demo_v1` and `jatibarang_full_v1` MRST-derived payloads are not yet
materialized locally, so preset promotion is explicitly **BLOCKED** while inline and
synthetic integration evidence pass. Final A/B/C execution and paper-number promotion
still belong to Feature 007. See
[`ABSTRACT_STATE_TO_FULL_PAPER_IMPLEMENTATION_GAP.md`](ABSTRACT_STATE_TO_FULL_PAPER_IMPLEMENTATION_GAP.md)
for the current closure sequence.

### Feature 001 evidence

- Mechanical tests: **PASS**, 41 tests.
- Five-case local validation: **PASS mechanically; CONDITIONAL scientifically**.
- Warm one-step p95: `0.0737 s`.
- 24-step single-rollout p95: `1.7610 s`.
- Compact `200 x 24` batch: `281.12 s`, `806,875,136` bytes peak RSS.
- Promoted checkpoint SHA-256:
  `7A685C7EDB99BF00F6075D6DE4AA55EF2F4A7D8CC7F93ABB7B37A6359885566B`.

Longer-than-24-step forecasts are returned with an extended-horizon confidence flag.
Inventory and produced-back CO2 remain engineering approximations because the frozen
checkpoint has no dedicated produced-CO2 output head.

### Feature 002 evidence

- Mechanical infrastructure tests: **PASS**, 29 tests.
- Full route library: 20 unfiltered candidates, 1 source, 54 free/hydraulic
  junctions, 108 reusable segments, and 63 raw source/nearest-neighbour paths.
- Default proxy net-value result: audited `no_viable_network` (zero wells are
  economically rational under the current proxy values and screened costs).
- Mandatory W01 validation fixture: **PASS**, 6 active segments, 2 flow-sized
  boosters, optimal CBC result in `1.044 s` cumulative solver time, zero reported gap.
- Continuous audit: peak and annual mass-balance residuals below `1e-9`; worst
  PWL/continuous difference `1.223 bar`, within the `max(1 bar, 5%)` gate.
- Base comparison: pipeline `3,475.15 USD/t` versus trucking `21.95 USD/t` for the
  deliberately low-throughput validation fixture. This is a screening sensitivity,
  not an Indonesian quote or a general mode-crossover claim.
- Evidence: [`paper/validation/feature002/`](paper/validation/feature002/).

### Feature 003 evidence

- Mechanical facility and artifact tests: **PASS**, 28 tests.
- Offline engineering validation: **PASS**, 8/8 DWSIM 10.0.9650 cases converged.
- Compressor/pump/total-power MAPE: `0.0000165%`, `0.0000000074%`, and
  `0.0000147%`; maximum individual power error: `0.0000198%`.
- Maximum reported DWSIM mass-balance residual: `0.0%`.
- Ownership: one dedicated skid per selected well; equipment sums to wells and wells
  sum to the portfolio exactly once.
- Pressure boundary: only recovered production CO2 is compressed; fresh plus dense
  recycle CO2 is pumped once across the remaining wellhead pressure rise.
- Evidence: [`paper/validation/feature003/`](paper/validation/feature003/) and
  [`docs/dwsim-validation/`](docs/dwsim-validation/).

Facility costs remain literature-aligned low/base/high screening proxies, not FEED,
proprietary Jatibarang design data, or Indonesian vendor quotations.

### Feature 004 evidence

- Focused economic-engine tests: **PASS**, 26 tests.
- Reference batch: **PASS**, 36 portfolio x carbon-price x fiscal combinations.
- Maximum cash-flow accounting residual: `1.1642e-10 USD`; storage reconciliation
  tolerance is `1e-6 tonne` and the maximum stream/inventory divergence fraction in
  the fixture is `0.002`.
- Metric fixtures: known IRR error `1.05e-11`, fractional discounted payback matched,
  and multiple/no-root statuses passed.
- Warmed `200 x 4 x 3` three-active-year batch with distinct cash-flow vectors:
  `0.8357 s` p95 on the local presentation machine, below the `1.0 s` gate.
- Evidence: [`paper/validation/feature004/`](paper/validation/feature004/).

The accounting and promotion verdicts are mechanically `PASS`. The economic outputs
remain screening-grade parametric fiscal sensitivities, not exact PSC replicas or
final-paper economics.

### Feature 005 evidence

- Focused screening tests: **PASS**, 23 tests.
- Complete repository regression: **PASS**, 140 tests.
- Synthetic integration fixtures prove request-local deduplication, selected-well-only
  facility ownership, a carbon-price selection pivot, partial-failure responses, the
  non-convergent pass-1/pass-2 audit, SSE sequencing, cancellation, and 429/503 mapping.
- Checkpoint, CBC, terrain, facility basis, and economic basis readiness: **READY**.
- `jatibarang_demo_v1` and `jatibarang_full_v1` payload readiness: **NOT READY** because
  the fixed upstream MRST seed exports have not been completed and imported.
- Bounded upstream exporter smoke: **PASS**, one eight-frame derived seed in `68.077 s`;
  this is producer evidence only and does not make the demo bank ready.
- Mechanical preset-promotion verdict: **BLOCKED, no fabricated result**. The
  hash-verified dependency evidence is in
  [`paper/validation/feature005/`](paper/validation/feature005/).
- Scientific/paper promotion: **DEFERRED TO FEATURE 007**.

## Install and Verify

```powershell
python -m pip install -e ".[test]"
python -m pytest -q
```

With the promoted checkpoint present under `models/checkpoints/`, start the service:

```powershell
uvicorn jatibarang_ccus.api.app:app --app-dir src --host 127.0.0.1 --port 8000
```

The service endpoints are:

- `GET /model/info`
- `POST /predict`
- `POST /predict/batch`
- `POST /screen`
- `POST /screen/stream`
- `DELETE /screen/runs/{run_id}`
- `GET /presets`
- `GET /health`

Interactive API documentation is available at `http://127.0.0.1:8000/docs`.

## Screening Workbench (Feature 006)

The `frontend/` directory holds the screening workbench — a classical WIMP
desktop-style single-page app (menu bar / toolbar / status bar / docked panels)
with a field-twin 3D terrain viewport. Build it and the FastAPI app serves it at
the site root:

```powershell
cd frontend
npm install
npm run build
```

With a build present under `frontend/dist/`, the workbench is available at
`http://127.0.0.1:8000/`. The static mount is a guarded no-op when no build is
present, so the API and test suite run unchanged. See
[`frontend/README.md`](frontend/README.md) for development, testing, and the
demo-asset notes. Screening logic stays in the backend; the frontend is an API
client, renderer, and client-side carbon-price pivot.

## Start Here

- Project rules: `.specify/memory/constitution.md`
- Feature specs: `specs/`
- Feature 001 plan and evidence: `specs/001-subsurface-surrogate/`
- Feature 002 plan and evidence: `specs/002-pipeline-optimizer/`
- Feature 003 plan and evidence: `specs/003-facility-model/`
- Feature 004 plan and evidence: `specs/004-economic-engine/`
- Feature 005 plan and evidence: `specs/005-screening-api/`
- Saved validation and benchmark reports: `paper/validation/`
- Active Spec Kit feature pointer: `.specify/feature.json`
- Local checkpoint drop zone: `models/checkpoints/`
- Local data drop zones: `data/terrain/`, `data/validation_cases/`,
  `data/scenario_b_runs/`, `data/screening_presets/`

## Feature Map

1. `specs/001-subsurface-surrogate/` - frozen surrogate inference service
   (**implemented and consumed by Feature 005**)
2. `specs/002-pipeline-optimizer/` - CO2 routing and logistics
   (**implemented and consumed by Feature 005**)
3. `specs/003-facility-model/` - surface facility sizing and cost model
   (**implemented and consumed by Feature 005**)
4. `specs/004-economic-engine/` - annual DCF and Indonesian fiscal sensitivities
   (**implemented and consumed by Feature 005; final-paper economics pending**)
5. `specs/005-screening-api/` - coupled screening API
   (**implemented mechanically; real derived presets and Feature 007 promotion pending**)
6. `specs/006-frontend/` - screening workbench frontend
   (**implemented; served at `/` from a `frontend/dist` build**)
7. `specs/007-paper-figures/` - paper and presentation figures

## Data Policy

Commit small source/configuration data that the app needs to run. Keep large
binary artifacts out of git:

- PyTorch checkpoints: `models/checkpoints/`
- SRTM/terrain rasters: `data/terrain/`
- Full MRST plume-validation cases: `data/validation_cases/`
- Scenario B limited-simulation runs/results: `data/scenario_b_runs/`
- Feature 005 derived preset payloads: `data/screening_presets/*/payload.npz`

Tiny surrogate regression fixtures may live in `tests/fixtures/surrogate/` when
they are intentionally small enough to review and version.
