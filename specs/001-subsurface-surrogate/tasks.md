# Tasks: Feature 001 Subsurface Surrogate Inference Service

## Phase 1: Setup

- [X] T001 Update Feature 001 specification and design artifacts under `specs/001-subsurface-surrogate/`
- [X] T002 Add FastAPI runtime and API test dependencies in `pyproject.toml`
- [X] T003 Refresh the managed plan reference in `AGENTS.md`

## Phase 2: Foundational

- [X] T004 Add locked channel/training/confidence metadata in `src/jatibarang_ccus/surrogate/metadata.py`
- [X] T005 Add typed physical and API schemas in `src/jatibarang_ccus/surrogate/schemas.py`
- [X] T006 Add tensor and schedule regression tests in `tests/surrogate/test_preprocessing.py`
- [X] T007 Implement schedule/tensor compilation and extrapolation flags in `src/jatibarang_ccus/surrogate/preprocessing.py`

## Phase 3: User Story 1 - Deterministic Physical Forecast

- [X] T008 [US1] Add scheduled rollout regression tests in `tests/surrogate/test_rollout.py`
- [X] T009 [US1] Refactor deterministic scheduled inference in `src/jatibarang_ccus/surrogate/runner.py`
- [X] T010 [US1] Add physical production conversion and cumulative series in `src/jatibarang_ccus/surrogate/runner.py`

## Phase 4: User Story 2 - Batch Screening

- [X] T011 [US2] Add batch equivalence and selection tests in `tests/surrogate/test_batch_rollout.py`
- [X] T012 [US2] Implement horizon-grouped microbatch inference in `src/jatibarang_ccus/surrogate/runner.py`

## Phase 5: User Story 3 - Engineering Outputs

- [X] T013 [US3] Add analytic physics tests in `tests/surrogate/test_postprocessing.py`
- [X] T014 [US3] Implement inventory, mass reconciliation, plume, and confidence outputs in `src/jatibarang_ccus/surrogate/postprocessing.py`

## Phase 6: User Story 4 - FastAPI Service

- [X] T015 [US4] Add endpoint and lifecycle tests in `tests/surrogate/test_api.py`
- [X] T016 [US4] Implement the shared FastAPI application and Feature 001 routes in `src/jatibarang_ccus/api/app.py`

## Phase 7: Validation and Polish

- [X] T017 Add five-case validation and benchmark runner in `src/jatibarang_ccus/surrogate/validation.py`
- [X] T018 Save mechanical and scientific evidence under `paper/validation/`
- [X] T019 Run the complete test suite, OpenAPI check, validation, and benchmarks
- [X] T020 Mark completed tasks and document any scientific caveats in `specs/001-subsurface-surrogate/tasks.md`

## Dependencies

`T001-T007 -> US1 -> US2 -> US3 -> US4 -> T017-T020`

Every phase is blocking. No task touching `runner.py` executes in parallel.

## Completion Evidence

- Mechanical tests: **PASS** (`41` tests collected and passed, including saved/generated OpenAPI contract comparison and a 200-scenario compact API request).
- Five-case validation: **PASS** mechanically; **CONDITIONAL** scientifically. Evidence is saved in `paper/validation/feature001_validation.json` and `paper/validation/feature001_validation.csv`.
- Performance promotion gate: **PASS** on the recorded machine. Warm one-step p95 was `0.0737 s`, 24-step rollout p95 was `1.7610 s`, and the compact `200 x 24` batch completed in `281.12 s` with `806,875,136` bytes peak RSS.
- Checkpoint identity: SHA-256 `7A685C7EDB99BF00F6075D6DE4AA55EF2F4A7D8CC7F93ABB7B37A6359885566B`; benchmark details are saved in `paper/validation/feature001_benchmark.json`.

## Scientific Caveats

- The validation bundle contains five curated local cases, not the full upstream 36-case held-out evaluation.
- Curated case files do not contain a distinct pre-operation frame; their first exported frame is used only as the validation inventory baseline. The public API still requires the full pre-operation state plus eight-frame seed contract.
- Inventory and produced-back CO2 are geometry- and density-aware approximations because the frozen checkpoint has no dedicated produced-CO2 prediction head.
- Forecast steps beyond the upstream validated 24-step horizon remain explicitly low confidence.
- Pressure R2 can become unstable when a target field is nearly spatially uniform; pressure RMSE must be considered with it.
