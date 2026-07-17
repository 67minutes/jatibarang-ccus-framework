# Tasks: Feature 002 Pipeline and Logistics Optimizer

## Phase 1: Setup

- [X] T001 Freeze Feature 002 plan, research, data model, quickstart, and JSON contract under `specs/002-pipeline-optimizer/`
- [X] T002 Add validation dependencies and tracked pipeline/exclusion/cost configuration under `pyproject.toml` and `data/jatibarang/`
- [X] T003 Refresh `.specify/feature.json` and the managed Feature 002 reference in `AGENTS.md`

## Phase 2: Foundational Contracts

- [X] T004 Add contract validation tests in `tests/infrastructure/test_pipeline_contracts.py`
- [X] T005 Implement typed route, demand, hydraulic, solver, cost, and supply models in `src/jatibarang_ccus/contracts.py`

## Phase 3: User Story 1 - Auditable Route Library

**Goal**: produce deterministic exclusion-aware source/well/junction routes.

**Independent test**: repeated builds have the same fingerprint and no hard-zone crossing.

- [X] T006 [US1] Add terrain bounds, exclusion, penalty, fingerprint, and junction tests in `tests/infrastructure/test_routing_exclusions.py`
- [X] T007 [US1] Implement exclusion GeoJSON loading, projection, raster masks, and provenance in `src/jatibarang_ccus/infrastructure/routing.py`
- [X] T008 [US1] Correct metric distance/slope behavior and endpoint validation in `src/jatibarang_ccus/infrastructure/routing.py`
- [X] T009 [US1] Implement multi-source route union, free-junction compression, and route-library fingerprints in `src/jatibarang_ccus/infrastructure/routing.py`

## Phase 4: User Story 2 - Optimized and Verified Network

**Goal**: select wells and design a physically verified network from annual demand and peak flow.

**Independent test**: single/multi-source and full Jatibarang cases pass all solver and continuous audits.

- [X] T010 [US2] Add signed pressure, PWL, booster, and continuous-profile tests in `tests/infrastructure/test_hydraulic_verification.py`
- [X] T011 [US2] Add selection, shared-junction, empty, infeasible, and multi-source MILP tests in `tests/infrastructure/test_pipeline_network.py`
- [X] T012 [US2] Implement peak-flow curves, signed local-state integration, and verification helpers in `src/jatibarang_ccus/infrastructure/hydraulics.py`
- [X] T013 [US2] Implement objective modes, multi-source flow, DCC loss, MAOP, velocities, and sized boosters in `src/jatibarang_ccus/infrastructure/pipeline.py`
- [X] T014 [US2] Implement solver-status handling, continuous audit, retry/failure states, and flow-based allocation in `src/jatibarang_ccus/infrastructure/pipeline.py`
- [X] T015 [US2] Update the Phase 1 adapter and existing infrastructure tests in `src/jatibarang_ccus/phase1/case_study.py` and `tests/infrastructure/`

## Phase 5: User Story 3 - Supply and Cost Comparison

**Goal**: compare pipeline and trucking with a reconciled low/base/high accounting basis.

**Independent test**: both modes return common, monotonic, provenance-complete cost results.

- [X] T016 [US3] Add cost, accounting, and supply comparison tests in `tests/infrastructure/test_supply_comparison.py`
- [X] T017 [US3] Implement NETL-derived cost cases and tracked source metadata in `src/jatibarang_ccus/infrastructure/costs.py` and `data/jatibarang/pipeline_cost_basis.json`
- [X] T018 [US3] Implement trucking and common pipeline comparison results in `src/jatibarang_ccus/infrastructure/supply.py`

## Phase 6: Evidence and Polish

- [X] T019 Add validation artifact tests in `tests/infrastructure/test_feature002_validation.py`
- [X] T020 Implement the full-case audit and plot generator in `src/jatibarang_ccus/infrastructure/validation.py`
- [X] T021 Generate and inspect the Feature 002 artifact bundle under `paper/validation/feature002/`
- [X] T022 Update `README.md`, `specs/README.md`, and `ABSTRACT_STATE_TO_FULL_PAPER_IMPLEMENTATION_GAP.md` with the verified Feature 002 verdict
- [X] T023 Run focused infrastructure tests, full regression, contract validation, and `git diff --check`
- [X] T024 Record completion evidence and remaining screening limitations in `specs/002-pipeline-optimizer/tasks.md`

## Dependencies

`T001-T005 -> US1 -> US2 -> US3 -> T019-T024`

US3 tests and cost-source transcription may proceed after contracts while US2 is in
progress, but tasks editing `contracts.py`, `routing.py`, `hydraulics.py`, or
`pipeline.py` remain sequential.

## Implementation Strategy

The first independently useful increment is US1's cached route library. US2 is the
Feature 002 mechanical promotion gate. US3 and the evidence phase complete the
paper-facing logistics comparison without expanding into Feature 005 orchestration.

## Completion Evidence (2026-07-15)

- `python -m pytest -q tests/infrastructure`: PASS, 29 tests.
- `python -m pytest -q`: PASS, 63 tests; Feature 001 saved/generated OpenAPI checks
  remain included in the regression suite.
- Feature 002 prerequisites: PASS; active feature directory and managed `AGENTS.md`
  references resolve to `specs/002-pipeline-optimizer/`.
- `git diff --check`: PASS (line-ending conversion warnings only; no whitespace
  errors).
- `paper/validation/feature002/artifact_manifest.json`: PASS, 20 candidates, no
  candidate prefiltering, 20 hashed files, optimal base solve with zero reported gap.
- Base mandatory validation fixture: 6 built segments, 2 sized boosters, `1.044 s`
  cumulative CBC solver time, maximum PWL/continuous difference `1.223 bar` within
  its 5% tolerance, and peak/annual mass-balance residuals below `1e-9`.
- Default proxy net-value case: audited `no_viable_network`; it is kept separate from
  the mandatory mechanics fixture.
- Low/base/high delivered costs are monotonic and use
  `raw_cashflows_levelized_display_only`; the base low-throughput fixture favors
  trucking (`21.95 USD/t`) over pipeline (`3,475.15 USD/t`).

Remaining boundaries: Feature 005 must supply real surrogate demand/value; pure-CO2
properties are limited to streams at or above 95% purity; public exclusions are not a
field survey; NETL/IEAGHG-derived costs are screening correlations rather than vendor
quotes or FEED; no DWSIM, live MRST, raw training corpus, or HTTP endpoint was added.
