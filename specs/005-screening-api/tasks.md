# Tasks: Feature 005 Screening Orchestrator

## Phase 1: Design and setup

- [X] T001 Create Feature 005 plan, research, data model, quickstart, and task artifacts
- [X] T002 Point Spec Kit and AGENTS context to Feature 005 and extend preset ignore rules
- [X] T003 Freeze OpenAPI and derived seed-design contracts

## Phase 2: Tests first

- [X] T004 Add request/grid/seed-coverage and preset-loader tests
- [X] T005 Add adapter/accounting/interference/shortlist tests
- [X] T006 Add orchestration order, caching, pivot, discrepancy, and failure tests
- [X] T007 Add API, SSE, cancellation, health, presets, and OpenAPI tests

## Phase 3: Core implementation

- [X] T008 Implement screening Pydantic schemas and deterministic grid expansion
- [X] T009 Implement preset registry, manifest validation, and derived-payload importer
- [X] T010 Implement real prediction-to-pipeline/facility/economic adapters
- [X] T011 Implement interference, flags, shortlist, and cross-price assembly
- [X] T012 Implement progress events, transient run registry, cancellation, and active-run guard
- [X] T013 Implement the shared 2 -> 1 -> 3 -> 4 orchestration event iterator

## Phase 4: Service and offline integration

- [X] T014 Add `/screen`, `/screen/stream`, cancellation, `/presets`, and `/health`
- [X] T015 Save and validate the Feature 005 OpenAPI contract without changing Feature 001 routes
- [X] T016 Add fixed-geology/fixed-schedule offline exporter support in `boreyes2026`
- [X] T017 Add tracked seed design plus ignored demo/full manifest workflow

## Phase 5: Evidence and promotion

- [X] T018 Add Feature 005 validation CLI, synthetic promotion fixture, and manifest verification
- [X] T019 Run focused and complete tests, contract checks, and dependency checks
- [X] T020 Generate the Feature 005 mechanical evidence bundle without fabricating missing real presets
- [X] T021 Synchronize README, specs index, gap audit, data docs, and Feature 005 status
- [X] T022 Run diff/link hygiene and record final mechanical versus scientific verdict

## Dependencies

`T001-T003 -> T004-T007 -> T008-T013 -> T014-T017 -> T018-T022`

Tests precede implementation. Shared API and orchestration files are changed
sequentially. The upstream exporter remains offline and cannot become a runtime import.
