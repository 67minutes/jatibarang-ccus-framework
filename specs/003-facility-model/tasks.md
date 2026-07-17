# Tasks: Feature 003 Surface Facility Cost Model

**Input**: Design documents from `specs/003-facility-model/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/facility-model.schema.json`, `quickstart.md`

**Tests**: Required by the approved plan. Tests precede the implementation they validate.

## Phase 1: Setup

- [X] T001 Create Feature 003 runtime, test, DWSIM-tool, documentation, and evidence directories described in `specs/003-facility-model/plan.md`
- [X] T002 Add contract-validation test dependencies and keep DWSIM outside runtime dependencies in `pyproject.toml`
- [X] T003 Verify Python/.NET ignore patterns and add only missing Feature 003 build/output patterns in `.gitignore`

## Phase 2: Foundational Contracts and Inputs

- [X] T004 [P] Add failing JSON-schema and Pydantic contract tests in `tests/facility/test_contracts.py`
- [X] T005 Implement Feature 003 provenance, well-load, equipment, loss-ledger, well-result, and portfolio request/result models in `src/jatibarang_ccus/contracts.py`
- [X] T006 [P] Add versioned facility design, cost, and eight-case calibration inputs in `data/jatibarang/facility_design_basis.json`, `data/jatibarang/facility_cost_basis.json`, and `data/jatibarang/facility_validation_cases.json`
- [X] T007 Implement strict basis-file loading, hashing, coefficient validation, and power-law equipment costing in `src/jatibarang_ccus/infrastructure/facility_costs.py`
- [X] T008 Run the contract tests and validate `specs/003-facility-model/contracts/facility-model.schema.json` against the Pydantic schemas

## Phase 3: User Story 1 - Correct Physical Facility Sizing (Priority: P1) MVP

**Goal**: Size a dedicated well-pad skid with correct standard-volume mass conversion, fresh-stream pumping, recycle-only compression, intercooling, and three-phase separator calculations.

**Independent Test**: A one-well request passes analytic unit tests, never applies the same pressure rise to fresh compression and pumping, and produces finite monotonic equipment duties.

- [X] T009 [P] [US1] Add failing standard-volume, phase-boundary, pressure-split, and zero-pressure-rise tests in `tests/facility/test_pressure_duty.py`
- [X] T010 [P] [US1] Add failing separator, dehydration, train-count, and monotonic-sizing tests in `tests/facility/test_equipment_sizing.py`
- [X] T011 [US1] Add standard-flow conversion, phase checks, and reusable compression/cooling state helpers in `src/jatibarang_ccus/infrastructure/thermo.py`
- [X] T012 [US1] Implement dedicated-skid pump, recycle-compressor, intercooler, dehydration, and separator calculations in `src/jatibarang_ccus/infrastructure/facility.py`
- [X] T013 [US1] Add calibration-envelope classification and warm eight-well runtime timing in `src/jatibarang_ccus/infrastructure/facility.py`
- [X] T014 [US1] Run User Story 1 tests in `tests/facility/` and confirm the eight-well p95 runtime is at most 0.5 seconds

## Phase 4: User Story 2 - Auditable Cost, Ownership, and Loss Accounting (Priority: P1)

**Goal**: Cost every equipment item once, return exact per-well/portfolio allocations, and separate handling losses from bulk produced-back CO2.

**Independent Test**: A multi-well request reconciles equipment to well to portfolio exactly, remains monotonic across low/base/high cases, and cannot double-count produced-back CO2 as a surface loss.

- [X] T015 [P] [US2] Add failing cost-case, equipment-train, loss-ledger, and portfolio-reconciliation tests in `tests/facility/test_costs_ownership_and_losses.py`
- [X] T016 [US2] Implement per-equipment CAPEX, energy, maintenance, redundancy, and provenance accounting in `src/jatibarang_ccus/infrastructure/facility_costs.py`
- [X] T017 [US2] Implement surface-loss mass ledgers and exact portfolio aggregation in `src/jatibarang_ccus/infrastructure/facility.py`
- [X] T018 [P] [US2] Add failing selected-portfolio compatibility tests in `tests/facility/test_phase1_adapter.py`
- [X] T019 [US2] Replace the per-well multiplied facility loop with one portfolio evaluation and per-well allocations in `src/jatibarang_ccus/phase1/case_study.py`
- [X] T020 [US2] Adapt the temporary Feature 004 input bridge without changing Feature 001/002 contracts in `src/jatibarang_ccus/infrastructure/economics.py`
- [X] T021 [US2] Run User Story 2 and existing regression tests in `tests/facility/`, `tests/phase1/`, and `tests/infrastructure/`

