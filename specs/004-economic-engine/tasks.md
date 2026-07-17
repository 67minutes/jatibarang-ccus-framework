# Tasks: Feature 004 Economic Engine

## Phase 1: Design and setup

- [x] T001 Create Feature 004 plan, research, data model, quickstart, tasks, and JSON Schema
- [x] T002 Add versioned economic basis and refresh active Spec Kit references

## Phase 2: Contracts and tests

- [x] T003 Add typed batch, portfolio, annual, supply, fiscal, metric, and result contracts
- [x] T004 Add contract, DCF, storage, revenue, ownership, fiscal, metric, batch, and adapter tests

## Phase 3: Core engine

- [x] T005 Implement annualized raw cash-flow assembly and storage reconciliation
- [x] T006 Implement pre-tax, cost-recovery, gross-split, and carbon-tax sensitivities
- [x] T007 Implement NPV, IRR, discounted payback, break-even solvers, uncertainty, and rankings

## Phase 4: Integration adapters

- [x] T008 Add Feature 001 annualization and Feature 002/003 raw-cost adapters
- [x] T009 Migrate the Phase 1 caller to the new portfolio engine without claiming full integration

## Phase 5: Evidence and promotion

- [x] T010 Add validation CLI, schema checks, manifest verification, and performance benchmark
- [x] T011 Generate the tracked Feature 004 evidence bundle
- [x] T012 Synchronize README, specs index, gap audit, data docs, and Feature 004 completion status
- [x] T013 Run focused and complete tests, manifest/schema checks, markdown links, and diff hygiene

## Dependencies

`T001-T003 -> T004 -> T005-T007 -> T008-T009 -> T010-T013`

Tasks touching shared contracts or the Phase 1 caller execute sequentially. Feature
001-003 APIs remain unchanged.