## Phase 5: User Story 3 - Reproducible DWSIM Calibration and Evidence (Priority: P2)

**Goal**: Refresh an eight-case offline DWSIM benchmark and produce a hashed comparison bundle without adding a runtime simulator dependency.

**Independent Test**: The validation CLI rejects missing/non-converged references, verifies hashes, computes error gates, and produces deterministic CSV/JSON/PNG evidence for eight converged cases.

- [X] T022 [P] [US3] Add failing runtime-only, compare-mode, gate, and artifact-manifest tests in `tests/facility/test_validation_artifacts.py`
- [X] T023 [US3] Implement runtime-only and DWSIM comparison/evidence CLI modes in `src/jatibarang_ccus/infrastructure/facility_validation.py`
- [X] T024 [P] [US3] Add the offline DWSIM automation project in `tools/dwsim/FacilityValidationRunner/FacilityValidationRunner.csproj` and `tools/dwsim/FacilityValidationRunner/Program.cs`
- [X] T025 [US3] Build and pin the DWSIM reference flowsheet and process-flow diagram in `docs/dwsim-validation/jatibarang_facility.dwxmz` and `docs/dwsim-validation/process_flow_diagram.png`
- [X] T026 [US3] Document the flowsheet, named streams, unit operations, property package, automation, and evidence semantics in `docs/dwsim-validation/README.md` and `docs/dwsim-validation/methodology.md`
- [X] T027 [US3] Run all eight DWSIM cases and save `paper/validation/feature003/dwsim_reference.csv`
- [X] T028 [US3] Generate and inspect the complete Feature 003 comparison and hash bundle under `paper/validation/feature003/`
- [X] T029 [US3] Run artifact tests in `tests/facility/test_validation_artifacts.py` and record separate verdicts in `paper/validation/feature003/artifact_manifest.json`

## Phase 6: Polish and Promotion

- [X] T030 Run `python -m pytest -q tests/facility`, the complete `python -m pytest -q` suite, schema checks, and `git diff --check`
- [X] T031 Synchronize Feature 003 status and evidence across `README.md`, `specs/README.md`, `specs/003-facility-model/spec.md`, `specs/003-facility-model/plan.md`, `specs/003-facility-model/quickstart.md`, `ABSTRACT_STATE_TO_FULL_PAPER_IMPLEMENTATION_GAP.md`, and `data/README.md`
- [X] T032 Add the evidence interpretation and regeneration command in `paper/validation/feature003/README.md`
- [X] T033 Mark completed work and retain any genuine external-validation blocker in `specs/003-facility-model/tasks.md`

## Dependencies and Execution Order

`T001-T008 -> US1 -> US2 -> US3 -> T030-T033`

- T004 and T006 can proceed in parallel after setup because they touch independent files.
- T009 and T010 can proceed in parallel before the shared `facility.py` implementation.
- T018 can be written while T016-T017 are implemented, but T019-T021 remain sequential.
- T022 and T024 can proceed in parallel after the runtime contracts stabilize.
- T027 requires an installed/pinned DWSIM and the completed T024-T026 surface.
- Documentation promotion wording in T031 depends on the actual T027-T030 verdict and must not be predeclared.

## Implementation Strategy

1. Complete the typed, unit-safe MVP through User Story 1.
2. Close ownership, loss, and compatibility accounting in User Story 2.
3. Treat DWSIM as a separate offline evidence gate in User Story 3; never substitute synthetic reference rows for a missing process-simulator run.
4. Promote documentation only from saved tests and artifacts.

## Explicit Boundaries

- Do not import DWSIM/.NET assemblies from the runtime Python package.
- Do not alter Feature 001 model behavior or Feature 002 route/MILP contracts.
- Do not copy the raw MRST training corpus.
- Do not represent screening costs as FEED, vendor quotes, or proprietary Jatibarang data.
- Do not mark DWSIM-dependent tasks complete without a real converged reference file and matching model/version hashes.
